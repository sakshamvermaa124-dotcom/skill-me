"""
SkillMe — Admin API Routes
Protected endpoints for student shortlisting/enrollment
and LinkedIn submission review. Requires X-Admin-Key header.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
import logging
from middleware.auth import require_admin
from services.enrollment_service import enrollment_service
from services.submission_service import submission_service, SCORE_PER_APPROVAL
from services.urgent_request_service import urgent_request_service
from services.email_service import email_service
from db.database import db
from config import settings

logger = logging.getLogger("skillme.admin")
router = APIRouter(prefix="/api/admin", tags=["admin"])


# ──────────────────────────────────────────────
# Request / Response Models
# ──────────────────────────────────────────────

# applied → shortlisted → enrolled → completed, or dropped at any point.
STUDENT_STATUSES = ("applied", "shortlisted", "enrolled", "completed", "dropped")
STUDENTS_PAGE_SIZE = 15
STUDENTS_MAX_PAGE_SIZE = 100


class UpdateStudentStatusRequest(BaseModel):
    status: str = Field(..., description="New status: applied | shortlisted | enrolled | completed | dropped")


class ReviewSubmissionRequest(BaseModel):
    admin_note: str | None = Field(None, max_length=500)


class BulkSubmissionRequest(BaseModel):
    submission_ids: list[int] = Field(..., min_length=1)
    admin_note: str | None = Field(None, max_length=500)


class SendAnnouncementRequest(BaseModel):
    status: str = Field("enrolled", description="Target student status filter (ignored if student_ids given)")
    student_ids: list[int] | None = Field(None, description="Explicit recipient list, overrides the status filter")


# Registry of one-off / recurring announcements admins can send from the panel.
# `fn` is the email_service method name — resolved dynamically at send time (not
# bound at import time) so it always dispatches through the current email_service.
ANNOUNCEMENTS = {
    "submission-flow-update": {
        "label": "Submission Flow Update (GitHub PRs → LinkedIn)",
        "fn": "send_submission_flow_update",
        "email_type": "submission_flow_update",
    },
}


# ──────────────────────────────────────────────
# Dashboard Stats
# ──────────────────────────────────────────────

@router.get("/stats", summary="Get admin dashboard stats")
async def get_stats(_: str = Depends(require_admin)):
    """Get aggregated stats for the admin dashboard (single round-trip)."""
    row = await db.fetch_one(
        f"""SELECT
             (SELECT COUNT(*) FROM students) AS total_students,
             (SELECT COUNT(*) FROM students WHERE status = 'applied') AS pending_applications,
             (SELECT COUNT(*) FROM students WHERE status = 'shortlisted') AS shortlisted_students,
             (SELECT COUNT(*) FROM students WHERE status = 'enrolled') AS enrolled_students,
             (SELECT COUNT(DISTINCT student_id) FROM payments
                WHERE status = 'paid' AND {REAL_PAYMENT_SQL}) AS total_alumni,
             (SELECT COUNT(*) FROM submissions WHERE status = 'pending') AS pending_submissions,
             (SELECT COUNT(*) FROM urgent_requests WHERE status = 'pending') AS pending_urgent_requests"""
    ) or {}
    keys = ("total_students", "pending_applications", "shortlisted_students", "enrolled_students",
            "total_alumni", "pending_submissions", "pending_urgent_requests")
    return {k: row.get(k) or 0 for k in keys}


# ──────────────────────────────────────────────
# Enrollment
# ──────────────────────────────────────────────

async def _enroll_and_notify(student_id: int, background_tasks: BackgroundTasks) -> dict:
    """Enroll a student and queue the offer letter. Raises ValueError on invalid state."""
    result = await enrollment_service.enroll_student(student_id)
    student = await db.fetch_one(
        "SELECT first_name, last_name, email FROM students WHERE id = ?", (student_id,)
    )
    if student:
        background_tasks.add_task(
            email_service.send_offer_letter,
            first_name=student["first_name"],
            last_name=student["last_name"],
            email=student["email"],
            domain=result["domain"],
        )
    return result


@router.post("/students/{student_id}/enroll", summary="Enroll a student")
async def enroll_student_endpoint(
    student_id: int,
    background_tasks: BackgroundTasks,
    _: str = Depends(require_admin),
):
    """Enrolls a student (applied, shortlisted or previously dropped) and sends the offer letter."""
    try:
        result = await _enroll_and_notify(student_id, background_tasks)
        return {"status": "enrolled", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error enrolling student {student_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to enroll student: {str(e)}")


# ──────────────────────────────────────────────
# Student Management
# ──────────────────────────────────────────────

# Correlated subquery returning the student's current enrollment reference
# (same ordering as enrollment_service.get_current_enrollment). Needed by the
# admin "Certificate" action; never rendered.
_CURRENT_BATCH_ID_SUBQUERY = """(
    SELECT e.batch_id FROM enrollments e
    WHERE e.student_id = s.id
    ORDER BY CASE WHEN e.status = 'dropped' THEN 1 ELSE 0 END,
             EXISTS (SELECT 1 FROM payments pay WHERE pay.student_id = e.student_id
                     AND pay.batch_id = e.batch_id AND pay.status = 'paid') DESC,
             EXISTS (SELECT 1 FROM certificates c WHERE c.student_id = e.student_id
                     AND c.batch_id = e.batch_id) DESC,
             (SELECT COUNT(*) FROM progress p WHERE p.student_id = e.student_id
                     AND p.batch_id = e.batch_id AND p.issues_completed > 0) DESC,
             e.id DESC
    LIMIT 1
)"""


@router.get("/students", summary="List students (server-side paginated)")
async def list_students(
    status: str | None = None,
    q: str | None = None,
    paid: bool | None = None,
    page: int | None = None,
    limit: int = STUDENTS_PAGE_SIZE,
    offset: int = 0,
    _: str = Depends(require_admin),
):
    """
    List students, newest first, `limit` (default 15) per page.
    - status: applied | shortlisted | enrolled | completed | dropped
    - q:      case-insensitive search over name, email, college and domain
    - paid:   true → alumni (have a paid certificate), false → everyone else
    - page:   1-based page number (takes precedence over offset)
    """
    limit = max(1, min(limit, STUDENTS_MAX_PAGE_SIZE))
    if page is not None:
        offset = (max(1, page) - 1) * limit
    offset = max(0, offset)

    conditions: list[str] = []
    params: list = []
    if status:
        conditions.append("s.status = ?")
        params.append(status)
    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        conditions.append(
            "(LOWER(s.first_name || ' ' || s.last_name) LIKE ? OR LOWER(s.email) LIKE ?"
            " OR LOWER(COALESCE(s.college, '')) LIKE ? OR LOWER(COALESCE(s.domain, '')) LIKE ?)"
        )
        params.extend([like, like, like, like])
    paid_exists = "EXISTS (SELECT 1 FROM payments p WHERE p.student_id = s.id AND p.status = 'paid')"
    if paid is True:
        conditions.append(paid_exists)
    elif paid is False:
        conditions.append(f"NOT {paid_exists}")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    students = await db.fetch_all(
        f"""SELECT s.id, s.first_name, s.last_name, s.email, s.phone, s.github_username,
                   s.linkedin_url, s.college, s.year_of_study, s.domain, s.status,
                   s.created_at, s.updated_at,
                   {_CURRENT_BATCH_ID_SUBQUERY} AS batch_id,
                   CASE WHEN {paid_exists} THEN 1 ELSE 0 END AS has_paid,
                   (SELECT p.updated_at FROM payments p
                     WHERE p.student_id = s.id AND p.status = 'paid'
                     ORDER BY p.updated_at DESC LIMIT 1) AS paid_at
            FROM students s
            {where}
            ORDER BY s.created_at DESC, s.id DESC
            LIMIT ? OFFSET ?""",
        (*params, limit, offset),
    )
    total_row = await db.fetch_one(f"SELECT COUNT(*) AS count FROM students s {where}", tuple(params))
    total = int(total_row["count"]) if total_row and total_row["count"] is not None else 0

    return {
        "students": students,
        "count": len(students),
        "total": total,
        "limit": limit,
        "offset": offset,
        "page": offset // limit + 1,
        "total_pages": max(1, -(-total // limit)),
    }


@router.get("/students/{student_id}", summary="Get student details")
async def get_student(student_id: int, _: str = Depends(require_admin)):
    """Get a specific student with their enrollment and progress info."""
    student = await db.fetch_one("SELECT * FROM students WHERE id = ?", (student_id,))
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    return {
        "student": student,
        "enrollment": await enrollment_service.get_current_enrollment(student_id),
        "progress": await enrollment_service.get_student_progress(student_id),
    }


@router.patch("/students/{student_id}/status", summary="Update student status")
async def update_student_status(
    student_id: int, req: UpdateStudentStatusRequest,
    background_tasks: BackgroundTasks,
    _: str = Depends(require_admin)
):
    """Update a student's application status and send lifecycle emails."""
    new_status = (req.status or "").strip().lower()
    if new_status not in STUDENT_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{req.status}'. Allowed: {', '.join(STUDENT_STATUSES)}",
        )

    student = await db.fetch_one(
        "SELECT id, first_name, last_name, email, domain, status FROM students WHERE id = ?",
        (student_id,)
    )
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    active = await enrollment_service.get_current_enrollment(student_id, include_dropped=False)

    # "enrolled" must go through the enrollment flow so the student actually gets an
    # enrollment (tasks, submissions, certificate) — never just a bare status flip.
    if new_status == "enrolled" and not active:
        try:
            await _enroll_and_notify(student_id, background_tasks)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"status": "updated", "student_id": student_id, "new_status": "enrolled"}

    if new_status in ("applied", "shortlisted") and active:
        raise HTTPException(
            status_code=400,
            detail="Student is already enrolled. Drop them first if you need to move them back.",
        )

    await db.execute(
        "UPDATE students SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (new_status, student_id),
    )

    if new_status == "shortlisted" and student["status"] != "shortlisted":
        background_tasks.add_task(
            email_service.send_shortlist_notification,
            first_name=student["first_name"],
            last_name=student["last_name"],
            email=student["email"],
            domain=student.get("domain") or "open-source",
        )
    elif new_status == "dropped":
        dropped = await enrollment_service.drop_student(student_id)
        if dropped:
            logger.info(f"Dropped student {student_id} ({dropped} enrollment(s) deactivated)")

    return {"status": "updated", "student_id": student_id, "new_status": new_status}


