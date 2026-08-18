"""
SkillMe — Email Service (Brevo SMTP relay)
Sends branded HTML emails for key student lifecycle events.

All public methods are async and never raise — email failures are logged
but never propagate to crash the calling API endpoint.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from datetime import datetime, timedelta
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

def _send_sync(to_email: str, to_name: str, subject: str, html_body: str) -> None:
    """
    Low-level SMTP send via Brevo relay with strict timeouts and port fallback.
    Runs synchronously — always call via asyncio.to_thread().
    """
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = f"{to_name} <{to_email}>" if to_name else to_email
    msg["Reply-To"] = settings.smtp_from_email

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
                    server.login(settings.smtp_user, settings.smtp_password)
                    server.sendmail(settings.smtp_from_email, [to_email], msg.as_string())
            else:
                with smtplib.SMTP(settings.smtp_host, port, timeout=10) as server:
                    server.ehlo()
                    server.starttls(context=ctx)
                    server.login(settings.smtp_user, settings.smtp_password)
                    server.sendmail(settings.smtp_from_email, [to_email], msg.as_string())
            logger.info("Email sent to %s via port %s | subject: %s", to_email, port, subject)
            return
        except Exception as e:
            logger.warning("SMTP connect failed on port %s: %s", port, e)
            last_err = e

    if last_err:
        raise last_err



async def _send(to_email: str, to_name: str, subject: str, html_body: str) -> bool:
    """
    Async wrapper around _send_sync.
    Returns True on success, False on failure (never raises).
    """
    if not settings.email_enabled:
        logger.info("[Email disabled] Would send '%s' to %s", subject, to_email)
        return True
    if not settings.smtp_user or not settings.smtp_password:
        logger.warning("SMTP credentials not configured — skipping email to %s", to_email)
        return False
    try:
        await asyncio.to_thread(_send_sync, to_email, to_name, subject, html_body)
        return True
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to_email, exc)
        return False


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

    success = await _send(to_email, to_name, subject, html_body)
    # Log to DB (best-effort — never crash the caller)
    try:
        from db.database import db
        await db.insert(
            """INSERT INTO email_logs
               (recipient_email, recipient_name, email_type, subject, student_id, batch_id, status, body)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (to_email, to_name, email_type, subject, student_id, batch_id,
             "sent" if success else "failed", html_body),
        )
    except Exception as log_exc:
        logger.warning("Failed to log email to DB: %s", log_exc)
    return success

# ── Domain label helper ───────────────────────────────────────────────────────

