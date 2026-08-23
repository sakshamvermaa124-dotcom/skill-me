"""
SkillMe — Admin API Routes
Protected endpoints for batch management, student enrollment,
and LinkedIn submission review. Requires X-Admin-Key header.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
import logging
from middleware.auth import require_admin
from services.batch_service import batch_service
from services.submission_service import submission_service
from services.email_service import email_service
from db.database import db
from config import settings

logger = logging.getLogger("skillme.admin")
router = APIRouter(prefix="/api/admin", tags=["admin"])


# ──────────────────────────────────────────────
# Request / Response Models
# ──────────────────────────────────────────────

class CreateBatchRequest(BaseModel):
    domain: str = Field(..., description="Domain name, e.g. 'web-dev', 'python'")
    batch_number: int = Field(..., ge=1, description="Sequential batch number")
    max_students: int = Field(30, ge=1, le=100)
    start_date: str | None = Field(None, description="ISO date (YYYY-MM-DD)")


class AddStudentRequest(BaseModel):
    student_id: int = Field(..., description="Student database ID")


class UpdateStudentStatusRequest(BaseModel):
    status: str = Field(..., description="New status: shortlisted | enrolled | completed | dropped")


class ReviewSubmissionRequest(BaseModel):
    admin_note: str | None = Field(None, max_length=500)


class BulkSubmissionRequest(BaseModel):
    submission_ids: list[int] = Field(..., min_length=1)
    admin_note: str | None = Field(None, max_length=500)


# ──────────────────────────────────────────────
# Dashboard Stats
# ──────────────────────────────────────────────

@router.get("/stats", summary="Get admin dashboard stats")
async def get_stats(_: str = Depends(require_admin)):
    """Get aggregated stats for the admin dashboard."""
    total_students = await db.fetch_one("SELECT COUNT(*) as count FROM students")
    active_batches = await db.fetch_one("SELECT COUNT(*) as count FROM batches WHERE status = 'active'")
    pending_applications = await db.fetch_one("SELECT COUNT(*) as count FROM students WHERE status = 'applied'")
    pending_submissions = await db.fetch_one("SELECT COUNT(*) as count FROM submissions WHERE status = 'pending'")

    return {
        "total_students": total_students["count"] if total_students else 0,
        "active_batches": active_batches["count"] if active_batches else 0,
        "pending_applications": pending_applications["count"] if pending_applications else 0,
        "pending_submissions": pending_submissions["count"] if pending_submissions else 0,
    }


# ──────────────────────────────────────────────
# Batch Management
# ──────────────────────────────────────────────

@router.post("/batches", summary="Create a new batch")
async def create_batch(req: CreateBatchRequest, _: str = Depends(require_admin)):
    """Creates a new batch record."""
    try:
        batch = await batch_service.create_batch(
            domain=req.domain,
            batch_number=req.batch_number,
            max_students=req.max_students,
            start_date=req.start_date,
        )
        return {"status": "created", "batch": batch}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create batch: {str(e)}")


@router.get("/batches", summary="List all batches")
async def list_batches(status: str | None = None, _: str = Depends(require_admin)):
    """List all batches with enrolled student counts, optionally filtered by status."""
    batches = await batch_service.list_batches(status=status)

    enrollment_counts = await db.fetch_all(
        "SELECT batch_id, COUNT(*) as count FROM enrollments WHERE status != 'dropped' GROUP BY batch_id"
    )
    counts_by_batch = {row["batch_id"]: row["count"] for row in enrollment_counts}
    for b in batches:
        b["enrolled_students"] = counts_by_batch.get(b["id"], 0)

    return {"batches": batches, "count": len(batches)}


@router.get("/batches/{batch_id}", summary="Get batch details")
async def get_batch(batch_id: int, _: str = Depends(require_admin)):
    """Get a specific batch with enrollment count."""
    batch = await batch_service.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    enrollment_count = await db.fetch_one(
        "SELECT COUNT(*) as count FROM enrollments WHERE batch_id = ? AND status != 'dropped'",
        (batch_id,),
    )
    batch["enrolled_students"] = enrollment_count["count"] if enrollment_count else 0

    return batch


@router.get("/batches/{batch_id}/progress", summary="Get batch progress for all students")
async def get_batch_progress(batch_id: int, _: str = Depends(require_admin)):
    """Get aggregated progress for all students in a batch."""
    batch = await batch_service.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    progress = await batch_service.get_batch_progress(batch_id)
    return {
        "batch": batch,
        "students": progress,
        "total_students": len(progress),
    }


@router.delete("/batches/{batch_id}", summary="Delete a batch and all related data")
async def delete_batch(batch_id: int, _: str = Depends(require_admin)):
    """Delete a batch entirely. Cascades to all related progress, submissions, enrollments, etc."""
    batch = await batch_service.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    try:
        await db.execute("DELETE FROM progress WHERE batch_id = ?", (batch_id,))
        await db.execute("DELETE FROM submissions WHERE batch_id = ?", (batch_id,))
        await db.execute("DELETE FROM enrollments WHERE batch_id = ?", (batch_id,))
        await db.execute("DELETE FROM certificates WHERE batch_id = ?", (batch_id,))
        await db.execute("DELETE FROM payments WHERE batch_id = ?", (batch_id,))
        await db.execute("DELETE FROM email_logs WHERE batch_id = ?", (batch_id,))
        await db.execute("DELETE FROM batches WHERE id = ?", (batch_id,))

        return {"status": "success", "message": f"Batch {batch_id} completely deleted from database."}
    except Exception as e:
        logger.error(f"Failed to delete batch {batch_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


# ──────────────────────────────────────────────
# Student Enrollment
# ──────────────────────────────────────────────

@router.post("/students/{student_id}/enroll", summary="Auto-enroll student into a dedicated batch")
async def auto_enroll_student_endpoint(
    student_id: int,
    background_tasks: BackgroundTasks,
    _: str = Depends(require_admin),
):
    """Enrolls a student into a dedicated batch for their domain and sends the offer letter."""
    try:
        result = await batch_service.auto_enroll_student(student_id)

        student = await db.fetch_one(
            "SELECT first_name, last_name, email, domain FROM students WHERE id = ?",
            (student_id,)
        )

        if student:
            background_tasks.add_task(
                email_service.send_offer_letter,
                first_name=student["first_name"],
                last_name=student["last_name"],
                email=student["email"],
                domain=result["domain"],
                batch_number=result["batch_number"],
            )

        return {"status": "enrolled", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error auto-enrolling student {student_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to auto-enroll student: {str(e)}")


@router.post("/batches/{batch_id}/students", summary="Add a student to a batch")
async def add_student_to_batch(
    batch_id: int, req: AddStudentRequest,
    background_tasks: BackgroundTasks,
    _: str = Depends(require_admin)
):
    """Enroll a student in a batch and send the offer letter email."""
    try:
        result = await batch_service.add_student_to_batch(req.student_id, batch_id)

        student = await db.fetch_one(
            "SELECT first_name, last_name, email FROM students WHERE id = ?",
            (req.student_id,)
        )
        batch = await db.fetch_one(
            "SELECT domain, batch_number FROM batches WHERE id = ?",
            (batch_id,)
        )
        if student and batch:
            background_tasks.add_task(
                email_service.send_offer_letter,
                first_name=student["first_name"],
                last_name=student["last_name"],
                email=student["email"],
                domain=batch["domain"],
                batch_number=batch["batch_number"],
            )

        return {"status": "enrolled", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error enrolling student {req.student_id} into batch {batch_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to enroll student: {str(e)}")


@router.delete("/batches/{batch_id}/students/{student_id}", summary="Remove student from batch")
async def remove_student_from_batch(
    batch_id: int, student_id: int, _: str = Depends(require_admin)
):
    """Remove a student from a batch."""
    await batch_service.remove_student_from_batch(student_id, batch_id)
    return {"status": "removed", "student_id": student_id, "batch_id": batch_id}


# ──────────────────────────────────────────────
# Student Management
# ──────────────────────────────────────────────

@router.get("/students", summary="List all students")
async def list_students(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    _: str = Depends(require_admin),
):
    """List all students, optionally filtered by status."""
    if status:
        students = await db.fetch_all(
            """SELECT s.*, e.batch_id,
               CASE WHEN p.id IS NOT NULL THEN 1 ELSE 0 END as has_paid
               FROM students s
               LEFT JOIN enrollments e ON s.id = e.student_id AND e.status != 'dropped'
               LEFT JOIN payments p ON s.id = p.student_id AND p.status = 'paid'
               WHERE s.status = ?
               ORDER BY s.created_at DESC LIMIT ? OFFSET ?""",
            (status, limit, offset),
        )
    else:
        students = await db.fetch_all(
            """SELECT s.*, e.batch_id,
               CASE WHEN p.id IS NOT NULL THEN 1 ELSE 0 END as has_paid
               FROM students s
               LEFT JOIN enrollments e ON s.id = e.student_id AND e.status != 'dropped'
               LEFT JOIN payments p ON s.id = p.student_id AND p.status = 'paid'
               ORDER BY s.created_at DESC LIMIT ? OFFSET ?""",
            (limit, offset),
        )

    total = await db.fetch_one(
        "SELECT COUNT(*) as count FROM students" + (f" WHERE status = '{status}'" if status else ""),
    )

    return {"students": students, "count": len(students), "total": total["count"] if total else 0}


@router.get("/students/{student_id}", summary="Get student details")
async def get_student(student_id: int, _: str = Depends(require_admin)):
    """Get a specific student with their enrollment and progress info."""
    student = await db.fetch_one("SELECT * FROM students WHERE id = ?", (student_id,))
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    enrollments = await db.fetch_all(
        """SELECT e.*, b.domain, b.batch_number, b.status as batch_status
           FROM enrollments e
           JOIN batches b ON e.batch_id = b.id
           WHERE e.student_id = ?""",
        (student_id,),
    )

    progress = await batch_service.get_student_progress(student_id)

    return {
        "student": student,
        "enrollments": enrollments,
        "progress": progress,
    }


@router.patch("/students/{student_id}/status", summary="Update student status")
async def update_student_status(
    student_id: int, req: UpdateStudentStatusRequest,
    background_tasks: BackgroundTasks,
    _: str = Depends(require_admin)
):
    """Update a student's application status and send lifecycle emails."""
    student = await db.fetch_one(
        "SELECT id, first_name, last_name, email FROM students WHERE id = ?",
        (student_id,)
    )
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    await db.execute(
        "UPDATE students SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (req.status, student_id),
    )

    if req.status == "shortlisted":
        student_domain = await db.fetch_one(
            "SELECT domain FROM students WHERE id = ?",
            (student_id,)
        )
        domain = student_domain["domain"] if student_domain and student_domain.get("domain") else "open-source"
        background_tasks.add_task(
            email_service.send_shortlist_notification,
            first_name=student["first_name"],
            last_name=student["last_name"],
            email=student["email"],
            domain=domain,
        )
    elif req.status == "dropped":
        active_enrollments = await db.fetch_all(
            "SELECT batch_id FROM enrollments WHERE student_id = ? AND status != 'dropped'",
            (student_id,)
        )
        for enr in active_enrollments:
            try:
                await batch_service.remove_student_from_batch(student_id, enr["batch_id"])
                logger.info(f"Removed dropped student {student_id} from batch {enr['batch_id']}")
            except Exception as e:
                logger.error(f"Error removing dropped student {student_id} from batch {enr['batch_id']}: {e}")

    return {"status": "updated", "student_id": student_id, "new_status": req.status}