@router.delete("/students/{student_id}", summary="Delete student and all associated records")
async def delete_student(student_id: int, _: str = Depends(require_admin)):
    """
    Permanently delete a student and all their associated records from the database:
    - Submissions, weekly progress, certificates, payment records, enrollments,
      urgent requests, referral codes & conversions, OTP login tokens and email logs.

    After deletion, when this user returns they will act as a completely new user.
    """
    student = await db.fetch_one("SELECT * FROM students WHERE id = ?", (student_id,))
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    email = student["email"]

    try:
        enrolled = await db.fetch_all(
            "SELECT batch_id FROM enrollments WHERE student_id = ?", (student_id,)
        )
        batch_ids = {row["batch_id"] for row in enrolled}

        await db.execute("DELETE FROM submissions WHERE student_id = ?", (student_id,))
        await db.execute("DELETE FROM progress WHERE student_id = ?", (student_id,))
        await db.execute("DELETE FROM certificates WHERE student_id = ?", (student_id,))
        await db.execute("DELETE FROM payments WHERE student_id = ?", (student_id,))
        await db.execute("DELETE FROM urgent_requests WHERE student_id = ?", (student_id,))
        await db.execute("DELETE FROM enrollments WHERE student_id = ?", (student_id,))
        await db.execute("DELETE FROM referral_codes WHERE student_id = ?", (student_id,))
        await db.execute(
            "DELETE FROM referral_conversions WHERE referrer_student_id = ? OR referred_student_id = ? OR LOWER(referred_email) = LOWER(?)",
            (student_id, student_id, email),
        )
        await db.execute("DELETE FROM email_logs WHERE student_id = ? OR LOWER(recipient_email) = LOWER(?)", (student_id, email))
        await db.execute("DELETE FROM otp_tokens WHERE LOWER(email) = LOWER(?)", (email,))

        # Remove the student's private enrollment rows once nothing else references them
        for b_id in batch_ids:
            refs = await db.fetch_one(
                """SELECT (SELECT COUNT(*) FROM enrollments WHERE batch_id = ?)
                        + (SELECT COUNT(*) FROM certificates WHERE batch_id = ?)
                        + (SELECT COUNT(*) FROM payments WHERE batch_id = ?) AS refs""",
                (b_id, b_id, b_id),
            )
            if not refs or refs["refs"] == 0:
                await db.execute("DELETE FROM progress WHERE batch_id = ?", (b_id,))
                await db.execute("DELETE FROM submissions WHERE batch_id = ?", (b_id,))
                await db.execute("DELETE FROM urgent_requests WHERE batch_id = ?", (b_id,))
                await db.execute("UPDATE email_logs SET batch_id = NULL WHERE batch_id = ?", (b_id,))
                await db.execute("DELETE FROM batches WHERE id = ?", (b_id,))

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


