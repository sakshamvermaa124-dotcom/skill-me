"""
SkillMe — Enrollment Service
Student lifecycle is simply: applied → shortlisted → enrolled (→ completed / dropped).
There is no admin-facing batch/cohort concept.

Internally, every enrollment still owns a private row in the legacy `batches` table
(one per enrollment, max_students = 1). That row's id is the key that submissions,
progress, payments, certificates and urgent requests hang off — and certificate IDs
are a hash of (student_id, batch_id), so these rows must never be renumbered or
merged, or every issued certificate would stop verifying. Treat `batch_id` as an
opaque enrollment reference; never show it to anyone.
Task content is generated dynamically per student (see services/task_service.py).
"""

import logging
from datetime import datetime, timedelta
from db.database import db

logger = logging.getLogger("skillme.enrollment")

# Picks the single enrollment that represents a student's internship. Non-dropped
# first; then (for legacy students who ended up with several) the one they paid for /
# were certified on / made progress in; newest last-resort tiebreak.
_CURRENT_ENROLLMENT_SQL = """
    SELECT e.id AS enrollment_id, e.batch_id, e.status, e.joined_at,
           e.payment_unlocked_at, b.domain, b.start_date
    FROM enrollments e
    JOIN batches b ON b.id = e.batch_id
    WHERE e.student_id = ? {extra}
    ORDER BY
      CASE WHEN e.status = 'dropped' THEN 1 ELSE 0 END,
      EXISTS (SELECT 1 FROM payments pay WHERE pay.student_id = e.student_id
              AND pay.batch_id = e.batch_id AND pay.status = 'paid') DESC,
      EXISTS (SELECT 1 FROM certificates c WHERE c.student_id = e.student_id
              AND c.batch_id = e.batch_id) DESC,
      (SELECT COUNT(*) FROM progress p WHERE p.student_id = e.student_id
              AND p.batch_id = e.batch_id AND p.issues_completed > 0) DESC,
      e.id DESC
    LIMIT 1
"""


class EnrollmentService:
    """Enrolls / drops students and resolves their (single) internship enrollment."""

    async def get_current_enrollment(self, student_id: int, include_dropped: bool = True) -> dict | None:
        """The enrollment that represents this student's internship, or None."""
        extra = "" if include_dropped else "AND e.status != 'dropped'"
        return await db.fetch_one(_CURRENT_ENROLLMENT_SQL.format(extra=extra), (student_id,))

    async def resolve_batch_id(self, student_id: int, batch_id: int | None) -> int | None:
        """
        Validate a client-supplied enrollment reference. Returns `batch_id` if it really
        belongs to this student, otherwise the student's current enrollment reference
        (covers stale bookmarks, `batch_id=0` fallbacks, and tampered URLs). None if the
        student has never been enrolled.
        """
        if batch_id:
            owned = await db.fetch_one(
                "SELECT 1 AS ok FROM enrollments WHERE student_id = ? AND batch_id = ?",
                (student_id, batch_id),
            )
            if owned:
                return batch_id
        current = await self.get_current_enrollment(student_id)
        return current["batch_id"] if current else None

    async def enroll_student(self, student_id: int) -> dict:
        """
        Enroll a student. Re-enrolling a previously dropped student reactivates their
        old enrollment so earlier progress/payments/certificates stay attached.
        """
        student = await db.fetch_one("SELECT * FROM students WHERE id = ?", (student_id,))
        if not student:
            raise ValueError(f"Student #{student_id} not found")

        active = await self.get_current_enrollment(student_id, include_dropped=False)
        if active:
            raise ValueError("Student is already enrolled")

        from services.task_service import task_service
        slug = task_service.normalize_domain_slug(student.get("domain") or "web-dev")

        dropped = await self.get_current_enrollment(student_id)
        if dropped:
            batch_id = dropped["batch_id"]
            enrollment_id = dropped["enrollment_id"]
            await db.execute(
                "UPDATE enrollments SET status = 'enrolled' WHERE id = ?", (enrollment_id,)
            )
            # Restart the 4-week window only if the old one has already run out — and only
            # for a private row (legacy shared batches would shift other students' dates).
            await db.execute(
                """UPDATE batches
                   SET status = 'active',
                       start_date = CASE WHEN start_date IS NULL
                                          OR julianday('now') - julianday(start_date) > 28
                                    THEN date('now') ELSE start_date END,
                       end_date = CASE WHEN start_date IS NULL
                                        OR julianday('now') - julianday(start_date) > 28
                                  THEN date('now', '+28 days') ELSE end_date END,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?
                     AND (SELECT COUNT(*) FROM enrollments WHERE batch_id = ?) = 1""",
                (batch_id, batch_id),
            )
            slug = dropped["domain"] or slug
            reactivated = True
        else:
            # Private per-enrollment row; batch_number only satisfies the legacy
            # UNIQUE(domain, batch_number) constraint and is never displayed.
            next_row = await db.fetch_one(
                "SELECT COALESCE(MAX(batch_number), 0) + 1 AS next_num FROM batches WHERE domain = ?",
                (slug,),
            )
            start_date = datetime.utcnow().strftime("%Y-%m-%d")
            end_date = (datetime.utcnow() + timedelta(weeks=4)).strftime("%Y-%m-%d")
            batch_id = await db.insert(
                """INSERT INTO batches (domain, batch_number, status, max_students, start_date, end_date)
                   VALUES (?, ?, 'active', 1, ?, ?)""",
                (slug, next_row["next_num"] if next_row else 1, start_date, end_date),
            )
            enrollment_id = await db.insert(
                "INSERT INTO enrollments (student_id, batch_id, status) VALUES (?, ?, 'enrolled')",
                (student_id, batch_id),
            )
            reactivated = False

        await db.execute(
            "UPDATE students SET status = 'enrolled', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (student_id,),
        )

        logger.info(
            f"{'Re-enrolled' if reactivated else 'Enrolled'} student {student['first_name']} "
            f"{student['last_name']} (id={student_id}) in {slug}"
        )
        return {
            "enrollment_id": enrollment_id,
            "student_id": student_id,
            "batch_id": batch_id,
            "domain": slug,
            "reactivated": reactivated,
        }

    async def drop_student(self, student_id: int) -> int:
        """Mark all of a student's active enrollments as dropped. Returns how many."""
        rows = await db.fetch_all(
            "SELECT id FROM enrollments WHERE student_id = ? AND status != 'dropped'",
            (student_id,),
        )
        if rows:
            await db.execute(
                "UPDATE enrollments SET status = 'dropped' WHERE student_id = ? AND status != 'dropped'",
                (student_id,),
            )
        return len(rows)

    async def get_student_progress(self, student_id: int) -> list[dict]:
        """All weekly progress records for a student."""
        return await db.fetch_all(
            """SELECT p.*, b.domain
               FROM progress p
               JOIN batches b ON p.batch_id = b.id
               WHERE p.student_id = ?
               ORDER BY p.week""",
            (student_id,),
        )


# Global service instance
enrollment_service = EnrollmentService()