@router.delete("/students/{student_id}", summary="Delete student and all associated records")
async def delete_student(student_id: int, _: str = Depends(require_admin)):
    """
    Permanently delete a student and all their associated records from the database:
    - Submissions, weekly progress, certificates, payment records, batch enrollments,
      referral codes & conversions, OTP login tokens, email logs, and any dedicated
      1-student batches created for them.

    After deletion, when this user returns they will act as a completely new user.
    """
    student = await db.fetch_one("SELECT * FROM students WHERE id = ?", (student_id,))
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    email = student["email"]

    try:
        enrolled_batches = await db.fetch_all(
            "SELECT batch_id FROM enrollments WHERE student_id = ?", (student_id,)
        )
        batch_ids = [b["batch_id"] for b in enrolled_batches]

        await db.execute("DELETE FROM submissions WHERE student_id = ?", (student_id,))
        await db.execute("DELETE FROM progress WHERE student_id = ?", (student_id,))
        await db.execute("DELETE FROM certificates WHERE student_id = ?", (student_id,))
        await db.execute("DELETE FROM payments WHERE student_id = ?", (student_id,))
        await db.execute("DELETE FROM enrollments WHERE student_id = ?", (student_id,))
        await db.execute("DELETE FROM referral_codes WHERE student_id = ?", (student_id,))
        await db.execute(
            "DELETE FROM referral_conversions WHERE referrer_student_id = ? OR referred_student_id = ? OR LOWER(referred_email) = LOWER(?)",
            (student_id, student_id, email),
        )
        await db.execute("DELETE FROM email_logs WHERE student_id = ? OR LOWER(recipient_email) = LOWER(?)", (student_id, email))
        await db.execute("DELETE FROM otp_tokens WHERE LOWER(email) = LOWER(?)", (email,))

        # Clean up any dedicated 1-student batches
        for b_id in batch_ids:
            batch = await db.fetch_one("SELECT max_students FROM batches WHERE id = ?", (b_id,))
            if batch and batch.get("max_students") == 1:
                active_enrollments = await db.fetch_one(
                    "SELECT COUNT(*) as count FROM enrollments WHERE batch_id = ?", (b_id,)
                )
                if not active_enrollments or active_enrollments["count"] == 0:
                    await db.execute("DELETE FROM progress WHERE batch_id = ?", (b_id,))
                    await db.execute("DELETE FROM submissions WHERE batch_id = ?", (b_id,))
                    await db.execute("DELETE FROM batches WHERE id = ?", (b_id,))
                    logger.info(f"Cleaned up dedicated 1-student batch {b_id}")

        try:
            await db.execute("DELETE FROM monitor_alerts WHERE student_id = ? OR LOWER(student_email) = LOWER(?)", (student_id, email))
            await db.execute("DELETE FROM frontend_errors WHERE LOWER(student_email) = LOWER(?)", (email,))
        except Exception:
            pass

        await db.execute("DELETE FROM students WHERE id = ?", (student_id,))

        logger.info(f"Admin permanently deleted student #{student_id} ({student['first_name']} {student['last_name']} - {email})")
        return {
            "status": "deleted",
            "student_id": student_id,
            "email": email,
            "message": f"Student #{student_id} ({email}) has been completely wiped from the database. When they return, they will be treated as a brand-new user."
        }
    except Exception as e:
        logger.error(f"Failed to delete student {student_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database error while deleting student: {str(e)}")


