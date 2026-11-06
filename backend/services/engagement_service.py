"""
SkillMe — Engagement engine (reminders around the existing workflows).

Safety model
  * mode 'off'      -> nothing is planned or sent.
  * mode 'dry_run'  -> candidates are evaluated and recorded as status 'dry_run'; no email leaves.
  * mode 'live'     -> sends, but ONLY if settings.engagement_live_allowed is true (env interlock).
Every decision is re-evaluated from fresh data at send time, so a student who progresses
between ticks stops receiving the old reminder automatically. Duplicate deliveries are
impossible: each reminder owns a UNIQUE dedupe_key and is claimed with INSERT OR IGNORE
before anything is sent.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta

from config import settings
from db.database import db
from services import activation_content as content
from services import activation_service as seg
from services import email_service as es
from services.activation_events import record_event

logger = logging.getLogger("skillme.engagement")

TRIGGERS = ["onboarding_no_login", "login_no_first_task", "milestone_stall", "inactivity", "internship_completed"]
TRIGGER_LABELS = {
    "onboarding_no_login": "No login after enrollment",
    "login_no_first_task": "Login without first task",
    "milestone_stall": "No progress after approved milestone",
    "inactivity": "Inactive for N days",
    "internship_completed": "Internship completed",
}
STAGE_TO_TRIGGER = {
    "never_logged_in": "onboarding_no_login",
    "no_first_task": "login_no_first_task",
    "stuck_week_1": "milestone_stall",
    "stuck_week_2": "milestone_stall",
    "stuck_week_3": "milestone_stall",
    "completed": "internship_completed",
}
SEND_THROTTLE_SECONDS = 1.0


# ── Mode ─────────────────────────────────────────────────────────────────────

def effective_mode(cfg: dict) -> tuple[str, str | None]:
    """(mode actually used, note). 'live' silently degrades to dry_run without the env interlock."""
    mode = cfg.get("mode", "off")
    if mode == "live" and not settings.engagement_live_allowed:
        return "dry_run", "Live is selected but ENGAGEMENT_LIVE_ALLOWED is not enabled on the server, so nothing will be sent."
    return (mode if mode in ("off", "dry_run", "live") else "off"), None


# ── Signed links ─────────────────────────────────────────────────────────────

def _sig(msg: str) -> str:
    return hmac.new(settings.jwt_secret_key.encode(), msg.encode(), hashlib.sha256).hexdigest()[:24]


def unsubscribe_sig(email: str) -> str:
    return _sig(f"unsub:{(email or '').strip().lower()}")


def unsubscribe_valid(email: str, sig: str) -> bool:
    return hmac.compare_digest(unsubscribe_sig(email), (sig or "").strip().lower())


def _base() -> str:
    return (settings.backend_url or "").rstrip("/")


def unsubscribe_url(email: str) -> str:
    from urllib.parse import quote
    return f"{_base()}/api/engagement/unsubscribe?e={quote(email.lower())}&s={unsubscribe_sig(email)}"


def click_url(token: str) -> str:
    return f"{_base()}/r/{token}"


# ── Suppression and caps ─────────────────────────────────────────────────────

async def suppression_reason(email: str) -> str | None:
    em = (email or "").strip().lower()
    pref = await db.fetch_one(
        "SELECT reminders_opt_out, unsubscribed_at FROM notification_preferences WHERE email = ?", (em,))
    if pref and (pref["reminders_opt_out"] or pref["unsubscribed_at"]):
        return "opted_out"
    bad = await db.fetch_one(
        """SELECT bounce_type, bounced_at, spam_reported_at, unsubscribed_at FROM email_logs
           WHERE lower(recipient_email) = ?
             AND (spam_reported_at IS NOT NULL OR unsubscribed_at IS NOT NULL
                  OR (bounced_at IS NOT NULL AND lower(COALESCE(bounce_type, '')) NOT LIKE '%soft%'))
           LIMIT 1""", (em,))
    if bad:
        if bad["spam_reported_at"]:
            return "spam_reported"
        if bad["unsubscribed_at"]:
            return "unsubscribed"
        return "bounced"
    return None


async def recently_emailed(email: str, trigger: str, hours: int) -> bool:
    """Frequency cap across triggers and the legacy task_reminder cron.
    Emails of the SAME trigger are exempt: their own step delays already space them out."""
    row = await db.fetch_one(
        """SELECT 1 AS x FROM email_logs
           WHERE lower(recipient_email) = ? AND status = 'sent'
             AND (email_type LIKE 'activation_%' OR email_type = 'task_reminder')
             AND email_type != ?
             AND sent_at > datetime('now', ?)
           LIMIT 1""", (email.lower(), f"activation_{trigger}", f"-{int(hours)} hours"))
    return bool(row)


# ── Candidate planning ───────────────────────────────────────────────────────

async def _steps_done(student_id: int, batch_id, trigger: str, include_dry: bool) -> int:
    sts = ("sent", "failed", "dry_run") if include_dry else ("sent", "failed")
    marks = ",".join("?" for _ in sts)
    row = await db.fetch_one(
        f"""SELECT COALESCE(MAX(step), 0) AS n FROM engagement_reminders
            WHERE student_id = ? AND COALESCE(batch_id, 0) = COALESCE(?, 0) AND trigger_key = ?
              AND status IN ({marks}) AND dedupe_key NOT LIKE 'manual:%'""",
        (student_id, batch_id, trigger, *sts))
    return int(row["n"] or 0)


def _base_time(r: dict, trigger: str, cfg: dict) -> datetime | None:
    if trigger == "onboarding_no_login":
        return r["enrolled_ts"]
    if trigger == "login_no_first_task":
        return r["first_login_ts"]
    if trigger == "milestone_stall":
        return r["last_approved_ts"]
    if trigger == "inactivity":
        return r["last_activity_ts"] + timedelta(days=cfg["inactive_days"]) if r["last_activity_ts"] else None
    return r["last_approved_ts"] if trigger == "internship_completed" else None


def applies(r: dict, trigger: str) -> bool:
    """Does this trigger still apply to the student RIGHT NOW? (auto-stop lives here)"""
    st = r["stage"]
    if trigger == "onboarding_no_login":
        return st == "never_logged_in"
    if trigger == "login_no_first_task":
        return st == "no_first_task"
    if trigger == "milestone_stall":
        # Next week already submitted (awaiting review) -> nothing to nudge
        return st in ("stuck_week_1", "stuck_week_2", "stuck_week_3") and \
            (max(r["weeks_reached"] or [0]) <= r["last_approved_week"])
    if trigger == "inactivity":
        return bool(r["inactive"]) and st != "completed"
    if trigger == "internship_completed":
        return st == "completed"
    return False


async def plan_automatic(rows: list[dict], cfg: dict, now: datetime, include_dry: bool) -> list[dict]:
    """Next due step per student per enabled trigger. Pure read."""
    out = []
    for r in rows:
        for trig in TRIGGERS:
            tc = cfg["triggers"].get(trig) or {}
            if not tc.get("enabled") or not applies(r, trig):
                continue
            base = _base_time(r, trig, cfg)
            if not base:
                continue
            delays = tc.get("delays_h") or [0]
            done = await _steps_done(r["id"], r["batch_id"], trig, include_dry)
            if trig == "inactivity":
                cooldown = timedelta(days=tc.get("cooldown_days", 7))
                last = await db.fetch_one(
                    """SELECT MAX(created_at) AS t FROM engagement_reminders WHERE student_id = ? AND trigger_key = ?
                       AND status IN ('sent','failed','dry_run')""", (r["id"], trig))
                last_t = seg.an.parse_ts(last["t"]) if last and last["t"] else None
                if last_t and now - last_t < cooldown:
                    continue
                step = done + 1
                due = base
            else:
                if done >= len(delays):
                    continue
                step = done + 1
                due = base + timedelta(hours=delays[step - 1])
            if now < due:
                continue
            out.append({"row": r, "trigger": trig, "step": step, "due": due})
    return out


def recommended_trigger(r: dict) -> str | None:
    t = STAGE_TO_TRIGGER.get(r["stage"])
    return t if t and applies(r, t) else None


# ── Rendering ────────────────────────────────────────────────────────────────

def _context(r: dict, trigger: str, token: str | None = None, now: datetime | None = None) -> dict:
    first = (r["name"] or "there").split(" ")[0]
    ctx = {
        "first_name": first, "email": r["email"], "domain_label": r["domain_label"],
        "cta_url": click_url(token) if token else f"{settings.frontend_url}/dashboard",
        "unsubscribe_url": unsubscribe_url(r["email"]),
    }
    if trigger in ("onboarding_no_login", "login_no_first_task"):
        ctx["ft"] = content.first_task_content(r["domain_key"], r["id"])
    if trigger in ("milestone_stall", "inactivity"):
        nxt = max(r["last_approved_week"] + 1, 1)
        nxt = min(nxt, 4)
        wk = content.week_content(r["domain_key"], r["id"], nxt)
        ctx["ms"] = {"last_approved": r["last_approved_week"], "next_week": nxt, "next_title": wk["title"],
                     "time_label": wk["time_label"], "remaining": max(4 - r["last_approved_week"], 0),
                     "deliverables": wk["deliverables"]}
        ctx["days_inactive"] = r["days_idle"] or 0
    return ctx


def preview(r: dict, trigger: str, step: int = 1) -> dict:
    subject, html = es.render_activation_email(trigger, step, **_context(r, trigger, token="preview"))
    return {"subject": subject, "html": html}


# ── Sending pipeline ─────────────────────────────────────────────────────────

def _dedupe(trigger: str, step: int, r: dict, manual: bool, now: datetime) -> str:
    base = f"{trigger}:{step}:{r['id']}:{r['batch_id'] or 0}"
    if trigger == "milestone_stall":
        base += f":w{r['last_approved_week']}"
    return f"manual:{now:%Y%m%d}:{base}" if manual else f"reminder:{base}"


async def _write_row(r, trigger, step, status, reason, key, token=None) -> bool:
    """INSERT OR IGNORE; True if this call created the row."""
    if await db.fetch_one("SELECT 1 AS x FROM engagement_reminders WHERE dedupe_key = ?", (key,)):
        return False
    await db.execute(
        """INSERT OR IGNORE INTO engagement_reminders
           (student_id, batch_id, trigger_key, step, segment, status, reason, token, dedupe_key)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (r["id"], r["batch_id"], trigger, step, r["stage"], status, reason, token, key))
    mine = await db.fetch_one("SELECT token FROM engagement_reminders WHERE dedupe_key = ?", (key,))
    return bool(mine) and (token is None or mine["token"] == token)