async def _notify_task_approved(background_tasks: BackgroundTasks, submission_id: int, admin_note: str | None) -> None:
    """Look up the submission's student and queue a congratulations email."""
    info = await db.fetch_one(
        """SELECT sub.week, s.first_name, s.last_name, s.email,
                  COALESCE(b.domain, s.domain) AS domain
           FROM submissions sub
           JOIN students s ON sub.student_id = s.id
           LEFT JOIN batches b ON sub.batch_id = b.id
           WHERE sub.id = ?""",
        (submission_id,),
    )
    if not info:
        return
    background_tasks.add_task(
        email_service.send_task_approved,
        first_name=info["first_name"],
        last_name=info["last_name"],
        email=info["email"],
        domain=info["domain"],
        week=info["week"],
        score=SCORE_PER_APPROVAL,
        admin_note=admin_note,
    )


@router.post("/submissions/{submission_id}/approve", summary="Approve a submission")
async def approve_submission(
    submission_id: int, req: ReviewSubmissionRequest = ReviewSubmissionRequest(),
    background_tasks: BackgroundTasks = None,
    _: str = Depends(require_admin),
):
    """Approve a LinkedIn submission — increments the student's progress and score, and emails the student."""
    try:
        result = await submission_service.approve_submission(submission_id, req.admin_note)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if not result.get("already"):
        await _notify_task_approved(background_tasks, submission_id, req.admin_note)
    return result


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
async def bulk_approve_submissions(
    req: BulkSubmissionRequest, background_tasks: BackgroundTasks, _: str = Depends(require_admin)
):
    """Approve multiple submissions in one call — powers the review queue's select-all/bulk-approve action."""
    results = await submission_service.bulk_approve(req.submission_ids)
    for r in results:
        if r.get("status") == "approved" and not r.get("already"):
            await _notify_task_approved(background_tasks, r["submission_id"], None)
    return {"status": "done", "results": results}


