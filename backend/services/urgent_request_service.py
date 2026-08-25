"""
SkillMe — Urgent Request Service
Handles student requests for 24h expedited certificate/LOR/portfolio processing.
"""

import logging
from datetime import datetime

from db.database import db

logger = logging.getLogger("skillme.urgent_request")


async def _completion_pct(student_id: int, batch_id: int) -> int:
    """Same formula as the certificate download completion gate, scoped to one batch."""
    progress = await db.fetch_all(
        "SELECT week, issues_completed FROM progress WHERE student_id = ? AND batch_id = ?",
        (student_id, batch_id),
    )
    completed_tasks = len({int(p["week"]) for p in progress if int(p["issues_completed"]) > 0})
    return min(100, round(completed_tasks / 4 * 100))


class UrgentRequestService:
    """Manages student-initiated urgent processing requests and admin resolution."""

    async def create_request(
        self, student_id: int, batch_id: int, request_type: str = "all", note: str | None = None
    ) -> dict:
        completion_pct = await _completion_pct(student_id, batch_id)
        if completion_pct < 50:
            raise ValueError("You need at least 50% task completion to request urgent processing.")

        existing = await db.fetch_one(
            "SELECT id FROM urgent_requests WHERE student_id = ? AND batch_id = ? AND status = 'pending'",
            (student_id, batch_id),
        )
        if existing:
            raise ValueError("You already have a pending urgent request for this batch.")

        request_id = await db.insert(
            """INSERT INTO urgent_requests (student_id, batch_id, request_type, note, status)
               VALUES (?, ?, ?, ?, 'pending')""",
            (student_id, batch_id, request_type, note),
        )
        logger.info(f"Student {student_id} filed urgent request {request_id} (type={request_type}) for batch {batch_id}")
        return {"request_id": request_id, "status": "pending"}

    async def list_requests(self, status: str | None = None) -> list[dict]:
        query = """SELECT u.*, s.first_name, s.last_name, s.email,
                          b.domain, b.batch_number
                   FROM urgent_requests u
                   JOIN students s ON u.student_id = s.id
                   JOIN batches b ON u.batch_id = b.id"""
        params: tuple = ()
        if status:
            query += " WHERE u.status = ?"
            params = (status,)
        query += " ORDER BY u.created_at ASC"
        return await db.fetch_all(query, params)

    async def _resolve(self, request_id: int, status: str, admin_note: str | None) -> dict:
        row = await db.fetch_one("SELECT * FROM urgent_requests WHERE id = ?", (request_id,))
        if not row:
            raise ValueError(f"Urgent request {request_id} not found")

        now = datetime.utcnow().isoformat()
        await db.execute(
            "UPDATE urgent_requests SET status = ?, admin_note = ?, resolved_at = ? WHERE id = ?",
            (status, admin_note, now, request_id),
        )

        info = await db.fetch_one(
            """SELECT s.first_name, s.last_name, s.email, b.domain
               FROM students s, batches b
               WHERE s.id = ? AND b.id = ?""",
            (row["student_id"], row["batch_id"]),
        )

        logger.info(f"Urgent request {request_id} marked {status}")
        return {
            "request_id": request_id,
            "status": status,
            "student_id": row["student_id"],
            "batch_id": row["batch_id"],
            "request_type": row["request_type"],
            "email": info["email"] if info else None,
            "first_name": info["first_name"] if info else None,
            "last_name": info["last_name"] if info else None,
            "domain": info["domain"] if info else None,
        }

    async def fulfill_request(self, request_id: int, admin_note: str | None = None) -> dict:
        return await self._resolve(request_id, "fulfilled", admin_note)

    async def reject_request(self, request_id: int, admin_note: str | None = None) -> dict:
        return await self._resolve(request_id, "rejected", admin_note)


# Global service instance
urgent_request_service = UrgentRequestService()