# ──────────────────────────────────────────────
# LinkedIn Submission Review Queue
# ──────────────────────────────────────────────

@router.get("/submissions", summary="List LinkedIn task submissions")
async def list_submissions(status: str | None = None, _: str = Depends(require_admin)):
    """
    List LinkedIn task submissions, optionally filtered by status
    (pending | approved | rejected). Defaults to all if omitted.
    """
    submissions = await submission_service.list_submissions(status=status)
    return {"count": len(submissions), "submissions": submissions}


@router.post("/submissions/{submission_id}/approve", summary="Approve a submission")
async def approve_submission(
    submission_id: int, req: ReviewSubmissionRequest = ReviewSubmissionRequest(),
    _: str = Depends(require_admin),
):
    """Approve a LinkedIn submission — increments the student's progress and score."""
    try:
        return await submission_service.approve_submission(submission_id, req.admin_note)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/submissions/{submission_id}/reject", summary="Reject a submission")
async def reject_submission(
    submission_id: int, req: ReviewSubmissionRequest = ReviewSubmissionRequest(),
    _: str = Depends(require_admin),
):
    """Reject a LinkedIn submission — the student can resubmit for this week."""
    try:
        return await submission_service.reject_submission(submission_id, req.admin_note)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/submissions/bulk-approve", summary="Approve multiple submissions at once")