@router.post("/submissions/bulk-reject", summary="Reject multiple submissions at once")
async def bulk_reject_submissions(req: BulkSubmissionRequest, _: str = Depends(require_admin)):
    """Reject multiple submissions in one call — powers the review queue's select-all/bulk-reject action."""
    results = await submission_service.bulk_reject(req.submission_ids, req.admin_note)
    return {"status": "done", "results": results}


# ──────────────────────────────────────────────
# Urgent Request Review Queue
# ──────────────────────────────────────────────

@router.get("/urgent-requests", summary="List urgent processing requests")
async def list_urgent_requests(status: str | None = None, _: str = Depends(require_admin)):
    """List urgent requests, optionally filtered by status (pending | fulfilled | rejected)."""
    requests = await urgent_request_service.list_requests(status=status)
    return {"count": len(requests), "requests": requests}


@router.post("/urgent-requests/{request_id}/fulfill", summary="Fulfill an urgent request")
async def fulfill_urgent_request(
    request_id: int, req: ReviewSubmissionRequest = ReviewSubmissionRequest(),
    background_tasks: BackgroundTasks = None,
    _: str = Depends(require_admin),
):
    """Mark an urgent request as fulfilled and email the student."""
    try:
        result = await urgent_request_service.fulfill_request(request_id, req.admin_note)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if result.get("email"):
        background_tasks.add_task(
            email_service.send_urgent_request_fulfilled,
            first_name=result["first_name"],
            last_name=result["last_name"],
            email=result["email"],
            domain=result["domain"],
            request_type=result["request_type"],
        )
    return result


@router.post("/urgent-requests/{request_id}/reject", summary="Reject an urgent request")
async def reject_urgent_request(
    request_id: int, req: ReviewSubmissionRequest = ReviewSubmissionRequest(),
    _: str = Depends(require_admin),
):
    """Reject an urgent request."""
    try:
        return await urgent_request_service.reject_request(request_id, req.admin_note)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ──────────────────────────────────────────────
# Announcements
# ──────────────────────────────────────────────

@router.get("/announcements", summary="List available announcements")
async def list_announcements(_: str = Depends(require_admin)):
    """List announcement templates admins can send from the panel."""
    return {
        "announcements": [
            {"key": key, "label": ann["label"]} for key, ann in ANNOUNCEMENTS.items()
        ]
    }


