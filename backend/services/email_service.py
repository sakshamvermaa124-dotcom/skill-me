"""
SkillMe — Email Service (Brevo SMTP relay)
Sends branded HTML emails for key student lifecycle events.

All public methods are async and never raise — email failures are logged
but never propagate to crash the calling API endpoint.
"""

from __future__ import annotations

import asyncio
import json
import logging
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import settings

logger = logging.getLogger(__name__)

# ── Template engine ─────────────────────────────────────────────────────────
_TEMPLATE_DIR = Path(__file__).parent.parent / "templates" / "emails"

_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
)


def _render(template_name: str, **ctx) -> str:
    """Render a Jinja2 HTML email template with the given context."""
    ctx.setdefault("frontend_url", settings.frontend_url)
    ctx.setdefault("dashboard_url", f"{settings.frontend_url}/dashboard.html")
    tpl = _jinja_env.get_template(template_name)
    return tpl.render(**ctx)


# ── SMTP sender (sync, called inside asyncio.to_thread) ─────────────────────

def _accounts() -> list[tuple[str, str]]:
    """All configured Brevo SMTP accounts as (login, smtp_key), primary first."""
    accounts: list[tuple[str, str]] = []
    if settings.smtp_user and settings.smtp_password:
        accounts.append((settings.smtp_user, settings.smtp_password))
    raw = (settings.smtp_extra_accounts or "").strip()
    if raw:
        try:
            for item in json.loads(raw):
                user, pwd = item.get("user"), item.get("password")
                if user and pwd and all(user != a[0] for a in accounts):
                    accounts.append((user, pwd))
        except Exception as exc:
            logger.error("SMTP_EXTRA_ACCOUNTS is not valid JSON, ignoring it: %s", exc)
    return accounts


# Brevo accepts over-quota mail over SMTP and then silently never delivers it, so we must never
# hand mail to an account that is out of quota. Two sources, best first:
#   1. Brevo's own remaining-credits counter (v3 /account), for every account whose REST API key
#      is configured. This is the truth: it includes sends we don't log (other apps, local runs).
#   2. Our email_logs count since 00:00 UTC, when Brevo's free-plan daily cap resets. A rolling 24h
#      count was tried and leaked: as yesterday's sends aged out it reported free slots while Brevo
#      still said 0, and ~70 mails went to an exhausted account and were dropped.

_REFUSAL_TTL = timedelta(hours=24)
_CREDITS_TTL = timedelta(seconds=60)          # re-ask Brevo at most once a minute per key
_CREDITS_STALE_AFTER = timedelta(minutes=10)  # keep using a last-known value through API blips
_BREVO_ACCOUNT_URL = "https://api.brevo.com/v3/account"


def _quota_day_start_utc() -> str:
    """Start of Brevo's current quota day (00:00 UTC) as a 'YYYY-MM-DD HH:MM:SS' string (matches sent_at)."""
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def _api_keys() -> list[str]:
    """Brevo REST API keys (one per Brevo account; order doesn't matter — each is matched to its SMTP login)."""
    keys = [settings.brevo_api_key] + (settings.brevo_extra_api_keys or "").split(",")
    seen: list[str] = []
    for k in keys:
        k = (k or "").strip()
        if k and k not in seen:
            seen.append(k)
    return seen


# SMTP login -> (credits left, when fetched). Decremented locally on each send between refreshes.
_credits: dict[str, tuple[int, datetime]] = {}
# API key -> when it was last fetched (so a key whose account has no sendLimit plan isn't re-fetched every send)
_key_fetched_at: dict[str, datetime] = {}
_credits_lock = asyncio.Lock()


async def _fetch_credits(client, key: str) -> None:
    resp = await client.get(_BREVO_ACCOUNT_URL, headers={"api-key": key, "accept": "application/json"})
    resp.raise_for_status()
    data = resp.json()
    login = (((data.get("relay") or {}).get("data") or {}).get("userName") or "").strip()
    credits = next((p.get("credits") for p in data.get("plan") or []
                    if p.get("creditsType") == "sendLimit" and p.get("credits") is not None), None)
    if login and credits is not None:
        _credits[login] = (int(credits), datetime.now(timezone.utc))