async def process_one(r: dict, trigger: str, step: int, mode: str, cfg: dict, *,
                      manual: bool = False, override_ended: bool = False, now: datetime | None = None) -> dict:
    """Evaluate and (if allowed) deliver one reminder. Returns {status, reason}."""
    now = now or datetime.utcnow()
    res = {"student_id": r["id"], "trigger": trigger, "step": step}
    live = mode == "live"

    def skip(reason, persist=False):
        res.update(status="skipped", reason=reason)
        return res

    if not applies(r, trigger):
        return skip("no_longer_applies")
    if r["eligibility"] == "dropped":
        return skip("dropped")
    if r["eligibility"] == "ended" and not (manual and override_ended):
        return skip("cohort_ended")
    if r["is_test"] and live:
        return skip("test_account")

    key = _dedupe(trigger, step, r, manual, now)
    sup = await suppression_reason(r["email"])
    if sup:
        await _write_row(r, trigger, step, "suppressed", sup, f"{key}:sup:{sup}")
        return skip(sup)
    if r["holdout"] and not manual:
        await _write_row(r, trigger, step, "suppressed", "holdout", f"{key}:sup:holdout")
        return skip("holdout")
    if await recently_emailed(r["email"], trigger, cfg["frequency_cap_hours"]):
        return skip("frequency_cap")

    if not live:
        created = await _write_row(r, trigger, step, "dry_run", "would_send", f"{key}:dry")
        res.update(status="dry_run", reason="would_send" if created else "already_recorded")
        return res

    token = secrets.token_urlsafe(12)
    if not await _write_row(r, trigger, step, "sending", None, key, token):
        return skip("duplicate")  # already claimed or sent: never deliver twice
    ok = False
    try:
        ok = await es.email_service.send_activation(
            trigger, step, r["email"], r["name"], r["id"], r["batch_id"], **_context(r, trigger, token))
    except Exception as exc:  # noqa: BLE001
        logger.error("activation send failed for %s: %s", r["email"], exc)
    log = await db.fetch_one(
        "SELECT id FROM email_logs WHERE lower(recipient_email) = ? AND email_type = ? ORDER BY id DESC LIMIT 1",
        (r["email"].lower(), f"activation_{trigger}"))
    await db.execute(
        "UPDATE engagement_reminders SET status = ?, sent_at = CURRENT_TIMESTAMP, email_log_id = ? WHERE dedupe_key = ?",
        ("sent" if ok else "failed", log["id"] if log else None, key))
    if ok:
        await record_event("reminder_sent", r["id"], r["batch_id"], email=r["email"],
                           discriminator=key, meta={"trigger": trigger, "step": step})
    res.update(status="sent" if ok else "failed", reason=None)
    return res


