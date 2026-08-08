"""
SkillMe — Scheduler Service
Uses APScheduler to automatically assign weekly tasks to active batches
that have auto_assign enabled.

Logic:
  - Runs every Monday at 09:00 (configurable)
  - For each active batch with auto_assign=1:
      1. Calculate the current week number from batch.start_date
      2. Skip if week already assigned or week > 4
      3. Call batch_service.assign_week_from_task_repo()
      4. Record the week in weeks_assigned
"""

import json
import logging
from datetime import date, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from db.database import db
from services.batch_service import batch_service
from services.email_service import email_service

logger = logging.getLogger("skillme.scheduler")


def _current_week(start_date_str: str) -> int | None:
    """
    Calculate which week of the internship we are in.
    Week 1 = days 1-7, Week 2 = days 8-14, etc.
    Returns None if the batch hasn't started or has finished (> week 4).
    """
    try:
        start = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None

    today = date.today()
    delta = (today - start).days
    if delta < 0:
        return None          # Batch hasn't started yet
    week = (delta // 7) + 1
    if week > 4:
        return None          # Internship over
    return week


async def run_auto_assign() -> None:
    """Core logic: find batches due for task assignment and assign."""
    logger.info("Scheduler: running auto-assign check...")

    batches = await db.fetch_all(
        "SELECT * FROM batches WHERE status = 'active' AND auto_assign = 1"
    )
    if not batches:
        logger.info("Scheduler: no active batches with auto_assign enabled.")
        return

    for batch in batches:
        week = _current_week(batch.get("start_date"))
        if week is None:
            logger.info(f"Batch {batch['id']} ({batch['domain']}): outside active weeks, skipping.")
            continue

        # Parse already-assigned weeks
        try:
            assigned = json.loads(batch.get("weeks_assigned") or "[]")
        except json.JSONDecodeError:
            assigned = []

        if week in assigned:
            logger.info(f"Batch {batch['id']}: Week {week} already assigned, skipping.")
            continue

        # Assign!
        logger.info(f"Batch {batch['id']} ({batch['domain']} #{batch['batch_number']}): assigning Week {week}...")
        try:
            result = await batch_service.assign_week_from_task_repo(
                batch_id=batch["id"],
                week_number=week,
            )
            # Record this week as assigned
            assigned.append(week)
            await db.execute(
                "UPDATE batches SET weeks_assigned = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (json.dumps(assigned), batch["id"]),
            )
            logger.info(
                f"Batch {batch['id']}: auto-assigned {len(result)} issues for Week {week}."
            )

            # Send weekly task email to each enrolled student
            try:
                students = await db.fetch_all(
                    """SELECT s.first_name, s.last_name, s.email, s.github_username
                       FROM students s
                       JOIN enrollments e ON e.student_id = s.id
                       WHERE e.batch_id = ? AND e.status != 'dropped'""",
                    (batch["id"],)
                )
                base_repo_url = (
                    f"https://github.com/{batch['repo_name']}"
                    if batch.get("repo_name") else None
                )
                tasks_for_email = [
                    {"title": r.get("title", "Task"), "issue_url": r.get("html_url")}
                    for r in result
                ]
                for student in students:
                    # Build a filtered issues URL — shows only THIS student's issues
                    gh_user = student.get("github_username")
                    repo_url = (
                        f"{base_repo_url}/issues?assignee={gh_user}"
                        if base_repo_url and gh_user else base_repo_url
                    )
                    await email_service.send_weekly_tasks_notification(
                        first_name=student["first_name"],
                        last_name=student["last_name"],
                        email=student["email"],
                        domain=batch["domain"],
                        batch_number=batch["batch_number"],
                        week_number=week,
                        tasks=tasks_for_email,
                        repo_url=base_repo_url,
                        github_username=gh_user or None,
                    )
                logger.info(f"Batch {batch['id']}: sent Week {week} emails to {len(students)} students.")
            except Exception as email_err:
                logger.error(f"Batch {batch['id']}: failed to send task emails: {email_err}")

        except Exception as e:
            logger.error(f"Batch {batch['id']}: auto-assign failed for Week {week}: {e}")


class SchedulerService:
    """Wraps APScheduler for lifecycle management inside FastAPI."""

    def __init__(self):
        self._scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
        # Default: every Monday at 09:00 IST
        self._scheduler.add_job(
            run_auto_assign,
            trigger=CronTrigger(day_of_week="mon", hour=9, minute=0),
            id="auto_assign_weekly",
            replace_existing=True,
            misfire_grace_time=3600,   # Allow up to 1 hour late
        )

    def start(self):
        self._scheduler.start()
        logger.info("Scheduler started — auto-assign runs every Monday at 09:00 IST.")

    def shutdown(self):
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler shut down.")

    async def trigger_now(self) -> dict:
        """Manually trigger the auto-assign job (for testing or immediate use)."""
        await run_auto_assign()
        return {"status": "triggered", "message": "Auto-assign ran immediately."}


# Global instance
scheduler_service = SchedulerService()
