"""
SkillMe — Admin API Routes
Protected endpoints for student shortlisting/enrollment
and LinkedIn submission review. Requires X-Admin-Key header.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field
import logging
import time
from datetime import datetime
from middleware.auth import require_admin
from services.enrollment_service import enrollment_service
from services.submission_service import submission_service, SCORE_PER_APPROVAL
from services.urgent_request_service import urgent_request_service
from services.email_service import email_service
from services import analytics_service
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
             (SELECT COUNT(*) FROM students WHERE COALESCE(is_test, 0) = 0) AS total_students,
             (SELECT COUNT(*) FROM students WHERE status = 'applied') AS pending_applications,
             (SELECT COUNT(*) FROM students WHERE status = 'shortlisted') AS shortlisted_students,
             (SELECT COUNT(*) FROM students WHERE status = 'enrolled') AS enrolled_students,
             (SELECT COUNT(DISTINCT student_id) FROM payments
                WHERE status = 'paid' AND {REAL_PAYMENT_SQL}) AS total_alumni,
             (SELECT COUNT(*) FROM submissions WHERE status = 'pending') AS pending_submissions,
             (SELECT COUNT(*) FROM urgent_requests WHERE status = 'pending') AS pending_urgent_requests,
             (SELECT COUNT(*) FROM students WHERE date(created_at) = date('now')) AS apps_today,
             (SELECT COUNT(*) FROM students WHERE created_at >= datetime('now', '-7 days')) AS apps_7d,
             (SELECT COUNT(*) FROM students WHERE created_at >= datetime('now', '-14 days')
                AND created_at < datetime('now', '-7 days')) AS apps_prev_7d,
             (SELECT COUNT(DISTINCT e) FROM (
                SELECT lower(email) AS e FROM otp_tokens
                  WHERE used = 1 AND datetime(created_at) >= datetime('now', '-7 days')
                UNION
                SELECT lower(s.email) FROM submissions sub JOIN students s ON s.id = sub.student_id
                  WHERE datetime(sub.submitted_at) >= datetime('now', '-7 days')
             )) AS active_7d,
             (SELECT COUNT(*) FROM submissions
                WHERE datetime(submitted_at) >= datetime('now', '-7 days')) AS subs_7d,
             (SELECT COUNT(*) FROM submissions
                WHERE datetime(submitted_at) >= datetime('now', '-14 days')
                  AND datetime(submitted_at) < datetime('now', '-7 days')) AS subs_prev_7d,
             (SELECT COUNT(*) FROM enrollments
                WHERE datetime(joined_at) >= datetime('now', '-7 days')) AS enrolled_7d,
             (SELECT COUNT(*) FROM submissions WHERE status = 'approved'
                AND datetime(reviewed_at) >= datetime('now', '-30 days')) AS approved_30d,
             (SELECT COUNT(*) FROM submissions WHERE status = 'rejected'
                AND datetime(reviewed_at) >= datetime('now', '-30 days')) AS rejected_30d,
             (SELECT julianday('now') - julianday(MIN(datetime(submitted_at)))
                FROM submissions WHERE status = 'pending') AS oldest_pending_days,
             (SELECT COUNT(*) FROM (
                SELECT student_id FROM submissions WHERE status = 'approved'
                GROUP BY student_id HAVING COUNT(DISTINCT week) >= {TOTAL_WEEKS})) AS completed_total,
             (SELECT COUNT(*) FROM (
                SELECT student_id FROM submissions WHERE status = 'approved'
                GROUP BY student_id HAVING COUNT(DISTINCT week) >= {ELIGIBLE_WEEKS}
              ) el WHERE el.student_id NOT IN (
                SELECT student_id FROM payments WHERE status = 'paid' AND {REAL_PAYMENT_SQL})
             ) AS eligible_unpaid"""
    ) or {}
    keys = ("total_students", "pending_applications", "shortlisted_students", "enrolled_students",
            "total_alumni", "pending_submissions", "pending_urgent_requests",
            "apps_today", "apps_7d", "apps_prev_7d", "active_7d", "eligible_unpaid",
            "subs_7d", "subs_prev_7d", "enrolled_7d", "approved_30d", "rejected_30d", "completed_total")
    out = {k: row.get(k) or 0 for k in keys}
    # Completed / eligible-unpaid / paying students come from the shared per-student rollup so the
    # Overview page and the Analytics page can never show different numbers for the same metric.
    _, students = await _dataset()
    ov = analytics_service.overview(analytics_service.apply_filters(students), datetime.utcnow())
    out["completed_total"] = ov["completed"]
    out["eligible_unpaid"] = ov["eligible_unpaid"]
    out["total_alumni"] = ov["paying_students"]
    reviewed = out["approved_30d"] + out["rejected_30d"]
    out["approval_rate_30d"] = _pct(out["approved_30d"], reviewed)
    oldest = row.get("oldest_pending_days")
    out["oldest_pending_days"] = round(max(0.0, oldest), 1) if oldest is not None else None
    return out


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
            student_id=student_id,
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

    students, count_rows = await db.fetch_batch([(
        f"""SELECT s.id, s.first_name, s.last_name, s.email, s.phone, s.github_username,
                   s.linkedin_url, s.college, s.year_of_study, s.domain, s.status,
                   s.quiz_score, s.quiz_total, s.created_at, s.updated_at,
                   (SELECT group_concat(o.domain, ', ') FROM students o
                     WHERE lower(o.email) = lower(s.email) AND o.id != s.id) AS other_domains,
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
    ), (f"SELECT COUNT(*) AS count FROM students s {where}", tuple(params))])
    total_row = count_rows[0] if count_rows else None
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
async def delete_student(student_id: int, force: bool = False, _: str = Depends(require_admin)):
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

    # Revenue history is not deleted by accident: a student with a real (non-test) paid payment or an
    # issued certificate needs an explicit ?force=true. Test accounts / test payments never block.
    if not force:
        kept = await db.fetch_one(
            f"""SELECT (SELECT COUNT(*) FROM payments WHERE student_id = ? AND status = 'paid' AND {REAL_PAYMENT_SQL}) AS paid,
                       (SELECT COUNT(*) FROM certificates WHERE student_id = ?) AS certs""",
            (student_id, student_id),
        )
        if kept and not student.get("is_test") and ((kept["paid"] or 0) or (kept["certs"] or 0)):
            raise HTTPException(
                status_code=409,
                detail=f"Student #{student_id} has {kept['paid']} paid payment(s) and {kept['certs']} certificate(s). "
                       "Deleting erases that revenue history. Re-send with ?force=true if you are sure.",
            )

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

        _invalidate_analytics()
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
# Analytics — definitions live in services/analytics_service.py
# ──────────────────────────────────────────────

# SQL fragment: a payment that counts as real money (not flagged test, not a seeded pay_test/pay_mock row)
REAL_PAYMENT_SQL = (
    "COALESCE(is_test, 0) = 0 "
    "AND COALESCE(razorpay_payment_id, '') NOT LIKE 'pay_test%' "
    "AND COALESCE(razorpay_payment_id, '') NOT LIKE 'pay_mock%'"
)
TOTAL_WEEKS = analytics_service.TOTAL_WEEKS
ELIGIBLE_WEEKS = analytics_service.ELIGIBLE_WEEKS
ANALYTICS_TTL_SECONDS = 60
# The raw rows are cached (not the filtered result): every filter combination is then computed
# from the same snapshot, so tabs and drill-downs can never disagree within a refresh.
_analytics_cache: dict = {"at": 0.0, "data": None}


def _pct(part: int, whole: int) -> float:
    return round(part * 100 / whole, 1) if whole else 0.0


async def _dataset(fresh: bool = False) -> tuple[dict, list[dict]]:
    now = time.monotonic()
    cached = _analytics_cache["data"]
    if not fresh and cached is not None and now - _analytics_cache["at"] < ANALYTICS_TTL_SECONDS:
        return cached
    raw = await analytics_service.load_raw(db)
    data = (raw, analytics_service.build_students(raw))
    _analytics_cache["at"] = now
    _analytics_cache["data"] = data
    return data


def _invalidate_analytics() -> None:
    _analytics_cache.update(at=0.0, data=None)


def _filters(date_from, date_to, domain, source, campaign, include_test) -> dict:
    return {"date_from": date_from or None, "date_to": date_to or None, "domain": domain or None,
            "source": source or None, "campaign": campaign or None, "include_test": include_test}


@router.get("/analytics", summary="Aggregated platform analytics for the admin dashboard")
async def get_analytics(
    fresh: bool = False,
    date_from: str | None = Query(None, alias="from", description="Applied on/after (IST date, YYYY-MM-DD)"),
    date_to: str | None = Query(None, alias="to", description="Applied on/before (IST date, YYYY-MM-DD)"),
    domain: str | None = None,
    source: str | None = None,
    campaign: str | None = None,
    include_test: bool = False,
    inactive_days: int = 7,
    _: str = Depends(require_admin),
):
    """
    Every figure is computed by services/analytics_service.py from one per-student rollup
    (see DEFINITIONS in the response). The date range is a COHORT filter: students who applied in
    the range (IST). Test accounts and test payments are excluded unless include_test=true.
    """
    raw, students = await _dataset(fresh)
    return analytics_service.compute(
        raw, students, _filters(date_from, date_to, domain, source, campaign, include_test),
        inactive_days=max(1, min(inactive_days, 90)))


@router.get("/analytics/students", summary="Drill-down: students behind a metric")
async def analytics_students(
    stage: str,
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
    domain: str | None = None,
    source: str | None = None,
    campaign: str | None = None,
    include_test: bool = False,
    q: str | None = None,
    page: int = 1,
    limit: int = 25,
    _: str = Depends(require_admin),
):
    """The exact students counted by a funnel stage / payment state, using the same filters and rollup."""
    _, students = await _dataset()
    try:
        return analytics_service.drilldown(
            students, _filters(date_from, date_to, domain, source, campaign, include_test), stage, page, limit, q)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unknown stage '{stage}'")


@router.get("/analytics/data-quality", summary="Inconsistent records and metric validation warnings")
async def analytics_data_quality(_: str = Depends(require_admin)):
    _, students = await _dataset()
    return await analytics_service.data_quality(db, students)


@router.get("/students/{student_id}/journey", summary="One student's full timeline")
async def student_journey(student_id: int, _: str = Depends(require_admin)):
    data = await analytics_service.journey(db, student_id)
    if not data:
        raise HTTPException(status_code=404, detail="Student not found")
    return data


class TestFlagRequest(BaseModel):
    is_test: bool


@router.patch("/students/{student_id}/test-flag", summary="Mark a student account as test (or real)")
async def set_student_test_flag(student_id: int, req: TestFlagRequest, _: str = Depends(require_admin)):
    """Flags only; nothing is deleted. Flagged students drop out of every analytics figure by default."""
    if not await db.fetch_one("SELECT id FROM students WHERE id = ?", (student_id,)):
        raise HTTPException(status_code=404, detail="Student not found")
    await db.execute("UPDATE students SET is_test = ? WHERE id = ?", (1 if req.is_test else 0, student_id))
    _invalidate_analytics()
    return {"student_id": student_id, "is_test": req.is_test}


@router.patch("/payments/{payment_id}/test-flag", summary="Mark a payment as a test transaction (or real)")
async def set_payment_test_flag(payment_id: int, req: TestFlagRequest, _: str = Depends(require_admin)):
    if not await db.fetch_one("SELECT id FROM payments WHERE id = ?", (payment_id,)):
        raise HTTPException(status_code=404, detail="Payment not found")
    await db.execute("UPDATE payments SET is_test = ? WHERE id = ?", (1 if req.is_test else 0, payment_id))
    _invalidate_analytics()
    return {"payment_id": payment_id, "is_test": req.is_test}


@router.get("/payments", summary="Payment lifecycle list (orders, transactions, failures)")
async def list_payments(
    status: str | None = None,     # created | pending | paid | failed | abandoned | test
    q: str | None = None,
    page: int = 1,
    limit: int = 25,
    _: str = Depends(require_admin),
):
    """Order-level view. 'abandoned' is derived (see DEFINITIONS); 'test' lists flagged test transactions."""
    from datetime import datetime, timedelta
    rows = await db.fetch_all(
        """SELECT p.id, p.student_id, p.razorpay_order_id, p.razorpay_payment_id, p.amount, p.status,
                  COALESCE(p.is_test, 0) AS is_test, p.created_at, p.initiated_at, p.completed_at, p.updated_at,
                  p.failure_code, p.failure_reason, p.discount_code, p.confirmed_via,
                  s.first_name || ' ' || s.last_name AS student_name, s.email, s.domain
           FROM payments p LEFT JOIN students s ON s.id = p.student_id ORDER BY p.id DESC"""
    )
    now = datetime.utcnow()
    out = []
    for r in rows:
        shown = r["status"]
        if r["status"] in ("created", "pending"):
            started = analytics_service.parse_ts(r["initiated_at"] or r["created_at"])
            limit_age = timedelta(hours=analytics_service.PENDING_ABANDON_HOURS) if r["status"] == "pending" \
                else timedelta(minutes=analytics_service.FIRST_STEP_ABANDON_MIN)
            if started and now - started > limit_age:
                shown = "abandoned"
        r["lifecycle"] = shown
        r["legacy"] = not r["initiated_at"]
        r["paid_at"] = (r["completed_at"] or r["updated_at"]) if r["status"] == "paid" else None
        out.append(r)
    if status == "test":
        out = [r for r in out if r["is_test"]]
    elif status:
        out = [r for r in out if r["lifecycle"] == status and not r["is_test"]]
    if q and q.strip():
        n = q.strip().lower()
        out = [r for r in out if n in f"{r['student_name']} {r['email']} {r['razorpay_order_id']} {r['razorpay_payment_id']}".lower()]
    total = len(out)
    limit = max(1, min(limit, 100))
    page = max(1, page)
    return {"payments": out[(page - 1) * limit: page * limit], "total": total, "page": page,
            "limit": limit, "total_pages": max(1, -(-total // limit))}