async def _refresh_credits() -> None:
    """Refresh Brevo's remaining credits for every configured API key whose cached value is older than a minute."""
    keys = _api_keys()
    if not keys:
        return
    async with _credits_lock:
        now = datetime.now(timezone.utc)
        due = [k for k in keys if now - _key_fetched_at.get(k, datetime.min.replace(tzinfo=timezone.utc)) >= _CREDITS_TTL]
        if not due:
            return
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            results = await asyncio.gather(*(_fetch_credits(client, k) for k in due), return_exceptions=True)
        for k, res in zip(due, results):
            _key_fetched_at[k] = now
            if isinstance(res, Exception):
                logger.warning("Brevo credits lookup failed for key ...%s: %s", k[-6:], res)


def _credits_left(login: str) -> int | None:
    """Brevo's remaining sends for this account, or None if unknown (no API key, or API unreachable for 10+ min)."""
    entry = _credits.get(login)
    if entry is None or datetime.now(timezone.utc) - entry[1] > _CREDITS_STALE_AFTER:
        return None
    return entry[0]


def _adjust_credits(login: str, delta: int) -> None:
    entry = _credits.get(login)
    if entry is not None:
        _credits[login] = (entry[0] + delta, entry[1])


async def get_quota_usage() -> list[dict]:
    """Per-account quota state (for account selection and the admin view)."""
    from db.database import db
    await _refresh_credits()
    since = _quota_day_start_utc()
    usage = []
    for i, (user, _) in enumerate(_accounts()):
        # Rows with no smtp_account were sent before multi-account support existed, when the
        # primary was the only account — count them against it.
        account_match = "(smtp_account = ? OR smtp_account IS NULL)" if i == 0 else "smtp_account = ?"
        try:
            row = await db.fetch_one(
                f"SELECT COUNT(*) AS n FROM email_logs WHERE {account_match} AND status = 'sent' AND sent_at >= ?",
                (user, since),
            )
            used = int((row or {}).get("n", 0) or 0)
        except Exception as exc:
            logger.warning("Quota lookup failed for %s: %s", user, exc)
            used = 0
        credits = _credits_left(user)
        # Brevo's counter wins when we have it; our own count is only the fallback.
        exhausted = credits <= 0 if credits is not None else used >= settings.smtp_daily_limit
        usage.append({
            "account": user,
            "used_today": used,
            "limit": settings.smtp_daily_limit,
            "daily_credits": settings.brevo_daily_credits,
            "brevo_credits_left": credits,
            # Best estimate of credits left: Brevo's number, else our own count against the daily cap
            "credits_left": credits if credits is not None else max(0, settings.brevo_daily_credits - used),
            "credits_source": "brevo" if credits is not None else "estimate",
            "exhausted": exhausted,
        })
    return usage


# ── Low-quota alert ──────────────────────────────────────────────────────────
# Once per account per quota day (00:00 UTC), email the owner when an account has used 90%+ of
# its daily credits. Triggered in the background after successful sends.

_alerted: set[tuple[str, str]] = set()  # (login, quota day) already alerted in this process
_alert_running = False
_background: set[asyncio.Task] = set()


def _schedule_quota_alert_check() -> None:
    if not settings.quota_alert_email or _alert_running:
        return
    try:
        task = asyncio.get_running_loop().create_task(_maybe_send_quota_alerts())
    except RuntimeError:
        return
    _background.add(task)
    task.add_done_callback(_background.discard)