async def run_tick(now: datetime | None = None, throttle: float = SEND_THROTTLE_SECONDS) -> dict:
    """One automatic evaluation pass. Safe to call any time (hourly job or manual button)."""
    now = now or datetime.utcnow()
    cfg = await seg.get_config()
    mode, note = effective_mode(cfg)
    summary = {"mode": mode, "note": note, "evaluated": 0, "sent": 0, "would_send": 0, "failed": 0,
               "suppressed": 0, "skipped": 0, "ran_at": now.isoformat()}
    if mode == "off":
        return summary
    rows, _ = await seg.load_recovery_rows(now, include_test=(mode != "live"))
    rows = [r for r in rows if r["eligibility"] == "active"]  # automation never touches ended cohorts
    plans = await plan_automatic(rows, cfg, now, include_dry=(mode != "live"))
    for p in plans:
        summary["evaluated"] += 1
        res = await process_one(p["row"], p["trigger"], p["step"], mode, cfg, now=now)
        s = res["status"]
        if s == "sent":
            summary["sent"] += 1
            await asyncio.sleep(throttle)
        elif s == "dry_run" and res["reason"] == "would_send":
            summary["would_send"] += 1
        elif s == "failed":
            summary["failed"] += 1
        elif res.get("reason") in ("holdout", "opted_out", "bounced", "spam_reported", "unsubscribed"):
            summary["suppressed"] += 1
        else:
            summary["skipped"] += 1
    await db.execute(
        """INSERT INTO engagement_settings (key, value, updated_at) VALUES ('last_run', ?, CURRENT_TIMESTAMP)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP""",
        (__import__("json").dumps(summary),))
    logger.info("engagement tick: %s", summary)
    return summary