async def bulk_approve_submissions(req: BulkSubmissionRequest, _: str = Depends(require_admin)):
    """Approve multiple submissions in one call — powers the review queue's select-all/bulk-approve action."""
    results = await submission_service.bulk_approve(req.submission_ids)
    return {"status": "done", "results": results}


@router.post("/submissions/bulk-reject", summary="Reject multiple submissions at once")
async def bulk_reject_submissions(req: BulkSubmissionRequest, _: str = Depends(require_admin)):
    """Reject multiple submissions in one call — powers the review queue's select-all/bulk-reject action."""
    results = await submission_service.bulk_reject(req.submission_ids, req.admin_note)
    return {"status": "done", "results": results}


# ──────────────────────────────────────────────
# Email
# ──────────────────────────────────────────────

class TestEmailRequest(BaseModel):
    to_email: str = Field(..., description="Email address to send the test to")


@router.post("/email/test", summary="Send a test email to verify SMTP configuration")
async def send_test_email(req: TestEmailRequest, _: str = Depends(require_admin)):
    """
    Send a test email to verify that the Brevo SMTP relay is correctly configured.
    Check config.py / .env for EMAIL_ENABLED, SMTP_USER, SMTP_PASSWORD, etc.
    """
    from config import settings
    if not settings.email_enabled:
        return {
            "status": "skipped",
            "message": "Email is disabled. Set EMAIL_ENABLED=True in .env to enable.",
        }
    success = await email_service.send_test_email(req.to_email)
    if success:
        return {"status": "sent", "to": req.to_email, "message": "Test email sent successfully!"}
    return {"status": "failed", "message": "Email send failed — check SMTP credentials in .env"}