@router.get("/announcements/{key}/preview", summary="Preview recipients for an announcement")
async def preview_announcement(key: str, status: str = "enrolled", _: str = Depends(require_admin)):
    """Preview who would receive this announcement before sending it."""
    if key not in ANNOUNCEMENTS:
        raise HTTPException(status_code=404, detail=f"Unknown announcement '{key}'")

    rows = await db.fetch_all(
        "SELECT id, first_name, last_name, email, domain FROM students WHERE status = ? ORDER BY first_name",
        (status,),
    )
    return {"count": len(rows), "students": rows}


@router.post("/announcements/{key}/send", summary="Send an announcement email")
async def send_announcement(
    key: str, req: SendAnnouncementRequest,
    background_tasks: BackgroundTasks,
    _: str = Depends(require_admin),
):
    """
    Send an announcement email to students.
    - If `student_ids` is provided, only those students are emailed.
    - Otherwise, all students matching `status` (default 'enrolled') are emailed.
    Emails are dispatched in the background so the API responds immediately.
    """
    if key not in ANNOUNCEMENTS:
        raise HTTPException(status_code=404, detail=f"Unknown announcement '{key}'")
    ann = ANNOUNCEMENTS[key]

    if req.student_ids:
        placeholders = ",".join("?" for _id in req.student_ids)
        rows = await db.fetch_all(
            f"SELECT id, first_name, last_name, email, domain FROM students WHERE id IN ({placeholders})",
            tuple(req.student_ids),
        )
    else:
        rows = await db.fetch_all(
            "SELECT id, first_name, last_name, email, domain FROM students WHERE status = ?",
            (req.status,),
        )

    if not rows:
        return {"status": "no_targets", "message": "No matching students found.", "sent_to": []}

    async def _fire_emails():
        import asyncio
        send_fn = getattr(email_service, ann["fn"])
        for r in rows:
            try:
                await send_fn(
                    first_name=r["first_name"],
                    last_name=r["last_name"],
                    email=r["email"],
                    domain=r.get("domain") or "web-dev",
                )
                logger.info(f"Announcement '{key}' sent → {r['email']} (student_id={r['id']})")
            except Exception as exc:
                logger.error(f"Failed to send announcement '{key}' to {r['email']}: {exc}")
            await asyncio.sleep(1)  # avoid tripping SMTP connection rate limits

    background_tasks.add_task(_fire_emails)

    sent_to = [
        {"student_id": r["id"], "name": f"{r['first_name']} {r['last_name']}", "email": r["email"]}
        for r in rows
    ]
    return {
        "status": "dispatched",
        "message": f"Announcement is being sent to {len(rows)} student(s) in the background.",
        "sent_to": sent_to,
    }


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


EMAIL_LOGS_PAGE_SIZE = 50
EMAIL_LOGS_MAX_PAGE_SIZE = 200