async def _maybe_send_quota_alerts() -> None:
    global _alert_running
    to = (settings.quota_alert_email or "").strip()
    if not to or _alert_running:
        return
    _alert_running = True
    try:
        from db.database import db
        day = _quota_day_start_utc()
        cap = settings.brevo_daily_credits
        usage = await get_quota_usage()
        for u in usage:
            login = u["account"]
            if (login, day) in _alerted or cap - u["credits_left"] < settings.quota_alert_threshold * cap:
                continue
            _alerted.add((login, day))
            # Survive restarts: skip if an alert for this account already went out this quota day
            try:
                prior = await db.fetch_one(
                    "SELECT id FROM email_logs WHERE email_type = 'quota_alert' AND status = 'sent' "
                    "AND subject LIKE ? AND sent_at >= ? LIMIT 1",
                    (f"%{login}%", day),
                )
                if prior:
                    continue
            except Exception as exc:
                logger.warning("Quota alert dedup check failed: %s", exc)
            used_pct = round((cap - u["credits_left"]) / cap * 100)
            rows = "".join(
                f"<tr><td style='padding:4px 12px 4px 0;font-family:monospace'>{a['account']}</td>"
                f"<td style='padding:4px 12px 4px 0'><b>{a['credits_left']}</b> / {cap} left</td>"
                f"<td style='padding:4px 0;color:#666'>{'from Brevo' if a['credits_source'] == 'brevo' else 'estimated'}"
                f"{' — OUT' if a['exhausted'] else ''}</td></tr>"
                for a in usage
            )
            html = (
                f"<p>Brevo account <b>{login}</b> has used <b>{used_pct}%</b> of today's {cap} emails "
                f"(<b>{u['credits_left']}</b> left).</p>"
                f"<p>All accounts right now:</p><table>{rows}</table>"
                f"<p>Quota resets at 05:30 IST (00:00 UTC). When an account runs out, sending moves to the "
                f"next account; if every account is out, emails are logged as failed until the reset.</p>"
            )
            await _send_and_log(to, "", f"⚠️ Brevo {login}: {used_pct}% of daily emails used",
                                html, email_type="quota_alert")
    except Exception as exc:
        logger.warning("Quota alert check failed: %s", exc)
    finally:
        _alert_running = False


# Accounts Brevo refused over SMTP (bad key, or a quota refusal if Brevo ever sends one),
# keyed by login -> time of refusal. They're tried last for the next 24h.
_refused_today: dict[str, datetime] = {}


def _is_refused_today(login: str) -> bool:
    at = _refused_today.get(login)
    return at is not None and datetime.now(timezone.utc) - at < _REFUSAL_TTL


async def _ordered_accounts() -> list[tuple[str, str]]:
    """
    Accounts that still have quota, in config order (accounts Brevo recently refused go last).
    Exhausted accounts are left out entirely: mail sent through them is accepted and then dropped,
    so failing the send (logged as 'failed', visible, retryable) is strictly better.
    """
    accounts = _accounts()
    if not accounts:
        return []
    exhausted = {u["account"] for u in await get_quota_usage() if u["exhausted"]}
    usable = [a for a in accounts if a[0] not in exhausted]
    return ([a for a in usable if not _is_refused_today(a[0])]
            + [a for a in usable if _is_refused_today(a[0])])


def _send_sync(to_email: str, to_name: str, subject: str, html_body: str, tag: str | None = None,
               account: tuple[str, str] | None = None) -> None:
    """
    Low-level SMTP send via Brevo relay with strict timeouts and port fallback.
    Runs synchronously — always call via asyncio.to_thread().

    `tag` is echoed back by Brevo on every webhook event (delivered/opened/clicked/
    bounced/...) for this message, which is how we match events back to email_logs rows.
    `account` is the (login, smtp_key) to send with; defaults to the primary account.
    """
    smtp_user, smtp_password = account or (settings.smtp_user, settings.smtp_password)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = f"{to_name} <{to_email}>" if to_name else to_email
    msg["Reply-To"] = settings.smtp_from_email
    if tag:
        msg["X-Mailin-Tag"] = tag

    msg.attach(MIMEText(html_body, "html", "utf-8"))

    ctx = ssl.create_default_context()
    
    # Try configured port first, then fallback to Brevo's alternative ports (2525, 465) if firewall blocks
    ports_to_try = [settings.smtp_port]
    for p in [587, 2525, 465]:
        if p not in ports_to_try:
            ports_to_try.append(p)

    last_err = None
    for port in ports_to_try:
        try:
            if port == 465:
                with smtplib.SMTP_SSL(settings.smtp_host, port, context=ctx, timeout=10) as server:
                    server.login(smtp_user, smtp_password)
                    server.sendmail(settings.smtp_from_email, [to_email], msg.as_string())
            else:
                with smtplib.SMTP(settings.smtp_host, port, timeout=10) as server:
                    server.ehlo()
                    server.starttls(context=ctx)
                    server.login(smtp_user, smtp_password)
                    server.sendmail(settings.smtp_from_email, [to_email], msg.as_string())
            logger.info("Email sent to %s via port %s (account %s) | subject: %s", to_email, port, smtp_user, subject)
            return
        except smtplib.SMTPResponseException as e:
            if isinstance(e, smtplib.SMTPConnectError):
                logger.warning("SMTP connect failed on port %s: %s", port, e)
                last_err = e
                continue
            # Auth failure / quota exceeded / rejected message: another port won't help
            logger.warning("SMTP rejected by account %s: %s", smtp_user, e)
            raise
        except Exception as e:
            logger.warning("SMTP connect failed on port %s: %s", port, e)
            last_err = e

    if last_err:
        raise last_err



