"""
SkillMe — Credential follow-ups and the credential funnel.

One reminder email, "credentials_waiting", sent by a daily job (see main.py) to students who
are eligible (3 of 4 weeks approved, or an approved priority request) but haven't paid:
the first FIRST_DELAY_DAYS after the unlock, then once every GAP_DAYS until they pay.

There is no deadline in it: it reminds, it never threatens. It stops by itself the moment the
student pays, because candidates are rebuilt from live data on every run. Opt-outs, hard bounces and spam reports are honoured (engagement_service rules), test
accounts are never emailed, and nobody gets two reminder emails within REMINDER_GAP_HOURS.

The funnel half records the browser-side steps (saw the offer, opened checkout, clicked pay,
opened the seat form, came back from an email) as once-per-enrollment student_events, and
funnel_report() lines them up against payments and stipend_entries.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from db.database import db
from services import analytics_service as an
from services.activation_events import record_event
from services.email_service import email_service

logger = logging.getLogger("skillme.credential_reminders")

UNLOCK_WEEKS = 3          # mirrors routes/payments.PAYMENT_UNLOCK_TASKS
FIRST_DELAY_DAYS = 2      # give them a moment after the unlock before the first nudge
GAP_DAYS = 14             # once every two weeks until they pay
REMINDER_GAP_HOURS = 24   # across every reminder type, so nobody gets two in a day

KINDS = ("credentials_waiting",)
REMINDER_EMAIL_TYPES = ("task_reminder", "credentials_waiting")

# Steps the dashboard may report. All are once per enrollment (see activation_events).
FUNNEL_STEPS = {
    "cred_offer_seen",       # dashboard loaded while unlocked and unpaid
    "cred_checkout_opened",  # checkout modal opened
    "cred_pay_clicked",      # pay button pressed
    "stipend_form_opened",   # seat modal opened (paid)
    "cred_email_clicked",    # arrived from a credentials_waiting email
    "stipend_email_clicked", # arrived from an old stipend-seat email link (no longer sent)
}


async def track_step(student: dict, step: str, batch_id: int | None) -> bool:
    if step not in FUNNEL_STEPS:
        return False
    return await record_event(step, student["id"], batch_id, email=student.get("email"))


# ── Candidates ───────────────────────────────────────────────────────────────

def _unlock_time(approved_at: list[datetime], unlocked_at: datetime | None) -> datetime | None:
    """When the enrollment became payable: the 3rd approved week, or an admin unlock if earlier."""
    times = sorted(approved_at)
    by_weeks = times[UNLOCK_WEEKS - 1] if len(times) >= UNLOCK_WEEKS else None
    options = [t for t in (by_weeks, unlocked_at) if t]
    return min(options) if options else None


async def unlocked_enrollments() -> list[dict]:
    """Every live, non-test enrollment that can pay (paid or not), with its unlock time."""
    rows = await db.fetch_all(
        """SELECT s.id AS student_id, s.email, s.first_name, s.last_name, s.domain,
                  e.batch_id, e.payment_unlocked_at,
                  EXISTS (SELECT 1 FROM payments p WHERE p.student_id = s.id AND p.batch_id = e.batch_id
                          AND p.status = 'paid') AS paid,
                  EXISTS (SELECT 1 FROM certificates c WHERE c.student_id = s.id AND c.batch_id = e.batch_id) AS has_cert
           FROM students s JOIN enrollments e ON e.student_id = s.id
           WHERE e.status != 'dropped' AND COALESCE(s.is_test, 0) = 0"""
    )
    if not rows:
        return []
    subs = await db.fetch_all(
        """SELECT student_id, batch_id, week, MIN(COALESCE(reviewed_at, submitted_at)) AS at
           FROM submissions WHERE status = 'approved' GROUP BY student_id, batch_id, week"""
    )
    approved: dict[tuple, list[datetime]] = {}
    for x in subs:
        t = an.parse_ts(x["at"])
        if t:
            approved.setdefault((x["student_id"], x["batch_id"]), []).append(t)
    out = []
    for r in rows:
        unlock = _unlock_time(approved.get((r["student_id"], r["batch_id"]), []),
                              an.parse_ts(r["payment_unlocked_at"]))
        if unlock:
            out.append({**dict(r), "paid": bool(r["paid"]), "has_cert": bool(r["has_cert"]), "unlocked_at": unlock})
    return out


async def _history(email: str, kind: str) -> tuple[int, datetime | None]:
    row = await db.fetch_one(
        """SELECT COUNT(*) AS n, MAX(sent_at) AS last FROM email_logs
           WHERE lower(recipient_email) = ? AND email_type = ? AND status = 'sent'""",
        (email.lower(), kind))
    return int(row["n"] or 0) if row else 0, an.parse_ts(row["last"]) if row and row["last"] else None


async def _emailed_recently(email: str) -> bool:
    marks = ",".join("?" for _ in REMINDER_EMAIL_TYPES)
    row = await db.fetch_one(
        f"""SELECT 1 AS x FROM email_logs
            WHERE lower(recipient_email) = ? AND status = 'sent'
              AND (email_type IN ({marks}) OR email_type LIKE 'activation_%')
              AND sent_at > datetime('now', ?) LIMIT 1""",
        (email.lower(), *REMINDER_EMAIL_TYPES, f"-{REMINDER_GAP_HOURS} hours"))
    return bool(row)


async def _due(email: str, kind: str, since: datetime, now: datetime) -> int | None:
    """The reminder number (1, 2, ...) that is due now, or None."""
    sent, last = await _history(email, kind)
    if sent == 0 and now - since < timedelta(days=FIRST_DELAY_DAYS):
        return None
    if last and now - last < timedelta(days=GAP_DAYS):
        return None
    return sent + 1


async def _suppressed(email: str) -> bool:
    from services.engagement_service import suppression_reason
    return bool(await suppression_reason(email))


async def get_candidates(now: datetime | None = None) -> list[dict]:
    """Who gets a reminder today: eligible, unpaid, due. One email per person per run."""
    now = now or datetime.utcnow()
    out: list[dict] = []
    seen: set[str] = set()

    # Credentials waiting: unlocked, unpaid, no certificate on any of their enrollments
    issued = {r["email"].lower() for r in await db.fetch_all(
        "SELECT DISTINCT s.email FROM certificates c JOIN students s ON s.id = c.student_id")}
    for r in sorted(await unlocked_enrollments(), key=lambda x: x["unlocked_at"]):
        em = (r["email"] or "").lower()
        if r["paid"] or r["has_cert"] or not em or em in issued or em in seen:
            continue
        step = await _due(em, "credentials_waiting", r["unlocked_at"], now)
        if step:
            seen.add(em)
            out.append({**r, "kind": "credentials_waiting", "step": step})

    kept = []
    for c in out:
        if await _suppressed(c["email"]) or await _emailed_recently(c["email"]):
            continue
        kept.append(c)
    return kept


# ── Sending ──────────────────────────────────────────────────────────────────

async def send_credential_reminders(now: datetime | None = None, throttle: float = 1.0) -> dict:
    candidates = await get_candidates(now)
    summary = {"sent": 0, "failed": 0}
    for c in candidates:
        try:
            ok = await email_service.send_credentials_waiting(
                c["first_name"], c["last_name"], c["email"], c.get("domain") or "web-dev", c["step"],
                student_id=c["student_id"], batch_id=c["batch_id"])
        except Exception as exc:  # noqa: BLE001 — one bad address must not stop the run
            logger.error("%s to %s failed: %s", c["kind"], c["email"], exc)
            ok = False
        if ok:
            summary["sent"] += 1
            await asyncio.sleep(throttle)
        else:
            summary["failed"] += 1
    logger.info("Credential reminders: %s", summary)
    return summary


# ── Funnel report ────────────────────────────────────────────────────────────

async def funnel_report(days: int | None = None) -> dict:
    """Unlock -> offer seen -> checkout -> pay click -> paid -> seat, plus the reminder emails.
    With `days`, every step counts only enrollments unlocked in that window."""
    now = datetime.utcnow()
    since = now - timedelta(days=days) if days else None
    unlocked = [r for r in await unlocked_enrollments() if not since or r["unlocked_at"] >= since]
    keys = {(r["student_id"], r["batch_id"]) for r in unlocked}
    emails = {(r["email"] or "").lower() for r in unlocked}

    events = await db.fetch_all(
        f"""SELECT student_id, batch_id, event_type, MIN(occurred_at) AS first_at FROM student_events
            WHERE event_type IN ({",".join("?" for _ in FUNNEL_STEPS)})
            GROUP BY student_id, batch_id, event_type""", tuple(FUNNEL_STEPS))
    reached: dict[str, set] = {s: set() for s in FUNNEL_STEPS}
    first_event = None
    for e in events:
        k = (e["student_id"], e["batch_id"])
        if k in keys:
            reached[e["event_type"]].add(k)
        t = an.parse_ts(e["first_at"])
        first_event = min(first_event, t) if first_event and t else (t or first_event)

    seats = {r["email"] for r in await db.fetch_all("SELECT email FROM stipend_entries")}
    paid = [r for r in unlocked if r["paid"]]
    seated = {(r["email"] or "").lower() for r in unlocked if r["has_cert"]} & seats

    sends = {}
    for kind in KINDS:
        row = await db.fetch_one(
            "SELECT COUNT(*) AS n, COUNT(DISTINCT lower(recipient_email)) AS people FROM email_logs "
            "WHERE email_type = ? AND status = 'sent'", (kind,))
        sends[kind] = {"emails": int(row["n"] or 0), "people": int(row["people"] or 0)}

    total = len(unlocked)

    def step(label, n, base=None):
        b = total if base is None else base
        return {"step": label, "count": n, "pct_of_unlocked": an.pct(n, total), "pct_of_previous": an.pct(n, b)}

    seen_n = len(reached["cred_offer_seen"])
    opened = len(reached["cred_checkout_opened"])
    clicked = len(reached["cred_pay_clicked"])
    return {
        "window_days": days,
        "tracking_since": first_event.isoformat() if first_event else None,
        "note": "Browser steps are only recorded from tracking_since. Paid and seat counts include earlier students.",
        "steps": [
            step("Credentials unlocked", total, total),
            step("Saw the offer on the dashboard", seen_n, total),
            step("Opened checkout", opened, seen_n),
            step("Pressed pay", clicked, opened),
            step("Paid", len(paid), clicked),
            step("Took a stipend seat", len(seated), len(paid)),
        ],
        "reminders": {
            **sends,
            "came_back_from_credentials_email": len(reached["cred_email_clicked"]),
        },
        "people_unlocked": len(emails),
    }
