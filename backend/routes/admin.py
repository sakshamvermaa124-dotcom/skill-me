"""
SkillMe — Admin API Routes
Protected endpoints for batch management, student enrollment,
and issue assignment. Requires X-Admin-Key header.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from middleware.auth import require_admin
from services.batch_service import batch_service
from services.github_service import github_service
from services.scheduler_service import scheduler_service
from services.email_service import email_service
from db.database import db

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ──────────────────────────────────────────────
# Request / Response Models
# ──────────────────────────────────────────────

class CreateBatchRequest(BaseModel):
    domain: str = Field(..., description="Domain name, e.g. 'web-dev', 'python'")
    batch_number: int = Field(..., ge=1, description="Sequential batch number")
    template_repo: str | None = Field(None, description="Override template repo name")
    max_students: int = Field(30, ge=1, le=100)
    start_date: str | None = Field(None, description="ISO date (YYYY-MM-DD)")
    webhook_url: str | None = Field(None, description="URL for GitHub webhooks")


class AddStudentRequest(BaseModel):
    student_id: int = Field(..., description="Student database ID")


class AssignIssuesRequest(BaseModel):
    week_number: int = Field(..., ge=1, le=4, description="Week number (1-4)")
    issues: list[dict] = Field(
        ...,
        description="List of issue dicts with 'title', 'body', 'assigned_to_student_id'",
    )


class AssignFromRepoRequest(BaseModel):
    week_number: int = Field(..., ge=1, le=4, description="Week number (1-4)")


class UpdateStudentStatusRequest(BaseModel):
    status: str = Field(..., description="New status: shortlisted | enrolled | completed | dropped")


# ──────────────────────────────────────────────
# GitHub Health Check
# ──────────────────────────────────────────────

@router.get("/github/status", summary="Check GitHub API connection")
async def github_status(_: str = Depends(require_admin)):
    """Verify the GitHub token is working and return org info."""
    user = await github_service.verify_token()
    if not user:
        raise HTTPException(status_code=502, detail="GitHub token is invalid or expired")
    return {
        "status": "connected",
        "authenticated_as": user.get("login"),
        "org": github_service.org,
    }


@router.get("/stats", summary="Get admin dashboard stats")
async def get_stats(_: str = Depends(require_admin)):
    """Get aggregated stats for the admin dashboard."""
    total_students = await db.fetch_one("SELECT COUNT(*) as count FROM students")
    active_batches = await db.fetch_one("SELECT COUNT(*) as count FROM batches WHERE status = 'active'")
    pending_applications = await db.fetch_one("SELECT COUNT(*) as count FROM students WHERE status = 'applied'")
    total_issues = await db.fetch_one("SELECT COUNT(*) as count FROM issues")

    return {
        "total_students": total_students["count"] if total_students else 0,
        "active_batches": active_batches["count"] if active_batches else 0,
        "pending_applications": pending_applications["count"] if pending_applications else 0,
        "total_issues_assigned": total_issues["count"] if total_issues else 0,
    }


# ──────────────────────────────────────────────
# Batch Management
# ──────────────────────────────────────────────

@router.post("/batches", summary="Create a new batch")
async def create_batch(req: CreateBatchRequest, _: str = Depends(require_admin)):
    """
    Creates a new batch:
    1. Generates a GitHub repo from the domain's template
    2. Sets up webhooks
    3. Records the batch in the database
    """
    try:
        batch = await batch_service.create_batch(
            domain=req.domain,
            batch_number=req.batch_number,
            template_repo=req.template_repo,
            max_students=req.max_students,
            start_date=req.start_date,
            webhook_url=req.webhook_url,
        )
        response = {"status": "created", "batch": batch}
        if not batch.get("github_repo_created", True):
            response["warning"] = (
                f"⚠️ GitHub repo '{batch['repo_name']}' could NOT be created — "
                f"no matching template found. Enrollment and task assignment will fail "
                f"until the repo is manually created on GitHub."
            )
        return response
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create batch: {str(e)}")


@router.get("/batches", summary="List all batches")
async def list_batches(status: str | None = None, _: str = Depends(require_admin)):
    """List all batches with enrolled student counts, optionally filtered by status."""
    batches = await batch_service.list_batches(status=status)

    # Fetch enrollment counts for all batches in one query and attach to each batch
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

    # Get enrollment count
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


# ──────────────────────────────────────────────
# Student Enrollment
# ──────────────────────────────────────────────

@router.post("/batches/{batch_id}/students", summary="Add a student to a batch")
async def add_student_to_batch(
    batch_id: int, req: AddStudentRequest,
    background_tasks: BackgroundTasks,
    _: str = Depends(require_admin)
):
    """
    Enroll a student in a batch:
    1. Adds them as a GitHub collaborator
    2. Creates the enrollment record
    3. Sends offer letter email
    """
    try:
        result = await batch_service.add_student_to_batch(req.student_id, batch_id)

        # Fetch student + batch info for email
        student = await db.fetch_one(
            "SELECT first_name, last_name, email, github_username FROM students WHERE id = ?",
            (req.student_id,)
        )
        batch = await db.fetch_one(
            "SELECT domain, batch_number, repo_name FROM batches WHERE id = ?",
            (batch_id,)
        )
        if student and batch:
            repo_url = (
                f"https://github.com/{github_service.org}/{batch['repo_name']}"
                if batch.get("repo_name") else None
            )
            background_tasks.add_task(
                email_service.send_offer_letter,
                first_name=student["first_name"],
                last_name=student["last_name"],
                email=student["email"],
                domain=batch["domain"],
                batch_number=batch["batch_number"],
                repo_url=repo_url,
                github_username=student.get("github_username") or None,
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
    """Remove a student from a batch and revoke GitHub access."""
    await batch_service.remove_student_from_batch(student_id, batch_id)
    return {"status": "removed", "student_id": student_id, "batch_id": batch_id}


# ──────────────────────────────────────────────
# Issue Assignment
# ──────────────────────────────────────────────

@router.post("/batches/{batch_id}/assign-issues", summary="Assign weekly issues")
async def assign_issues(
    batch_id: int, req: AssignIssuesRequest, _: str = Depends(require_admin)
):
    """
    Create and assign issues for a specific week:
    1. Creates issues in the batch's GitHub repo
    2. Assigns each issue to the specified student
    3. Updates progress tracking
    """
    try:
        created = await batch_service.assign_weekly_issues(
            batch_id=batch_id,
            week_number=req.week_number,
            issues=req.issues,
        )
        return {
            "status": "assigned",
            "week": req.week_number,
            "issues_created": len(created),
            "issues": created,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/batches/{batch_id}/assign-from-repo", summary="Assign weekly issues from task repo")
async def assign_from_repo(
    batch_id: int, req: AssignFromRepoRequest, _: str = Depends(require_admin)
):
    """
    Fetch tasks from the central task repo for the batch's domain and week,
    and assign them to all enrolled students.
    """
    try:
        created = await batch_service.assign_week_from_task_repo(
            batch_id=batch_id,
            week_number=req.week_number,
        )
        return {
            "status": "assigned",
            "week": req.week_number,
            "issues_created": len(created),
            "issues": created,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
            """SELECT s.*, e.batch_id 
               FROM students s 
               LEFT JOIN enrollments e ON s.id = e.student_id AND e.status != 'dropped'
               WHERE s.status = ? 
               ORDER BY s.created_at DESC LIMIT ? OFFSET ?""",
            (status, limit, offset),
        )
    else:
        students = await db.fetch_all(
            """SELECT s.*, e.batch_id 
               FROM students s 
               LEFT JOIN enrollments e ON s.id = e.student_id AND e.status != 'dropped'
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
        """SELECT e.*, b.domain, b.batch_number, b.repo_name, b.status as batch_status
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

    # Send lifecycle email or handle cohort removal based on new status
    if req.status == "shortlisted":
        # Domain is stored directly on the student record
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
        # If student is dropped, remove them from any active cohorts on GitHub and update enrollments table
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


# ──────────────────────────────────────────────
# Auto-Assign Scheduler
# ──────────────────────────────────────────────

@router.patch("/batches/{batch_id}/auto-assign", summary="Toggle auto-assign for a batch")
async def toggle_auto_assign(
    batch_id: int,
    _: str = Depends(require_admin),
    enabled: bool = True,
):
    """
    Enable or disable automatic weekly task assignment for a batch.
    When enabled, tasks are assigned every Monday based on the batch's start_date.
    """
    batch = await db.fetch_one("SELECT id FROM batches WHERE id = ?", (batch_id,))
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    await db.execute(
        "UPDATE batches SET auto_assign = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (1 if enabled else 0, batch_id),
    )
    return {"status": "updated", "batch_id": batch_id, "auto_assign": enabled}


@router.post("/scheduler/trigger", summary="Manually trigger the auto-assign scheduler")
async def trigger_scheduler(_: str = Depends(require_admin)):
    """
    Manually run the auto-assign scheduler immediately.
    Useful for testing or when you want to assign tasks outside the Monday schedule.
    """
    result = await scheduler_service.trigger_now()
    return result


@router.get("/scheduler/status", summary="Get scheduler status")
async def scheduler_status(_: str = Depends(require_admin)):
    """Get the status of the auto-assign scheduler and upcoming runs."""
    from services.scheduler_service import run_auto_assign
    job = scheduler_service._scheduler.get_job("auto_assign_weekly")
    next_run = job.next_run_time.isoformat() if job and job.next_run_time else None
    batches_with_auto = await db.fetch_all(
        "SELECT id, domain, batch_number, start_date, weeks_assigned FROM batches WHERE auto_assign = 1 AND status = 'active'"
    )
    return {
        "scheduler_running": scheduler_service._scheduler.running,
        "next_run": next_run,
        "auto_assign_batches": [
            {
                "batch_id": b["id"],
                "name": f"{b['domain']} #{b['batch_number']}",
                "start_date": b["start_date"],
                "weeks_assigned": b["weeks_assigned"],
            }
            for b in batches_with_auto
        ],
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
        conditions.append("status = ?")
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