async def _send_ex(to_email: str, to_name: str, subject: str, html_body: str,
                   tag: str | None = None) -> tuple[bool, str | None]:
    """
    Async wrapper around _send_sync with multi-account failover.
    Returns (success, login of the account that sent it). Never raises.
    """
    if not settings.email_enabled:
        logger.info("[Email disabled] Would send '%s' to %s", subject, to_email)
        return True, None
    if not _accounts():
        logger.warning("SMTP credentials not configured — skipping email to %s", to_email)
        return False, None
    attempted = False
    for account in await _ordered_accounts():
        login = account[0]
        # Re-check and reserve a credit with no await in between, so concurrent sends can't all
        # spend the same last credit.
        left = _credits_left(login)
        if left is not None and left <= 0:
            continue
        attempted = True
        _adjust_credits(login, -1)
        try:
            await asyncio.to_thread(_send_sync, to_email, to_name, subject, html_body, tag, account)
            _schedule_quota_alert_check()
            return True, login
        except smtplib.SMTPRecipientsRefused as exc:
            _adjust_credits(login, +1)
            # This recipient is the problem, not the account — another account won't help
            logger.error("Recipient %s refused via account %s: %s", to_email, login, exc)
            return False, None
        except smtplib.SMTPResponseException as exc:
            _adjust_credits(login, +1)
            if not isinstance(exc, smtplib.SMTPConnectError):
                # Brevo refused this account (quota hit / bad key) — deprioritise it until the daily reset
                _refused_today[login] = datetime.now(timezone.utc)
            logger.error("Failed to send email to %s via account %s: %s", to_email, login, exc)
        except Exception as exc:
            _adjust_credits(login, +1)
            logger.error("Failed to send email to %s via account %s: %s", to_email, login, exc)
    if not attempted:
        logger.error("Not sending email to %s: every Brevo account is out of today's quota "
                     "(resets 00:00 UTC). Logged as failed so it can be resent.", to_email)
    return False, None


async def _send(to_email: str, to_name: str, subject: str, html_body: str, tag: str | None = None) -> bool:
    """Returns True on success, False on failure (never raises)."""
    ok, _ = await _send_ex(to_email, to_name, subject, html_body, tag)
    return ok


async def _send_and_log(
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,
    email_type: str = "other",
    student_id: int | None = None,
    batch_id:   int | None = None,
) -> bool:
    """
    Sends an email and records it in email_logs regardless of success/failure.
    Deduplicates non-OTP emails (welcome, certificate_ready, task_assigned) to prevent duplicate emails.
    """
    # Deduplication guard for single-event emails
    if email_type in ("certificate_ready", "welcome", "task_assigned"):
        try:
            from db.database import db
            query = """SELECT id FROM email_logs 
                       WHERE recipient_email = ? AND email_type = ? AND status = 'sent'"""
            params = [to_email, email_type]
            if student_id is not None:
                query += " AND student_id = ?"
                params.append(student_id)
            if batch_id is not None:
                query += " AND batch_id = ?"
                params.append(batch_id)
            query += " LIMIT 1"

            existing = await db.fetch_one(query, tuple(params))
            if existing:
                logger.info("Skipping duplicate %s email to %s (already sent).", email_type, to_email)
                return True
        except Exception as dedup_exc:
            logger.warning("Email deduplication check warning: %s", dedup_exc)

    # Insert a pending row first so we have an id to tag the outgoing message with —
    # Brevo echoes this tag back on every delivery/open/click/bounce webhook event.
    from db.database import db
    log_id = None
    try:
        log_id = await db.insert(
            """INSERT INTO email_logs
               (recipient_email, recipient_name, email_type, subject, student_id, batch_id, status, body)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (to_email, to_name, email_type, subject, student_id, batch_id, html_body),
        )
    except Exception as log_exc:
        logger.warning("Failed to pre-log email to DB: %s", log_exc)

    tag = f"log{log_id}" if log_id else None
    success, account = await _send_ex(to_email, to_name, subject, html_body, tag)

    try:
        if log_id:
            await db.execute(
                "UPDATE email_logs SET status = ?, message_tag = ?, smtp_account = ? WHERE id = ?",
                ("sent" if success else "failed", tag, account, log_id),
            )
        else:
            # Pre-log insert failed — fall back to a single post-send insert (no tracking tag)
            await db.insert(
                """INSERT INTO email_logs
                   (recipient_email, recipient_name, email_type, subject, student_id, batch_id, status, body, smtp_account)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (to_email, to_name, email_type, subject, student_id, batch_id,
                 "sent" if success else "failed", html_body, account),
            )
    except Exception as log_exc:
        logger.warning("Failed to log email to DB: %s", log_exc)
    return success