async def evaluate_manual(student_ids: list[int], override_ended: bool = False,
                          now: datetime | None = None) -> tuple[list[dict], list[dict], list[dict]]:
    """Dry evaluation for the admin confirm dialog. Returns (eligible, excluded, rows-with-trigger).
    Never writes. Mirrors process_one's gates."""
    now = now or datetime.utcnow()
    cfg = await seg.get_config()
    rows, _ = await seg.load_recovery_rows(now, include_test=True)
    by = {r["id"]: r for r in rows}
    eligible, excluded = [], []
    for sid in student_ids:
        r = by.get(sid)
        if not r:
            excluded.append({"student_id": sid, "reason": "not_enrolled"})
            continue
        trig = recommended_trigger(r)
        if not trig:
            excluded.append({"student_id": sid, "name": r["name"], "reason": "nothing_to_send"})
            continue
        reason = None
        if r["eligibility"] == "ended" and not override_ended:
            reason = "cohort_ended"
        else:
            reason = await suppression_reason(r["email"])
            if not reason and await recently_emailed(r["email"], trig, cfg["frequency_cap_hours"]):
                reason = "frequency_cap"
        if reason:
            excluded.append({"student_id": sid, "name": r["name"], "reason": reason, "trigger": trig})
        else:
            done = await _steps_done(sid, r["batch_id"], trig, False)
            steps = len(cfg["triggers"].get(trig, {}).get("delays_h") or [1])
            eligible.append({"student_id": sid, "name": r["name"], "email": r["email"], "trigger": trig,
                             "step": min(done + 1, max(steps, 1)), "ended": r["eligibility"] == "ended"})
    return eligible, excluded, rows


