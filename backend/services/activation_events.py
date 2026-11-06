"""
SkillMe — Activation event recorder.

Append-only log of student lifecycle events. Every write is INSERT OR IGNORE on a
dedupe_key, so retries and replays never create duplicates. record_event() never
raises: tracking must not be able to break a login, submission, enrollment or approval.
"""
from __future__ import annotations

import json
import logging

from db.database import db

logger = logging.getLogger("skillme.activation")

EVENT_TYPES = {
    "enrollment_created", "first_verified_login", "first_task_viewed",
    "first_task_submitted", "first_task_approved", "week_approved",
    "internship_completed", "reminder_sent", "reminder_clicked", "support_requested",
}
# One occurrence per enrollment; week_approved is keyed per week.
_ONCE_PER_ENROLLMENT = {
    "enrollment_created", "first_verified_login", "first_task_viewed",
    "first_task_submitted", "first_task_approved", "internship_completed",
}


def make_dedupe_key(event_type: str, student_id: int, batch_id: int | None,
                    discriminator: str | int | None = None) -> str:
    parts = [event_type, str(student_id), str(batch_id if batch_id is not None else 0)]
    if discriminator is not None:
        parts.append(str(discriminator))
    return ":".join(parts)


async def record_event(event_type: str, student_id: int, batch_id: int | None = None, *,
                       email: str | None = None, at: str | None = None,
                       meta: dict | None = None, source: str = "live",
                       discriminator: str | int | None = None) -> bool:
    """Record an event once. Returns True if a new row was written, False otherwise."""
    try:
        if event_type not in EVENT_TYPES:
            logger.warning("Unknown activation event type: %s", event_type)
            return False
        if event_type in _ONCE_PER_ENROLLMENT:
            discriminator = None
        key = make_dedupe_key(event_type, student_id, batch_id, discriminator)
        cols = "student_id, batch_id, email, event_type, source, meta, dedupe_key"
        vals = [student_id, batch_id, (email or "").lower() or None, event_type, source,
                json.dumps(meta) if meta else None, key]
        if at:
            cols += ", occurred_at"
            vals.append(at)
        marks = ", ".join("?" for _ in vals)
        before = await db.fetch_one("SELECT id FROM student_events WHERE dedupe_key = ?", (key,))
        if before:
            return False
        await db.execute(f"INSERT OR IGNORE INTO student_events ({cols}) VALUES ({marks})", tuple(vals))
        return True
    except Exception as exc:  # noqa: BLE001 — tracking must never break the caller
        logger.warning("record_event(%s, %s) failed: %s", event_type, student_id, exc)
        return False


# ── Hook helpers: each is fully guarded and safe to await from existing routes ──

async def track_enrollment(student_id: int, batch_id: int | None) -> None:
    try:
        row = await db.fetch_one("SELECT email FROM students WHERE id = ?", (student_id,))
        await record_event("enrollment_created", student_id, batch_id,
                           email=row["email"] if row else None)
    except Exception as exc:  # noqa: BLE001
        logger.warning("track_enrollment failed: %s", exc)


async def track_login(email: str) -> None:
    """First verified login: one event per non-dropped enrollment of this email."""
    try:
        rows = await db.fetch_all(
            """SELECT s.id AS student_id, e.batch_id
               FROM students s JOIN enrollments e ON e.student_id = s.id
               WHERE lower(s.email) = lower(?) AND e.status != 'dropped'""",
            (email,),
        )
        for r in rows:
            await record_event("first_verified_login", r["student_id"], r["batch_id"], email=email)
    except Exception as exc:  # noqa: BLE001
        logger.warning("track_login failed: %s", exc)


async def track_submission(student_id: int, batch_id: int, week: int) -> None:
    try:
        row = await db.fetch_one("SELECT email FROM students WHERE id = ?", (student_id,))
        await record_event("first_task_submitted", student_id, batch_id,
                           email=row["email"] if row else None, meta={"week": week})
    except Exception as exc:  # noqa: BLE001
        logger.warning("track_submission failed: %s", exc)


async def track_approval(submission_id: int) -> None:
    """Records first_task_approved / week_approved / internship_completed (read-only on core tables)."""
    try:
        sub = await db.fetch_one(
            """SELECT sub.student_id, sub.batch_id, sub.week, s.email
               FROM submissions sub JOIN students s ON s.id = sub.student_id WHERE sub.id = ?""",
            (submission_id,),
        )
        if not sub:
            return
        sid, bid, wk, em = sub["student_id"], sub["batch_id"], sub["week"], sub["email"]
        await record_event("week_approved", sid, bid, email=em, discriminator=wk, meta={"week": wk})
        await record_event("first_task_approved", sid, bid, email=em, meta={"week": wk})
        cnt = await db.fetch_one(
            "SELECT COUNT(DISTINCT week) AS n FROM submissions WHERE student_id = ? AND batch_id = ? AND status = 'approved'",
            (sid, bid),
        )
        if cnt and int(cnt["n"] or 0) >= 4:
            await record_event("internship_completed", sid, bid, email=em)
    except Exception as exc:  # noqa: BLE001
        logger.warning("track_approval failed: %s", exc)
