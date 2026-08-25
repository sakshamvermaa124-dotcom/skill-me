"""
SkillMe — Urgent Request Service
Handles student requests for 24h expedited certificate/LOR/portfolio processing.

Students below the 50% completion threshold don't get direct payment access —
they file a request here instead. If an admin fulfills it, payment unlocks
for that student+batch (see fulfill_request / _resolve) even at 0% completion.
Students at/above 50% never need this — payment is already visible to them.
"""

import logging
from datetime import datetime

from db.database import db

logger = logging.getLogger("skillme.urgent_request")


class UrgentRequestService:
    """Manages student-initiated urgent processing requests and admin resolution."""

    async def create_request(
        self, student_id: int, batch_id: int, request_type: str = "all", note: str | None = None
    ) -> dict:
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
        result = await self._resolve(request_id, "fulfilled", admin_note)
        await db.execute(
            "UPDATE enrollments SET payment_unlocked_at = CURRENT_TIMESTAMP WHERE student_id = ? AND batch_id = ?",
            (result["student_id"], result["batch_id"]),
        )
        logger.info(f"Payment unlocked for student {result['student_id']} batch {result['batch_id']} via urgent request {request_id}")
        return result

    async def reject_request(self, request_id: int, admin_note: str | None = None) -> dict:
        return await self._resolve(request_id, "rejected", admin_note)


# Global service instance
urgent_request_service = UrgentRequestService()