async def send_manual(student_ids: list[int], override_ended: bool = False, now: datetime | None = None,
                      throttle: float = SEND_THROTTLE_SECONDS) -> dict:
    now = now or datetime.utcnow()
    cfg = await seg.get_config()
    mode, note = effective_mode(cfg)
    out = {"mode": mode, "note": note, "sent": 0, "would_send": 0, "skipped": [], "failed": 0}
    if mode == "off":
        out["note"] = "Engagement is switched off. Set it to Dry run to preview sends."
        return out
    rows, _ = await seg.load_recovery_rows(now, include_test=(mode != "live"))
    by = {r["id"]: r for r in rows}
    for sid in student_ids:
        r = by.get(sid)
        trig = recommended_trigger(r) if r else None
        if not r or not trig:
            out["skipped"].append({"student_id": sid, "reason": "nothing_to_send"})
            continue
        done = await _steps_done(sid, r["batch_id"], trig, False)
        steps = len(cfg["triggers"].get(trig, {}).get("delays_h") or [1])
        res = await process_one(r, trig, min(done + 1, max(steps, 1)), mode, cfg, manual=True,
                                override_ended=override_ended, now=now)
        if res["status"] == "sent":
            out["sent"] += 1
            await asyncio.sleep(throttle)
        elif res["status"] == "dry_run":
            out["would_send"] += 1 if res["reason"] == "would_send" else 0
        elif res["status"] == "failed":
            out["failed"] += 1
        else:
            out["skipped"].append({"student_id": sid, "reason": res["reason"]})
    return out


# ── Click tracking and opt-out ───────────────────────────────────────────────

async def register_click(token: str) -> bool:
    """Marks the reminder clicked exactly once. Returns True when the token exists."""
    row = await db.fetch_one(
        "SELECT student_id, batch_id, clicked_at, dedupe_key, trigger_key FROM engagement_reminders WHERE token = ?",
        (token,))
    if not row:
        return False
    if not row["clicked_at"]:
        await db.execute(
            "UPDATE engagement_reminders SET clicked_at = CURRENT_TIMESTAMP WHERE token = ? AND clicked_at IS NULL", (token,))
        await record_event("reminder_clicked", row["student_id"], row["batch_id"],
                           discriminator=row["dedupe_key"], meta={"trigger": row["trigger_key"]})
    return True


async def opt_out(email: str, source: str = "unsubscribe_link") -> None:
    em = email.strip().lower()
    await db.execute(
        """INSERT INTO notification_preferences (email, reminders_opt_out, unsubscribed_at, source, updated_at)
           VALUES (?, 1, CURRENT_TIMESTAMP, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(email) DO UPDATE SET reminders_opt_out = 1, unsubscribed_at = COALESCE(unsubscribed_at, CURRENT_TIMESTAMP),
                                            source = excluded.source, updated_at = CURRENT_TIMESTAMP""",
        (em, source))
