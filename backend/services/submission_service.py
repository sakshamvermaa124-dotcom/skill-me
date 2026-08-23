"""
SkillMe — Submission Service
Handles the LinkedIn-URL task submission flow: students submit a link to
their milestone post, an admin reviews it, and approval increments progress.
"""

import logging
from datetime import datetime
from urllib.parse import urlparse

from db.database import db

logger = logging.getLogger("skillme.submission")

SCORE_PER_APPROVAL = 25


def _is_linkedin_url(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False
    return host.endswith("linkedin.com")


class SubmissionService:
    """Manages LinkedIn-URL task submissions and admin review."""

    async def submit_linkedin_url(
        self, student_id: int, batch_id: int, week: int, linkedin_url: str
    ) -> dict:
        """Submit (or resubmit after rejection) a LinkedIn post URL for a week's task."""
        if not _is_linkedin_url(linkedin_url):
            raise ValueError("Please submit a valid linkedin.com URL.")

        enrollment = await db.fetch_one(
            "SELECT id FROM enrollments WHERE student_id = ? AND batch_id = ? AND status != 'dropped'",
            (student_id, batch_id),
        )
        if not enrollment:
            raise ValueError("Student is not enrolled in this batch.")

        existing = await db.fetch_one(
            "SELECT id, status FROM submissions WHERE student_id = ? AND batch_id = ? AND week = ?",
            (student_id, batch_id, week),
        )
        if existing:
            if existing["status"] == "approved":
                raise ValueError("This week's task is already approved.")
            if existing["status"] == "pending":
                raise ValueError("You already have a submission pending review for this week.")
            # rejected — allow resubmission
            await db.execute(
                """UPDATE submissions
                   SET linkedin_url = ?, status = 'pending', admin_note = NULL,
                       submitted_at = CURRENT_TIMESTAMP, reviewed_at = NULL
                   WHERE id = ?""",
                (linkedin_url, existing["id"]),
            )
            submission_id = existing["id"]
        else:
            submission_id = await db.insert(
                """INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status)
                   VALUES (?, ?, ?, ?, 'pending')""",
                (student_id, batch_id, week, linkedin_url),
            )

        logger.info(f"Student {student_id} submitted week {week} task for batch {batch_id}: {linkedin_url}")
        return {"submission_id": submission_id, "status": "pending"}

    async def approve_submission(self, submission_id: int, admin_note: str | None = None) -> dict:
        submission = await db.fetch_one("SELECT * FROM submissions WHERE id = ?", (submission_id,))
        if not submission:
            raise ValueError(f"Submission {submission_id} not found")
        if submission["status"] == "approved":
            return {"submission_id": submission_id, "status": "approved", "already": True}

        now = datetime.utcnow().isoformat()
        await db.execute(
            "UPDATE submissions SET status = 'approved', admin_note = ?, reviewed_at = ? WHERE id = ?",
            (admin_note, now, submission_id),
        )

        student_id = submission["student_id"]
        batch_id = submission["batch_id"]
        week = submission["week"]

        existing_progress = await db.fetch_one(
            "SELECT id FROM progress WHERE student_id = ? AND batch_id = ? AND week = ?",
            (student_id, batch_id, week),
        )
        if existing_progress:
            await db.execute(
                """UPDATE progress
                   SET issues_completed = issues_completed + 1,
                       score = score + ?,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (SCORE_PER_APPROVAL, existing_progress["id"]),
            )
        else:
            await db.insert(
                """INSERT INTO progress (student_id, batch_id, week, issues_completed, score)
                   VALUES (?, ?, ?, 1, ?)""",
                (student_id, batch_id, week, SCORE_PER_APPROVAL),
            )

        logger.info(f"Approved submission {submission_id} (student {student_id}, week {week}): +{SCORE_PER_APPROVAL} score")
        return {"submission_id": submission_id, "status": "approved"}

    async def reject_submission(self, submission_id: int, admin_note: str | None = None) -> dict:
        submission = await db.fetch_one("SELECT * FROM submissions WHERE id = ?", (submission_id,))
        if not submission:
            raise ValueError(f"Submission {submission_id} not found")

        now = datetime.utcnow().isoformat()
        await db.execute(
            "UPDATE submissions SET status = 'rejected', admin_note = ?, reviewed_at = ? WHERE id = ?",
            (admin_note, now, submission_id),
        )
        logger.info(f"Rejected submission {submission_id}: {admin_note or ''}")
        return {"submission_id": submission_id, "status": "rejected"}

    async def bulk_approve(self, submission_ids: list[int]) -> list[dict]:
        results = []
        for sid in submission_ids:
            try:
                results.append(await self.approve_submission(sid))
            except ValueError as e:
                results.append({"submission_id": sid, "status": "error", "error": str(e)})
        return results

    async def bulk_reject(self, submission_ids: list[int], admin_note: str | None = None) -> list[dict]:
        results = []
        for sid in submission_ids:
            try:
                results.append(await self.reject_submission(sid, admin_note))
            except ValueError as e:
                results.append({"submission_id": sid, "status": "error", "error": str(e)})
        return results

    async def list_submissions(self, status: str | None = None) -> list[dict]:
        query = """SELECT sub.*, s.first_name, s.last_name, s.email,
                          b.domain, b.batch_number
                   FROM submissions sub
                   JOIN students s ON sub.student_id = s.id
                   JOIN batches b ON sub.batch_id = b.id"""
        params: tuple = ()
        if status:
            query += " WHERE sub.status = ?"
            params = (status,)
        query += " ORDER BY sub.submitted_at ASC"
        return await db.fetch_all(query, params)


# Global service instance
submission_service = SubmissionService()