def _domain_label(domain: str) -> str:
    """Convert domain slug/value to human-readable label."""
    mapping = {
        # Original domains
        "web-dev": "Web Development",
        "Web Development": "Web Development",
        "python": "Python",
        "Python": "Python",
        "ml": "Machine Learning",
        "Machine Learning": "Machine Learning",
        "devops": "DevOps / Cloud",
        "DevOps / CI-CD": "DevOps / CI-CD",
        "mobile": "Mobile Development",
        "flutter": "Flutter / Mobile",
        "Flutter / Mobile": "Flutter / Mobile",
        "ui-ux": "UI/UX Design",
        "uiux": "UI/UX Design",
        "UI/UX Design": "UI/UX Design",
        # New domains — slug and display value mappings
        "react": "React / Next.js",
        "React / Next.js": "React / Next.js",
        "node": "Node.js / Express",
        "Node.js / Express": "Node.js / Express",
        "java": "Java / Spring Boot",
        "Java / Spring Boot": "Java / Spring Boot",
        "datascience": "Data Science",
        "data-science": "Data Science",
        "Data Science": "Data Science",
        "cpp": "C/C++ / DSA",
        "C/C++ / DSA": "C/C++ / DSA",
        "cyber": "Cybersecurity",
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
        github_username: str = "",
    ) -> bool:
        html = _render(
            "application_received.html",
            first_name=first_name,
            last_name=last_name,
            email=email,
            domain_label=_domain_label(domain),
            github_username=github_username,
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
        batch_number: int,
        joining_date: str | None = None,
        repo_url: str | None = None,
        github_username: str | None = None,
    ) -> bool:
        if not joining_date:
            joining_date = datetime.utcnow().strftime("%d %B %Y")
        # Build a filtered issues URL that shows ONLY this student's issues
        issues_url = None
        if repo_url and github_username:
            issues_url = f"{repo_url}/issues?assignee={github_username}"
        html = _render(
            "offer_letter.html",
            first_name=first_name,
            last_name=last_name,
            domain_label=_domain_label(domain),
            batch_number=batch_number,
            joining_date=joining_date,
            repo_url=repo_url or "",
            issues_url=issues_url or "",
            github_username=github_username or "",
            dashboard_url=f"{settings.frontend_url}/dashboard.html",
        )
        return await _send_and_log(
            email,
            f"{first_name} {last_name}",
            f"🚀 Your SkillMe Offer Letter — {_domain_label(domain)} Program",
            html,
            email_type="offer_letter",
        )

    # 4. Weekly tasks assigned
    async def send_weekly_tasks_notification(
        self,
        first_name: str,
        last_name: str,
        email: str,
        domain: str,
        batch_number: int,
        week_number: int,
        tasks: list[dict],
        repo_url: str | None = None,
        github_username: str | None = None,
    ) -> bool:
        deadline = (datetime.utcnow() + timedelta(days=7)).strftime("%d %B %Y")
        # Build filtered issues URL for this student only
        issues_url = None
        if repo_url and github_username:
            issues_url = f"{repo_url}/issues?assignee={github_username}"
        html = _render(
            "weekly_tasks.html",
            first_name=first_name,
            last_name=last_name,
            domain_label=_domain_label(domain),
            batch_number=batch_number,
            week_number=week_number,
            tasks=tasks,
            task_count=len(tasks),
            deadline=deadline,
            repo_url=repo_url or "",
            issues_url=issues_url or "",
            github_username=github_username or "",
            dashboard_url=f"{settings.frontend_url}/dashboard.html",
        )
        return await _send_and_log(
            email,
            f"{first_name} {last_name}",
            f"💻 Week {week_number} Tasks Are Live — SkillMe {_domain_label(domain)}",
            html,
            email_type="weekly_tasks",
        )

    # 5. Certificate ready
    async def send_certificate_ready(
        self,
        first_name: str,
        last_name: str,
        email: str,
        domain: str,
        batch_number: int,
        cert_id: str,
        issued_date: str | None = None,
    ) -> bool:
        if not issued_date:
            issued_date = datetime.utcnow().strftime("%d %B %Y")
        _base = "https://skill-me-intern.in"
        certificate_url = f"{_base}/certificate.html?email={email}"
        verify_url = f"{_base}/certificate.html?cert_id={cert_id}"
        lor_url = f"{_base}/lor.html?cert_id={cert_id}"
        html = _render(
            "certificate_ready.html",
            first_name=first_name,
            last_name=last_name,
            domain_label=_domain_label(domain),
            batch_number=batch_number,
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

    # 6. GitHub invite reminder (for students with pending collaborator status)
    async def send_github_invite_reminder(
        self,
        first_name: str,
        last_name: str,
        email: str,
        domain: str,
        repo_url: str | None = None,
        github_email: str | None = None,
        student_id: int | None = None,
    ) -> bool:
        html = _render(
            "github_invite_reminder.html",
            first_name=first_name,
            last_name=last_name,
            domain_label=_domain_label(domain),
            repo_url=repo_url or "",
            github_email=github_email or email,
        )
        return await _send_and_log(
            email,
            f"{first_name} {last_name}",
            "⚠️ Action Required: Accept Your GitHub Invite to Start Your Internship",
            html,
            email_type="github_invite_reminder",
            student_id=student_id,
        )

    # Test utility
    async def send_test_email(self, to_email: str) -> bool:
        """Send a test email to verify SMTP configuration."""
        html = _render(
            "application_received.html",
            first_name="Test",
            last_name="User",
            email=to_email,
            domain_label="Web Development",
            github_username="testuser",
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