# ── Activation / engagement emails (additive; never used by transactional flows) ──

_ACTIVATION_TEMPLATES = {
    "onboarding_no_login": "activation_onboarding.html",
    "login_no_first_task": "activation_first_task.html",
    "milestone_stall": "activation_milestone.html",
    "inactivity": "activation_inactive.html",
    "internship_completed": "activation_completed.html",
}


def _activation_subject(kind: str, step: int, ctx: dict) -> str:
    ft, ms, dl = ctx.get("ft") or {}, ctx.get("ms") or {}, ctx.get("domain_label", "")
    if kind == "onboarding_no_login":
        return ["Your SkillMe internship is ready: here is how to log in",
                "Your first SkillMe task is waiting",
                "Your SkillMe internship window is running"][min(step, 3) - 1]
    if kind == "login_no_first_task":
        t = ft.get("title", "your first task")
        return f"Start your first {dl} task: {t}" if step <= 1 else f"Your first task takes {str(ft.get('time_label', 'a couple of hours')).lower()}"
    if kind == "milestone_stall":
        return f"Week {ms.get('last_approved')} approved. Week {ms.get('next_week')} is next"
    if kind == "inactivity":
        return f"Pick up where you left off: Week {ms.get('next_week')}"
    return "You completed your SkillMe internship"


def render_activation_email(kind: str, step: int = 1, **ctx) -> tuple[str, str]:
    """Pure render (no sending, no logging). Returns (subject, html)."""
    ctx["step"] = step
    html = _render(_ACTIVATION_TEMPLATES[kind], **ctx)
    return _activation_subject(kind, step, ctx), html


# ── Domain label helper ───────────────────────────────────────────────────────

def _domain_label(domain: str) -> str:
    """Convert domain slug/value to human-readable label."""
    mapping = {
        # Original domains
        "web-dev": "Full Stack Engineer",
        "Web Development": "Full Stack Engineer",
        "Full Stack Engineer": "Full Stack Engineer",
        "python": "Python",
        "Python": "Python",
        "ml": "Machine Learning",
        "Machine Learning": "Machine Learning",
        "devops": "DevOps / Cloud",
        "DevOps / CI-CD": "DevOps / CI-CD",
        "mobile": "Mobile Development",
        "flutter": "App Developer",
        "Flutter / Mobile": "App Developer",
        "App Developer": "App Developer",
        "ui-ux": "UI/UX Design",
        "uiux": "UI/UX Design",
        "UI/UX Design": "UI/UX Design",
        # New domains — slug and display value mappings
        "react": "Frontend Engineer",
        "React / Next.js": "Frontend Engineer",
        "Frontend Engineer": "Frontend Engineer",
        "node": "Backend Engineer",
        "nodejs": "Backend Engineer",
        "Node.js / Express": "Backend Engineer",
        "Backend Engineer": "Backend Engineer",
        "java": "Java / Spring Boot",
        "Java / Spring Boot": "Java / Spring Boot",
        "datascience": "Data Science",
        "data-science": "Data Science",
        "Data Science": "Data Science",
        "cpp": "C/C++ / DSA",
        "C/C++ / DSA": "C/C++ / DSA",
        "cyber": "Cybersecurity",
        "cybersecurity": "Cybersecurity",
        "Cybersecurity": "Cybersecurity",
        "cloud": "Cloud / AWS",
        "Cloud / AWS": "Cloud / AWS",
        "dsa": "DSA / Competitive Programming",
        "DSA / Competitive": "DSA / Competitive Programming",
        "blockchain": "Blockchain / Web3",
        "Blockchain / Web3": "Blockchain / Web3",
        "android": "Android / Kotlin",
        "Android / Kotlin": "Android / Kotlin",
        "sql": "SQL / Databases",
        "SQL / Databases": "SQL / Databases",
        "genai": "Generative AI",
        "Generative AI": "Generative AI",
        # Newly added domains
        "ai-engineer": "AI Engineer",
        "AI Engineer": "AI Engineer",
        "fde": "Forward Deployed Engineer",
        "Forward Deployed Engineer": "Forward Deployed Engineer",
        "sde": "SDE / SWE",
        "swe": "SDE / SWE",
        "SDE": "SDE / SWE",
        "SWE": "SDE / SWE",
        "ai-pm": "AI Product Management",
        "AI Product Management": "AI Product Management",
        "qa": "Software Quality",
        "Software Quality": "Software Quality",
    }
    return mapping.get(domain, domain.replace("-", " ").title())