@router.get("/email/logs", summary="Get email send history")
async def get_email_logs(
    _:           str = Depends(require_admin),
    email_type:  str | None = None,   # filter by type
    recipient:   str | None = None,   # filter by email address (partial match)
    status:      str | None = None,   # sent | failed
    limit:       int = 50,
    offset:      int = 0,
):
    """
    Return a paginated list of all emails sent (or attempted) by SkillMe.
    Useful for auditing delivery, debugging failures, and tracking communication history.
    """
    conditions = []
    params: list = []

    if email_type:
        conditions.append("email_type = ?")
        params.append(email_type)
    if recipient:
        conditions.append("recipient_email LIKE ?")
        params.append(f"%{recipient}%")
    if status:
        conditions.append("el.status = ?")
        params.append(status)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    rows = await db.fetch_all(
        f"""SELECT el.*,
                   s.first_name || ' ' || s.last_name AS student_name
            FROM email_logs el
            LEFT JOIN students s ON s.id = el.student_id
            {where}
            ORDER BY el.sent_at DESC
            LIMIT ? OFFSET ?""",
        (*params, limit, offset),
    )

    total_row = await db.fetch_one(
        f"SELECT COUNT(*) as total FROM email_logs el {where}",
        tuple(params),
    )

    return {
        "total": total_row["total"] if total_row else 0,
        "limit": limit,
        "offset": offset,
        "logs": rows,
    }


# ──────────────────────────────────────────────
# Batch Analytics
# ──────────────────────────────────────────────

@router.get("/batches/{batch_id}/analytics", summary="Batch analytics overview")
async def get_batch_analytics(batch_id: int, _: str = Depends(require_admin)):
    """
    Returns aggregated analytics for a batch:
    - Enrollment counts (total, active, dropped, completed)
    - Per-week task completion rates
    - Submission stats (pending, approved, rejected)
    - Revenue from certificate payments
    """
    batch = await db.fetch_one("SELECT * FROM batches WHERE id = ?", (batch_id,))
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    enrollment_stats = await db.fetch_one(
        """SELECT
             COUNT(*) as total,
             SUM(CASE WHEN e.status = 'enrolled' OR e.status = 'active' THEN 1 ELSE 0 END) as active,
             SUM(CASE WHEN e.status = 'dropped' THEN 1 ELSE 0 END) as dropped,
             SUM(CASE WHEN e.status = 'completed' THEN 1 ELSE 0 END) as completed
           FROM enrollments e WHERE e.batch_id = ?""",
        (batch_id,)
    )

    weekly_progress = await db.fetch_all(
        """SELECT week, SUM(issues_completed) as completed
           FROM progress WHERE batch_id = ?
           GROUP BY week ORDER BY week""",
        (batch_id,)
    )

    submission_stats = await db.fetch_one(
        """SELECT
             COUNT(*) as total_submissions,
             SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) as approved,
             SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected,
             SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending
           FROM submissions WHERE batch_id = ?""",
        (batch_id,)
    )

    revenue = await db.fetch_one(
        """SELECT
             COUNT(*) as total_payments,
             SUM(CASE WHEN status = 'paid' THEN amount ELSE 0 END) as total_paise
           FROM payments WHERE batch_id = ?""",
        (batch_id,)
    )

    student_grid = await db.fetch_all(
        """SELECT s.id, s.first_name, s.last_name,
                  e.status as enrollment_status,
                  SUM(p.issues_completed) as tasks_completed
           FROM enrollments e
           JOIN students s ON s.id = e.student_id
           LEFT JOIN progress p ON p.student_id = s.id AND p.batch_id = e.batch_id
           WHERE e.batch_id = ?
           GROUP BY s.id
           ORDER BY tasks_completed DESC""",
        (batch_id,)
    )

    return {
        "batch": dict(batch),
        "enrollments": dict(enrollment_stats) if enrollment_stats else {},
        "weekly_progress": [dict(w) for w in weekly_progress],
        "submission_stats": dict(submission_stats) if submission_stats else {},
        "revenue": {
            "total_payments": revenue["total_payments"] if revenue else 0,
            "total_inr": (revenue["total_paise"] or 0) // 100 if revenue else 0,
        },
        "student_grid": [dict(s) for s in student_grid],
    }