@router.get("/email/logs", summary="Get email send history")
async def get_email_logs(
    _:           str = Depends(require_admin),
    email_type:  str | None = None,   # filter by type
    recipient:   str | None = None,   # filter by email address (partial match)
    status:      str | None = None,   # sent | failed
    page:        int | None = None,   # 1-based page number (takes precedence over offset)
    limit:       int = EMAIL_LOGS_PAGE_SIZE,
    offset:      int = 0,
):
    """
    Return a paginated list of all emails sent (or attempted) by SkillMe.
    Useful for auditing delivery, debugging failures, and tracking communication history.
    """
    limit = max(1, min(limit, EMAIL_LOGS_MAX_PAGE_SIZE))
    if page is not None:
        offset = (max(1, page) - 1) * limit
    offset = max(0, offset)

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
    total = int(total_row["total"]) if total_row and total_row["total"] is not None else 0

    return {
        "logs": rows,
        "count": len(rows),
        "total": total,
        "limit": limit,
        "offset": offset,
        "page": offset // limit + 1,
        "total_pages": max(1, -(-total // limit)),
    }


@router.get("/email/directory", summary="Per-student email contact directory")
async def get_email_directory(
    _:  str = Depends(require_admin),
    q:  str | None = None,     # search by name, email or domain
    page: int | None = None,
    limit: int = STUDENTS_PAGE_SIZE,
    offset: int = 0,
):
    """
    One row per student showing their email address plus a rollup of their send
    history (last email sent, last status, counts of delivered/opened/bounced) —
    the "who have we emailed, and did it land" view, as opposed to /email/logs'
    raw chronological log of every individual send.
    """
    limit = max(1, min(limit, STUDENTS_MAX_PAGE_SIZE))
    if page is not None:
        offset = (max(1, page) - 1) * limit
    offset = max(0, offset)

    conditions: list[str] = []
    params: list = []
    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        conditions.append(
            "(LOWER(s.first_name || ' ' || s.last_name) LIKE ? OR LOWER(s.email) LIKE ?"
            " OR LOWER(COALESCE(s.domain, '')) LIKE ?)"
        )
        params.extend([like, like, like])
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    rows = await db.fetch_all(
        f"""SELECT
              s.id, s.first_name, s.last_name, s.email, s.domain, s.status,
              (SELECT COUNT(*) FROM email_logs el WHERE el.student_id = s.id) AS emails_sent,
              (SELECT COUNT(*) FROM email_logs el WHERE el.student_id = s.id AND el.status = 'failed') AS emails_failed,
              (SELECT COUNT(*) FROM email_logs el WHERE el.student_id = s.id AND el.bounced_at IS NOT NULL) AS emails_bounced,
              (SELECT el2.email_type FROM email_logs el2 WHERE el2.student_id = s.id
                 ORDER BY el2.sent_at DESC LIMIT 1) AS last_email_type,
              (SELECT el3.sent_at FROM email_logs el3 WHERE el3.student_id = s.id
                 ORDER BY el3.sent_at DESC LIMIT 1) AS last_email_at
            FROM students s
            {where}
            ORDER BY s.created_at DESC, s.id DESC
            LIMIT ? OFFSET ?""",
        (*params, limit, offset),
    )
    total_row = await db.fetch_one(f"SELECT COUNT(*) AS count FROM students s {where}", tuple(params))
    total = int(total_row["count"]) if total_row and total_row["count"] is not None else 0

    return {
        "students": rows,
        "count": len(rows),
        "total": total,
        "limit": limit,
        "offset": offset,
        "page": offset // limit + 1,
        "total_pages": max(1, -(-total // limit)),
    }


@router.get("/email/stats", summary="Aggregate email deliverability & engagement stats")
async def get_email_stats(_: str = Depends(require_admin)):
    """
    Aggregate counts across all logged emails: sent/failed, delivered, opened,
    clicked, bounced and marked-as-spam. Populated from Brevo webhook events
    (see /api/webhooks/brevo) — rows sent before that webhook was configured
    will show as sent/failed only, with no engagement data.
    """
    row = await db.fetch_one(
        """SELECT
             COUNT(*)                                   AS total,
             SUM(CASE WHEN status = 'sent'   THEN 1 ELSE 0 END) AS sent,
             SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
             SUM(CASE WHEN delivered_at      IS NOT NULL THEN 1 ELSE 0 END) AS delivered,
             SUM(CASE WHEN opened_at         IS NOT NULL THEN 1 ELSE 0 END) AS opened,
             SUM(CASE WHEN clicked_at        IS NOT NULL THEN 1 ELSE 0 END) AS clicked,
             SUM(CASE WHEN bounced_at        IS NOT NULL THEN 1 ELSE 0 END) AS bounced,
             SUM(CASE WHEN spam_reported_at  IS NOT NULL THEN 1 ELSE 0 END) AS spam_reported,
             SUM(CASE WHEN unsubscribed_at   IS NOT NULL THEN 1 ELSE 0 END) AS unsubscribed
           FROM email_logs"""
    )
    return row or {}


# ──────────────────────────────────────────────
# Task Reminders
# ──────────────────────────────────────────────

@router.get("/reminders/preview", summary="Preview inactive students who would receive reminders")
async def preview_inactive_students(_: str = Depends(require_admin)):
    """Returns a list of enrolled students who are behind on tasks and eligible for a reminder email."""
    from services.reminder_service import get_inactive_students
    students = await get_inactive_students()
    return {"count": len(students), "students": students}


class SendRemindersRequest(BaseModel):
    student_ids: list[int] | None = Field(None, description="Optional: send only to these student IDs")


@router.post("/reminders/send", summary="Send task reminder emails to inactive students")
async def send_task_reminders(
    req: SendRemindersRequest,
    background_tasks: BackgroundTasks,
    _: str = Depends(require_admin),
):
    """Trigger task reminder emails. If student_ids provided, only those students get emailed."""
    from services.reminder_service import get_inactive_students, send_reminders

    inactive = await get_inactive_students()

    if req.student_ids:
        target_ids = set(req.student_ids)
        inactive = [s for s in inactive if int(s["student_id"]) in target_ids]

    if not inactive:
        return {"status": "no_targets", "message": "No eligible inactive students found.", "count": 0}

    async def _dispatch():
        result = await send_reminders(inactive)
        logger.info("Admin-triggered task reminders: %s", result)

    background_tasks.add_task(_dispatch)

    return {
        "status": "dispatched",
        "message": f"Sending {len(inactive)} reminder(s) in background.",
        "count": len(inactive),
        "students": [
            {"student_id": s["student_id"], "name": f"{s['first_name']} {s['last_name']}", "email": s["email"]}
            for s in inactive
        ],
    }


# ──────────────────────────────────────────────
# Analytics
# ──────────────────────────────────────────────

# Payments that never went through Razorpay checkout (seeded/manual test rows such
# as pay_test123 / pay_mock_456). Every real paid row passes signature verification
# in routes/payments.py and carries a genuine pay_… id, so these are excluded from
# every revenue / paid figure — the dashboard only reports money actually collected.
REAL_PAYMENT_SQL = (
    "COALESCE(razorpay_payment_id, '') NOT LIKE 'pay_test%' "
    "AND COALESCE(razorpay_payment_id, '') NOT LIKE 'pay_mock%'"
)
TOTAL_WEEKS = 4


def _pct(part: int, whole: int) -> float:
    return round(part * 100 / whole, 1) if whole else 0.0


@router.get("/analytics", summary="Aggregated platform analytics for the admin dashboard")
async def get_analytics(_: str = Depends(require_admin)):
    """
    Built from real activity rather than students.status (which stays 'enrolled'
    for almost everyone and never records completion):
      started   = has at least one task submission
      completed = all 4 weeks approved
      certified = has a certificate row
      paid      = at least one verified Razorpay payment (test ids excluded)

    Domains are merged through task_service.normalize_domain_slug — the same resolver
    tasks, emails and certificates already use — so stored variants like
    'Data Science' / 'data-science' count as one domain.

    The per-student rollup is ONE query over pre-aggregated joins (no per-row
    correlated subqueries); the funnel cards and the domain table are both derived
    from it, so their numbers always agree with each other.
    """
    from services.task_service import task_service
    from services.email_service import _domain_label

    students = await db.fetch_all(
        f"""SELECT s.id, s.domain,
                   COALESCE(sub.submitted, 0)      AS submitted,
                   COALESCE(sub.weeks_approved, 0) AS weeks_approved,
                   CASE WHEN pay.student_id  IS NULL THEN 0 ELSE 1 END AS has_paid,
                   COALESCE(pay.revenue, 0)        AS revenue_paise,
                   CASE WHEN cert.student_id IS NULL THEN 0 ELSE 1 END AS has_cert
            FROM students s
            LEFT JOIN (SELECT student_id, COUNT(*) AS submitted,
                              COUNT(DISTINCT CASE WHEN status = 'approved' THEN week END) AS weeks_approved
                       FROM submissions GROUP BY student_id) sub ON sub.student_id = s.id
            LEFT JOIN (SELECT student_id, SUM(amount) AS revenue
                       FROM payments WHERE status = 'paid' AND {REAL_PAYMENT_SQL}
                       GROUP BY student_id) pay ON pay.student_id = s.id
            LEFT JOIN (SELECT DISTINCT student_id FROM certificates) cert ON cert.student_id = s.id"""
    )

    funnel = {"total": 0, "started": 0, "completed": 0, "certified": 0, "paid": 0}
    domains: dict[str, dict] = {}
    for s in students:
        raw = (s["domain"] or "").strip()
        key = task_service.normalize_domain_slug(raw) if raw else "unspecified"
        d = domains.setdefault(key, {
            "domain": key,
            "label": _domain_label(key) if raw else "Unspecified",
            "total": 0, "started": 0, "completed": 0, "certified": 0, "paid": 0,
            "revenue_rupees": 0.0,
        })
        started = (s["submitted"] or 0) > 0
        completed = (s["weeks_approved"] or 0) >= TOTAL_WEEKS
        for bucket in (funnel, d):
            bucket["total"] += 1
            bucket["started"] += started
            bucket["completed"] += completed
            bucket["certified"] += bool(s["has_cert"])
            bucket["paid"] += bool(s["has_paid"])
        d["revenue_rupees"] += (s["revenue_paise"] or 0) / 100

    domain_list = sorted(domains.values(), key=lambda d: d["total"], reverse=True)
    for d in domain_list:
        d["completion_rate"] = _pct(d["completed"], d["started"])

    # Week-by-week review status — approved counts per week form the drop-off curve.
    weekly = await db.fetch_all(
        """SELECT week,
                  SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) AS approved,
                  SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected,
                  SUM(CASE WHEN status = 'pending'  THEN 1 ELSE 0 END) AS pending
           FROM submissions GROUP BY week ORDER BY week"""
    )

    # Revenue by price point: full-price and discount-code orders are reported
    # separately so a ₹5 order reads as an intended discount, not a data error.
    tiers = await db.fetch_all(
        f"""SELECT amount, COUNT(*) AS orders FROM payments
            WHERE status = 'paid' AND {REAL_PAYMENT_SQL}
            GROUP BY amount ORDER BY amount DESC"""
    )
    full_price = settings.certificate_price_paise
    tier_list = []
    for t in tiers:
        amount = t["amount"] or 0
        orders = t["orders"] or 0
        kind = "full" if amount == full_price else ("discounted" if amount < full_price else "legacy")
        tier_list.append({
            "kind": kind,
            "price_rupees": amount / 100,
            "orders": orders,
            "revenue_rupees": amount * orders / 100,
        })
    total_revenue = sum(t["revenue_rupees"] for t in tier_list)
    paid_orders = sum(t["orders"] for t in tier_list)

    excluded = await db.fetch_one(
        f"""SELECT COUNT(*) AS orders, COALESCE(SUM(amount), 0) AS amount FROM payments
            WHERE status = 'paid' AND NOT ({REAL_PAYMENT_SQL})"""
    ) or {}

    # Students who opened checkout but never completed a real payment. An order row is
    # created on every "Pay" click, so counting rows instead of students overstates this.
    abandoned = await db.fetch_one(
        f"""SELECT COUNT(DISTINCT student_id) AS students FROM payments
            WHERE status = 'pending' AND student_id NOT IN (
                SELECT student_id FROM payments WHERE status = 'paid' AND {REAL_PAYMENT_SQL})"""
    ) or {}

    revenue_trend = await db.fetch_all(
        f"""SELECT strftime('%Y-%m', created_at) AS month,
                   COUNT(*) AS orders, COALESCE(SUM(amount), 0) AS revenue_paise
            FROM payments
            WHERE status = 'paid' AND {REAL_PAYMENT_SQL}
              AND created_at >= datetime('now', '-12 months')
            GROUP BY month ORDER BY month"""
    )

    applications_trend = await db.fetch_all(
        """SELECT strftime('%Y-%m', created_at) AS month, COUNT(*) AS count
           FROM students
           WHERE created_at >= datetime('now', '-12 months')
           GROUP BY month ORDER BY month"""
    )

    return {
        "funnel": {
            **funnel,
            "never_started": funnel["total"] - funnel["started"],
            "start_rate": _pct(funnel["started"], funnel["total"]),
            "completion_rate": _pct(funnel["completed"], funnel["started"]),
            "paid_rate": _pct(funnel["paid"], funnel["total"]),
        },
        "domains": domain_list,
        "weekly_completion": [
            {"week": r["week"], "approved": r["approved"] or 0,
             "rejected": r["rejected"] or 0, "pending": r["pending"] or 0}
            for r in weekly
        ],
        "revenue": {
            "total_revenue_rupees": total_revenue,
            "paid_orders": paid_orders,
            "paid_students": funnel["paid"],
            "avg_order_rupees": round(total_revenue / paid_orders, 2) if paid_orders else 0,
            "tiers": tier_list,
            "abandoned_checkouts": abandoned.get("students") or 0,
            "excluded_test_orders": excluded.get("orders") or 0,
            "excluded_test_rupees": (excluded.get("amount") or 0) / 100,
            "trend": [
                {"month": r["month"], "orders": r["orders"] or 0,
                 "revenue_rupees": (r["revenue_paise"] or 0) / 100}
                for r in revenue_trend
            ],
        },
        "applications_trend": [
            {"month": r["month"], "count": r["count"] or 0} for r in applications_trend
        ],
    }