# ── Public API ────────────────────────────────────────────────────────────────

class EmailService:
    """High-level email sending service for SkillMe lifecycle events."""

    # 1. Application received
    async def send_application_confirmation(
        self,
        first_name: str,
        last_name: str,
        email: str,
        domain: str,
    ) -> bool:
        html = _render(
            "application_received.html",
            first_name=first_name,
            last_name=last_name,
            email=email,
            domain_label=_domain_label(domain),
        )
        return await _send_and_log(
            email,
            f"{first_name} {last_name}",
            "✅ We received your SkillMe application!",
            html,
            email_type="application_confirmation",
        )

    # 2. Shortlisted
    async def send_shortlist_notification(
        self,
        first_name: str,
        last_name: str,
        email: str,
        domain: str,
    ) -> bool:
        html = _render(
            "shortlisted.html",
            first_name=first_name,
            last_name=last_name,
            domain_label=_domain_label(domain),
        )
        return await _send_and_log(
            email,
            f"{first_name} {last_name}",
            "🎉 You've been shortlisted for SkillMe!",
            html,
            email_type="shortlisted",
        )

    # 3. Offer letter / enrollment
    async def send_offer_letter(
        self,
        first_name: str,
        last_name: str,
        email: str,
        domain: str,
        joining_date: str | None = None,
        repo_url: str | None = None,
        github_username: str | None = None,
        student_id: int | None = None,
    ) -> bool:
        if not joining_date:
            joining_date = datetime.utcnow().strftime("%d %B %Y")
        # Signed reference so the letter's QR / links can be verified by a college.
        from services.auth_service import offer_ref
        offer_query = f"&student_id={student_id}&ref={offer_ref(student_id)}" if student_id else ""
        # Build a filtered issues URL that shows ONLY this student's issues
        issues_url = None
        if repo_url and github_username:
            issues_url = f"{repo_url}/issues?assignee={github_username}"
        html = _render(
            "offer_letter.html",
            first_name=first_name,
            last_name=last_name,
            domain_label=_domain_label(domain),
            joining_date=joining_date,
            repo_url=repo_url or "",
            issues_url=issues_url or "",
            github_username=github_username or "",
            dashboard_url=f"{settings.frontend_url}/dashboard.html",
            offer_query=offer_query,
        )
        return await _send_and_log(
            email,
            f"{first_name} {last_name}",
            f"🚀 Your SkillMe Offer Letter — {_domain_label(domain)} Program",
            html,
            email_type="offer_letter",
        )

    # 5. Certificate ready
    async def send_certificate_ready(
        self,
        first_name: str,
        last_name: str,
        email: str,
        domain: str,
        cert_id: str,
        issued_date: str | None = None,
    ) -> bool:
        if not issued_date:
            issued_date = datetime.utcnow().strftime("%d %B %Y")
        _base = "https://skill-me-intern.in"
        certificate_url = f"{_base}/certificate.html?cert_id={cert_id}"
        verify_url = f"{_base}/verify.html?cert_id={cert_id}"
        lor_url = f"{_base}/lor.html?cert_id={cert_id}"
        html = _render(
            "certificate_ready.html",
            first_name=first_name,
            last_name=last_name,
            domain_label=_domain_label(domain),
            cert_id=cert_id,
            issued_date=issued_date,
            certificate_url=certificate_url,
            verify_url=verify_url,
            lor_url=lor_url,
        )
        return await _send_and_log(
            email,
            f"{first_name} {last_name}",
            f"🏆 Your Certificate & Letter of Recommendation are Ready — {cert_id}",
            html,
            email_type="certificate_ready",
        )

    # Stipend seat confirmed (student submitted their certificate ID on the dashboard)
    async def send_stipend_entry_confirmed(
        self,
        first_name: str,
        last_name: str,
        email: str,
        domain: str,
        cert_id: str,
    ) -> bool:
        html = _render(
            "stipend_entry_confirmed.html",
            first_name=first_name,
            last_name=last_name,
            domain_label=_domain_label(domain),
            cert_id=cert_id,
            entered_date=datetime.utcnow().strftime("%d %B %Y"),
        )
        return await _send_and_log(
            email,
            f"{first_name} {last_name}",
            "Your seat in the $100 top-performer stipend is confirmed",
            html,
            email_type="stipend_entry_confirmed",
        )

    # Follow-ups that stop by themselves once the student acts (credential_reminder_service).
    # No deadlines: they remind, they never pressure.
    async def send_credentials_waiting(
        self,
        first_name: str,
        last_name: str,
        email: str,
        domain: str,
        step: int,
        student_id: int | None = None,
        batch_id: int | None = None,
    ) -> bool:
        from services.engagement_service import unsubscribe_url
        subjects = {
            1: f"{first_name}, your credentials are ready to issue",
            2: f"Your {_domain_label(domain)} certificate is still waiting, {first_name}",
            3: "One last note about your SkillMe credentials",
        }
        html = _render(
            "credentials_waiting.html",
            first_name=first_name,
            last_name=last_name,
            domain_label=_domain_label(domain),
            step=step,
            last=step >= 3,
            cta_url=f"{settings.frontend_url}/dashboard.html?from=cred_email#checkout",
            unsubscribe_url=unsubscribe_url(email),
        )
        return await _send_and_log(
            email,
            f"{first_name} {last_name}",
            subjects.get(step, subjects[1]),
            html,
            email_type="credentials_waiting",
            student_id=student_id,
            batch_id=batch_id,
        )

    async def send_stipend_seat_reminder(
        self,
        first_name: str,
        last_name: str,
        email: str,
        domain: str,
        cert_id: str,
        step: int,
        student_id: int | None = None,
        batch_id: int | None = None,
    ) -> bool:
        from services.engagement_service import unsubscribe_url
        subjects = {
            1: f"{first_name}, your stipend seat is still open",
            2: "Your seat in the $100 stipend is waiting for you",
            3: "One last note about your stipend seat",
        }
        html = _render(
            "stipend_seat_reminder.html",
            first_name=first_name,
            last_name=last_name,
            domain_label=_domain_label(domain),
            cert_id=cert_id,
            step=step,
            last=step >= 3,
            cta_url=f"{settings.frontend_url}/dashboard.html?from=stipend_email#stipend",
            unsubscribe_url=unsubscribe_url(email),
        )
        return await _send_and_log(
            email,
            f"{first_name} {last_name}",
            subjects.get(step, subjects[1]),
            html,
            email_type="stipend_seat_reminder",
            student_id=student_id,
            batch_id=batch_id,
        )

    # Announcement: GitHub PR -> LinkedIn submission flow change
    async def send_submission_flow_update(
        self,
        first_name: str,
        last_name: str,
        email: str,
        domain: str,
    ) -> bool:
        html = _render(
            "submission_flow_update.html",
            first_name=first_name,
            last_name=last_name,
            domain_label=_domain_label(domain),
        )
        return await _send_and_log(
            email,
            f"{first_name} {last_name}",
            "📢 Important Update: How You Submit Your Weekly Tasks Has Changed",
            html,
            email_type="submission_flow_update",
        )

    # 4. Weekly task approved
    async def send_task_approved(
        self,
        first_name: str,
        last_name: str,
        email: str,
        domain: str,
        week: int,
        score: int,
        admin_note: str | None = None,
    ) -> bool:
        html = _render(
            "task_approved.html",
            first_name=first_name,
            last_name=last_name,
            domain_label=_domain_label(domain),
            week=week,
            score=score,
            admin_note=admin_note,
        )
        return await _send_and_log(
            email,
            f"{first_name} {last_name}",
            f"🎉 Week {week} Task Approved!",
            html,
            email_type="task_approved",
        )

    # Weekly task rejected — student can fix and resubmit
    async def send_task_rejected(
        self,
        first_name: str,
        last_name: str,
        email: str,
        domain: str,
        week: int,
        admin_note: str | None = None,
    ) -> bool:
        html = _render(
            "task_rejected.html",
            first_name=first_name,
            last_name=last_name,
            domain_label=_domain_label(domain),
            week=week,
            admin_note=admin_note,
        )
        return await _send_and_log(
            email,
            f"{first_name} {last_name}",
            f"Week {week} Task Needs Changes — Please Resubmit",
            html,
            email_type="task_rejected",
        )

    # Weekly task submitted — automatic per-task feedback (see feedback_service)
    async def send_submission_feedback(
        self,
        first_name: str,
        last_name: str,
        email: str,
        domain: str,
        week: int,
        feedback: dict,
        student_id: int | None = None,
        batch_id: int | None = None,
    ) -> bool:
        html = _render(
            "submission_feedback.html",
            first_name=first_name,
            last_name=last_name,
            domain_label=_domain_label(domain),
            week=week,
            **feedback,
        )
        return await _send_and_log(
            email,
            f"{first_name} {last_name}",
            f"Week {week} submission received — {_domain_label(domain)}",
            html,
            email_type="submission_feedback",
            student_id=student_id,
            batch_id=batch_id,
        )

    # Urgent request fulfilled
    async def send_urgent_request_fulfilled(
        self,
        first_name: str,
        last_name: str,
        email: str,
        domain: str,
        request_type: str,
    ) -> bool:
        html = _render(
            "urgent_request_fulfilled.html",
            first_name=first_name,
            last_name=last_name,
            domain_label=_domain_label(domain),
            request_type=request_type,
        )
        return await _send_and_log(
            email,
            f"{first_name} {last_name}",
            "🚀 Your Urgent Request Has Been Fulfilled",
            html,
            email_type="urgent_request_fulfilled",
        )

    # Task inactivity reminder
    async def send_task_reminder(
        self,
        first_name: str,
        last_name: str,
        email: str,
        domain: str,
        week_due: int,
        days_inactive: int,
        completed_tasks: int,
        student_id: int | None = None,
        batch_id: int | None = None,
    ) -> bool:
        html = _render(
            "task_reminder.html",
            first_name=first_name,
            last_name=last_name,
            domain_label=_domain_label(domain),
            week_due=week_due,
            days_inactive=days_inactive,
            completed_tasks=completed_tasks,
        )
        return await _send_and_log(
            email,
            f"{first_name} {last_name}",
            f"⏰ You're falling behind — Week {week_due} task is overdue",
            html,
            email_type="task_reminder",
            student_id=student_id,
            batch_id=batch_id,
        )

    # Test utility
    async def send_activation(self, kind: str, step: int, to_email: str, to_name: str,
                              student_id: int, batch_id: int | None, **ctx) -> bool:
        """Send one activation/engagement email. Logged as email_type 'activation_<kind>'."""
        subject, html = render_activation_email(kind, step, **ctx)
        return await _send_and_log(to_email, to_name, subject, html,
                                   email_type=f"activation_{kind}", student_id=student_id, batch_id=batch_id)

    async def send_test_email(self, to_email: str) -> bool:
        """Send a test email to verify SMTP configuration."""
        html = _render(
            "application_received.html",
            first_name="Test",
            last_name="User",
            email=to_email,
            domain_label="Web Development",
        )
        return await _send_and_log(
            to_email,
            "Test User",
            "🧪 SkillMe Email Test — SMTP Working!",
            html,
            email_type="test",
        )


# Singleton instance
email_service = EmailService()
