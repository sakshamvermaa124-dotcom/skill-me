"""
SkillMe — Task Reminder Service
Detects inactive enrolled students and sends professional nudge emails.

Inactivity criteria:
  - Student status = 'enrolled', enrollment active
  - Batch is active
  - Completed < 4 tasks
  - No submission (pending or approved) in last 5 days
  - No 'task_reminder' email sent in last 7 days (cooldown)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from db.database import db
from services.email_service import email_service

logger = logging.getLogger("skillme.reminders")

# Inactivity threshold: days without any submission
INACTIVITY_DAYS = 7
# Cooldown: minimum days between reminder emails to same student
REMINDER_COOLDOWN_DAYS = 7


async def get_inactive_students() -> list[dict]:
    """
    Find enrolled students who haven't submitted any task in the last
    INACTIVITY_DAYS days, have not completed all 4 tasks, and haven't
    received a task_reminder email in the last REMINDER_COOLDOWN_DAYS days.
    """
    query = """
        SELECT
            s.id            AS student_id,
            s.email,
            s.first_name,
            s.last_name,
            s.domain,
            e.batch_id,
            b.start_date,
            COALESCE((
                SELECT SUM(p.issues_completed)
                FROM progress p
                WHERE p.student_id = s.id AND p.batch_id = e.batch_id
            ), 0) AS completed_tasks,
            COALESCE((
                SELECT MAX(sub.submitted_at)
                FROM submissions sub
                WHERE sub.student_id = s.id AND sub.batch_id = e.batch_id
            ), e.joined_at) AS last_activity
        FROM students s
        JOIN enrollments e ON e.student_id = s.id
        JOIN batches b ON b.id = e.batch_id
        WHERE s.status = 'enrolled'
          AND e.status IN ('enrolled', 'active')
          AND b.status = 'active'
          -- Not finished (completed < 4 tasks)
          AND COALESCE((
              SELECT SUM(p2.issues_completed)
              FROM progress p2
              WHERE p2.student_id = s.id AND p2.batch_id = e.batch_id
          ), 0) < 4
          -- Must be inactive for at least N days
          AND julianday('now') - julianday(COALESCE((
              SELECT MAX(sub.submitted_at)
              FROM submissions sub
              WHERE sub.student_id = s.id AND sub.batch_id = e.batch_id
          ), e.joined_at)) >= ?
          -- Cooldown: no reminder sent in last M days
          AND NOT EXISTS (
              SELECT 1 FROM email_logs el
              WHERE el.recipient_email = s.email
                AND el.email_type = 'task_reminder'
                AND el.status = 'sent'
                AND el.sent_at > datetime('now', ?)
          )
        ORDER BY last_activity DESC
    """
    params = (
        INACTIVITY_DAYS,
        f"-{REMINDER_COOLDOWN_DAYS} days",
    )

    rows = await db.fetch_all(query, params)

    results = []
    for row in rows:
        completed = int(row["completed_tasks"] or 0)
        week_due = min(completed + 1, 4)

        # Calculate days inactive
        last_activity = row["last_activity"]
        if last_activity:
            try:
                if isinstance(last_activity, str):
                    # Handle various datetime formats from SQLite
                    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                        try:
                            last_dt = datetime.strptime(last_activity, fmt)
                            break
                        except ValueError:
                            continue
                    else:
                        last_dt = datetime.utcnow()
                else:
                    last_dt = datetime.utcnow()
                days_inactive = (datetime.utcnow() - last_dt).days
            except Exception:
                days_inactive = INACTIVITY_DAYS
        else:
            days_inactive = INACTIVITY_DAYS

        results.append({
            "student_id": row["student_id"],
            "email": row["email"],
            "first_name": row["first_name"],
            "last_name": row["last_name"],
            "domain": row["domain"],
            "batch_id": row["batch_id"],
            "week_due": week_due,
            "days_inactive": max(days_inactive, 1),
            "completed_tasks": completed,
            "last_activity": last_activity,
        })

    logger.info("Found %d inactive students for task reminders", len(results))
    return results


async def send_reminders(student_list: list[dict] | None = None) -> dict:
    """
    Send task reminder emails to inactive students.
    If student_list is None, auto-detects inactive students.
    Returns summary dict with sent/failed counts.
    """
    if student_list is None:
        student_list = await get_inactive_students()

    if not student_list:
        logger.info("No inactive students to remind.")
        return {"sent": 0, "failed": 0, "total": 0}

    sent = 0
    failed = 0

    for student in student_list:
        try:
            success = await email_service.send_task_reminder(
                first_name=student["first_name"],
                last_name=student["last_name"],
                email=student["email"],
                domain=student.get("domain") or "web-dev",
                week_due=student["week_due"],
                days_inactive=student["days_inactive"],
                completed_tasks=student["completed_tasks"],
                student_id=student["student_id"],
                batch_id=student["batch_id"],
            )
            if success:
                sent += 1
                logger.info("Task reminder sent → %s (week %d, %d days inactive)",
                            student["email"], student["week_due"], student["days_inactive"])
            else:
                failed += 1
        except Exception as exc:
            logger.error("Failed to send task reminder to %s: %s", student["email"], exc)
            failed += 1

        # Throttle: 1 second between sends to avoid SMTP rate limits
        await asyncio.sleep(1)

    summary = {"sent": sent, "failed": failed, "total": sent + failed}
    logger.info("Task reminder batch complete: %s", summary)
    return summary
