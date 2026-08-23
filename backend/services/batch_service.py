"""
SkillMe — Batch Service
Manages the batch/cohort lifecycle: creation and student enrollment.
Task content is generated dynamically per student (see services/task_service.py
and routes/tasks.py) — no per-student task rows are stored here.
"""

import logging
from datetime import datetime, timedelta
from db.database import db

logger = logging.getLogger("skillme.batch")


class BatchService:
    """Manages the batch lifecycle."""

    # ──────────────────────────────────────────────
    # Batch CRUD
    # ──────────────────────────────────────────────

    async def create_batch(
        self,
        domain: str,
        batch_number: int,
        max_students: int = 30,
        start_date: str | None = None,
    ) -> dict:
        """Create a new batch record."""
        existing = await db.fetch_one(
            "SELECT id FROM batches WHERE domain = ? AND batch_number = ?",
            (domain, batch_number),
        )
        if existing:
            raise ValueError(f"Batch {domain} #{batch_number} already exists (id={existing['id']})")

        if not start_date:
            start_date = datetime.utcnow().strftime("%Y-%m-%d")
        end_date = (
            datetime.strptime(start_date, "%Y-%m-%d") + timedelta(weeks=4)
        ).strftime("%Y-%m-%d")

        batch_id = await db.insert(
            """INSERT INTO batches (domain, batch_number, status, max_students, start_date, end_date)
               VALUES (?, ?, 'active', ?, ?, ?)""",
            (domain, batch_number, max_students, start_date, end_date),
        )

        logger.info(f"Created batch: {domain} #{batch_number} (id={batch_id})")

        return {
            "id": batch_id,
            "domain": domain,
            "batch_number": batch_number,
            "status": "active",
            "start_date": start_date,
            "end_date": end_date,
        }

    async def get_batch(self, batch_id: int) -> dict | None:
        """Get a batch by ID."""
        return await db.fetch_one("SELECT * FROM batches WHERE id = ?", (batch_id,))

    async def list_batches(self, status: str | None = None) -> list[dict]:
        """List all batches, optionally filtered by status."""
        if status:
            return await db.fetch_all(
                "SELECT * FROM batches WHERE status = ? ORDER BY created_at DESC", (status,)
            )
        return await db.fetch_all("SELECT * FROM batches ORDER BY created_at DESC")

    async def update_batch_status(self, batch_id: int, status: str) -> bool:
        """Update batch status."""
        await db.execute(
            "UPDATE batches SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, batch_id),
        )
        return True

    # ──────────────────────────────────────────────
    # Student Enrollment
    # ──────────────────────────────────────────────

    async def add_student_to_batch(self, student_id: int, batch_id: int) -> dict:
        """Enroll a student in a batch."""
        student = await db.fetch_one("SELECT * FROM students WHERE id = ?", (student_id,))
        if not student:
            raise ValueError(f"Student {student_id} not found")

        batch = await db.fetch_one("SELECT * FROM batches WHERE id = ?", (batch_id,))
        if not batch:
            raise ValueError(f"Batch {batch_id} not found")

        enrolled_count = await db.fetch_one(
            "SELECT COUNT(*) as count FROM enrollments WHERE batch_id = ? AND status != 'dropped'",
            (batch_id,),
        )
        if enrolled_count and enrolled_count["count"] >= batch["max_students"]:
            raise ValueError(f"Batch {batch_id} is full ({batch['max_students']} students max)")

        existing = await db.fetch_one(
            "SELECT id FROM enrollments WHERE student_id = ? AND batch_id = ?",
            (student_id, batch_id),
        )
        if existing:
            raise ValueError(f"Student {student_id} is already enrolled in batch {batch_id}")

        enrollment_id = await db.insert(
            "INSERT INTO enrollments (student_id, batch_id, status) VALUES (?, ?, 'enrolled')",
            (student_id, batch_id),
        )

        await db.execute(
            "UPDATE students SET status = 'enrolled', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (student_id,),
        )

        logger.info(
            f"Enrolled student {student['first_name']} {student['last_name']} "
            f"(id={student_id}) in batch {batch['domain']} #{batch['batch_number']}"
        )

        return {
            "enrollment_id": enrollment_id,
            "student_id": student_id,
            "batch_id": batch_id,
        }

    async def auto_enroll_student(self, student_id: int) -> dict:
        """
        Enroll a student into a dedicated batch for their domain (created on demand),
        without any external repo/collaborator setup.
        """
        student = await db.fetch_one("SELECT * FROM students WHERE id = ?", (student_id,))
        if not student:
            raise ValueError(f"Student #{student_id} not found")

        existing = await db.fetch_one(
            """SELECT e.id, e.batch_id, b.domain, b.batch_number
               FROM enrollments e
               JOIN batches b ON e.batch_id = b.id
               WHERE e.student_id = ? AND e.status != 'dropped'""",
            (student_id,),
        )
        if existing:
            raise ValueError(
                f"Student is already enrolled in {existing['domain']} Batch #{existing['batch_number']}"
            )

        raw_domain = student.get("domain") or "web-dev"
        from services.task_service import task_service
        slug = task_service.normalize_domain_slug(raw_domain)

        batch_count_row = await db.fetch_one(
            "SELECT COALESCE(MAX(batch_number), 0) + 1 AS next_batch FROM batches WHERE domain = ?",
            (slug,),
        )
        batch_number = batch_count_row["next_batch"] if batch_count_row else 1

        start_date = datetime.utcnow().strftime("%Y-%m-%d")
        end_date = (datetime.utcnow() + timedelta(weeks=4)).strftime("%Y-%m-%d")

        batch_id = await db.insert(
            """INSERT INTO batches (domain, batch_number, status, max_students, start_date, end_date)
               VALUES (?, ?, 'active', 1, ?, ?)""",
            (slug, batch_number, start_date, end_date),
        )

        enrollment_id = await db.insert(
            "INSERT INTO enrollments (student_id, batch_id, status) VALUES (?, ?, 'enrolled')",
            (student_id, batch_id),
        )

        await db.execute(
            "UPDATE students SET status = 'enrolled', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (student_id,),
        )

        logger.info(
            f"Auto-enrolled student {student['first_name']} {student['last_name']} "
            f"(id={student_id}) into dedicated batch {slug} #{batch_number}"
        )

        return {
            "enrollment_id": enrollment_id,
            "student_id": student_id,
            "batch_id": batch_id,
            "domain": slug,
            "batch_number": batch_number,
        }

    async def remove_student_from_batch(self, student_id: int, batch_id: int) -> bool:
        """Remove a student from a batch."""
        await db.execute(
            "UPDATE enrollments SET status = 'dropped' WHERE student_id = ? AND batch_id = ?",
            (student_id, batch_id),
        )
        return True

    # ──────────────────────────────────────────────
    # Progress Tracking
    # ──────────────────────────────────────────────

    async def get_batch_progress(self, batch_id: int) -> list[dict]:
        """Get aggregated progress for all students in a batch."""
        return await db.fetch_all(
            """SELECT
                 s.id as student_id,
                 s.first_name,
                 s.last_name,
                 e.status as enrollment_status,
                 COALESCE(SUM(p.issues_completed), 0) as total_completed,
                 COALESCE(SUM(p.score), 0) as total_score
               FROM enrollments e
               JOIN students s ON e.student_id = s.id
               LEFT JOIN progress p ON p.student_id = s.id AND p.batch_id = e.batch_id
               WHERE e.batch_id = ?
               GROUP BY s.id
               ORDER BY total_score DESC""",
            (batch_id,),
        )

    async def get_student_progress(self, student_id: int) -> list[dict]:
        """Get all progress records for a student across all batches."""
        return await db.fetch_all(
            """SELECT
                 p.*, b.domain, b.batch_number
               FROM progress p
               JOIN batches b ON p.batch_id = b.id
               WHERE p.student_id = ?
               ORDER BY b.domain, p.week""",
            (student_id,),
        )


# Global service instance
batch_service = BatchService()
