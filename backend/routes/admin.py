"""
SkillMe — Admin API Routes
Protected endpoints for batch management, student enrollment,
and issue assignment. Requires X-Admin-Key header.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
import logging
from middleware.auth import require_admin
from services.batch_service import batch_service
from services.github_service import github_service
from services.scheduler_service import scheduler_service
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
        warnings = []
        if not batch.get("github_repo_created", True):
            warnings.append(
                f"⚠️ GitHub repo '{batch['repo_name']}' could NOT be created. "
                f"Enrollment and task assignment will fail until the repo is manually created."
            )
        if not batch.get("github_webhook_created", False):
            if req.webhook_url:
                warnings.append(
                    f"⚠️ GitHub webhook could NOT be attached to '{batch['repo_name']}'. "
                    f"PR tracking will fail until the webhook is manually attached."
                )
            else:
                warnings.append(
                    f"⚠️ No webhook URL provided. "
                    f"PR tracking will fail until a webhook is manually attached to '{batch['repo_name']}'."
                )
            
        if warnings:
            response["warning"] = " | ".join(warnings)
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


@router.post("/batches/{batch_id}/sync-prs", summary="Sync merged PRs from GitHub API")
async def sync_batch_prs(batch_id: int, _: str = Depends(require_admin)):
    """
    Fetches all closed/merged PRs directly from GitHub API for this batch repo
    and updates database submissions and student scores.
    """
    batch = await db.fetch_one("SELECT * FROM batches WHERE id = ?", (batch_id,))
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    repo_name = batch["repo_name"]
    prs = await github_service.list_pull_requests(repo_name, state="closed")
    merged_count = 0
    skipped_count = 0
    for pr in prs:
        if pr.get("merged_at"):
            pr_number = pr.get("number")
            pr_user = pr.get("user", {}).get("login", "")
            pr_url = pr.get("html_url", "")
            
            # Check if this PR already has a merged submission — skip to avoid score inflation
            existing = await db.fetch_one(
                "SELECT id, status FROM submissions WHERE batch_id = ? AND pr_number = ?",
                (batch_id, pr_number)
            )
            if existing and existing["status"] == "merged":
                skipped_count += 1
                continue
            
            if not existing:
                await batch_service.record_submission(
                    batch_id=batch_id,
                    student_github_username=pr_user,
                    pr_number=pr_number,
                    pr_url=pr_url,
                    pr_head_branch=pr.get("head", {}).get("ref") or None,
                )
            await batch_service.update_submission_status(
                batch_id=batch_id,
                pr_number=pr_number,
                status="merged"
            )
            merged_count += 1
            
    return {"status": "synced", "batch_id": batch_id, "merged_prs_processed": merged_count, "already_synced": skipped_count}


@router.post("/batches/{batch_id}/setup-webhook", summary="Attach GitHub webhook to an existing batch")
async def setup_batch_webhook(batch_id: int, _: str = Depends(require_admin)):
    """
    Register a GitHub webhook on the batch's repo pointing to this backend.
    Use this to fix batches that were created before BACKEND_URL was configured,
    or where webhook registration failed during batch creation.
    Requires BACKEND_URL to be set in the environment.
    """
    if not settings.backend_url:
        raise HTTPException(
            status_code=400,
            detail="BACKEND_URL is not configured. Set it in your Render environment variables to enable auto-webhook registration."
        )

    batch = await db.fetch_one("SELECT * FROM batches WHERE id = ?", (batch_id,))
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    repo_name = batch["repo_name"]
    webhook_url = settings.backend_url.rstrip("/") + "/api/webhooks/github"

    try:
        result = await github_service.create_webhook(repo_name, webhook_url)
        return {
            "status": "webhook_created",
            "repo": repo_name,
            "webhook_url": webhook_url,
            "webhook_id": result.get("id"),
        }
    except Exception as e:
        error_msg = str(e)
        # GitHub returns 422 if a webhook with the same URL already exists
        if "already exists" in error_msg or "422" in error_msg:
            return {
                "status": "already_exists",
                "repo": repo_name,
                "webhook_url": webhook_url,
                "message": "A webhook pointing to this URL already exists on the repo.",
            }
        raise HTTPException(status_code=502, detail=f"Failed to create webhook on GitHub: {error_msg}")


@router.delete("/batches/{batch_id}", summary="Delete a batch and all related data")
async def delete_batch(batch_id: int, _: str = Depends(require_admin)):
    """
    Delete a batch entirely. Also cascades to all related progress, submissions, enrollments, etc.
    Does NOT delete the actual GitHub repository or the Students themselves.
    """
    batch = await batch_service.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    try:
        # Delete related data manually if no foreign key ON DELETE CASCADE is set
        await db.execute("DELETE FROM progress WHERE batch_id = ?", (batch_id,))
        await db.execute("DELETE FROM submissions WHERE batch_id = ?", (batch_id,))
        await db.execute("DELETE FROM issues WHERE batch_id = ?", (batch_id,))
        await db.execute("DELETE FROM enrollments WHERE batch_id = ?", (batch_id,))
        await db.execute("DELETE FROM certificates WHERE batch_id = ?", (batch_id,))
        await db.execute("DELETE FROM payments WHERE batch_id = ?", (batch_id,))
        await db.execute("DELETE FROM email_logs WHERE batch_id = ?", (batch_id,))
        
        # Finally delete the batch
        await db.execute("DELETE FROM batches WHERE id = ?", (batch_id,))
        
        return {"status": "success", "message": f"Batch {batch_id} completely deleted from database."}
    except Exception as e:
        logger.error(f"Failed to delete batch {batch_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


# ──────────────────────────────────────────────
# Student Enrollment
# ──────────────────────────────────────────────

@router.post("/students/{student_id}/enroll", summary="Auto-enroll student with dedicated repo and webhook")
async def auto_enroll_student_endpoint(
    student_id: int,
    background_tasks: BackgroundTasks,
    _: str = Depends(require_admin),
):
    """
    Automated 1-repo-per-student enrollment:
    1. Creates a dedicated GitHub repository from the domain template.
    2. Attaches GitHub webhook for PR tracking.
    3. Adds student as collaborator.
    4. Creates batch and enrollment records in DB.
    5. Auto-assigns Week 1 tasks.
    6. Sends Offer Letter and Week 1 tasks emails.
    """
    try:
        result = await batch_service.auto_enroll_student(student_id)

        # Fetch student details for emails
        student = await db.fetch_one(
            "SELECT first_name, last_name, email, github_username, domain FROM students WHERE id = ?",
            (student_id,)
        )

        if student:
            repo_url = result.get("repo_url")
            gh_user = student.get("github_username")

            # 1. Dispatch Offer Letter email
            background_tasks.add_task(
                email_service.send_offer_letter,
                first_name=student["first_name"],
                last_name=student["last_name"],
                email=student["email"],
                domain=result["domain"],
                batch_number=result["batch_number"],
                repo_url=repo_url,
                github_username=gh_user or None,
            )

            # 2. Dispatch Week 1 Tasks email if tasks were created
            week_1_tasks = result.get("week_1_tasks", [])
            if week_1_tasks:
                tasks_for_email = [
                    {
                        "title": r.get("title", "Task"),
                        "issue_url": f"{repo_url}/issues/{r.get('github_issue_number')}" if r.get("github_issue_number") else repo_url
                    }
                    for r in week_1_tasks
                ]
                background_tasks.add_task(
                    email_service.send_weekly_tasks_notification,
                    first_name=student["first_name"],
                    last_name=student["last_name"],
                    email=student["email"],
                    domain=result["domain"],
                    batch_number=result["batch_number"],
                    week_number=1,
                    tasks=tasks_for_email,
                    repo_url=repo_url,
                    github_username=gh_user or None,
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
    batch_id: int, req: AssignFromRepoRequest, background_tasks: BackgroundTasks, _: str = Depends(require_admin)
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

        # Send weekly task emails if tasks were successfully created
        if created:
            batch = await db.fetch_one("SELECT * FROM batches WHERE id = ?", (batch_id,))
            students = await db.fetch_all(
                """SELECT s.id, s.first_name, s.last_name, s.email, s.github_username
                   FROM students s
                   JOIN enrollments e ON e.student_id = s.id
                   WHERE e.batch_id = ? AND e.status != 'dropped'""",
                (batch_id,)
            )
            base_repo_url = (
                f"https://github.com/{settings.github_org}/{batch['repo_name']}"
                if batch and batch.get("repo_name") else None
            )
            # Send emails in background
            for student in students:
                gh_user = student.get("github_username")
                tasks_for_email = [
                    {
                        "title": r.get("title", "Task"), 
                        "issue_url": f"{base_repo_url}/issues/{r.get('github_issue_number')}" if r.get("github_issue_number") else base_repo_url
                    }
                    for r in created if r.get('assigned_to') == student['id']
                ]
                
                # BUGFIX: Only send email if they actually received tasks in this exact assignment batch
                if not tasks_for_email:
                    continue

                background_tasks.add_task(
                    email_service.send_weekly_tasks_notification,
                    first_name=student["first_name"],
                    last_name=student["last_name"],
                    email=student["email"],
                    domain=batch["domain"],
                    batch_number=batch["batch_number"],
                    week_number=req.week_number,
                    tasks=tasks_for_email,
                    repo_url=base_repo_url,
                    github_username=gh_user or None,
                )

        return {
            "status": "assigned",
            "week": req.week_number,
            "issues_created": len(created),
            "issues": created,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/batches/{batch_id}/fix-assignees", summary="Re-assign GitHub issue assignees for all enrolled students")
async def fix_assignees(batch_id: int, _: str = Depends(require_admin)):
    """
    Iterates all open/assigned GitHub issues for this batch that have a student
    assigned in the DB but may be missing the GitHub assignee (e.g. because the
    student hadn't accepted their collaborator invite when the issue was created).

    For each such issue, calls the GitHub API to add the student's GitHub username
    as an assignee. Safe to call multiple times — GitHub ignores duplicates.
    """
    batch = await db.fetch_one("SELECT * FROM batches WHERE id = ?", (batch_id,))
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    repo_name = batch.get("repo_name")
    if not repo_name:
        raise HTTPException(status_code=400, detail="Batch has no GitHub repo configured")

    # Fetch all issues that have a student assigned in the DB
    issues = await db.fetch_all(
        """SELECT i.id, i.github_issue_number, i.title, i.status,
                  s.github_username, s.first_name, s.last_name
           FROM issues i
           JOIN students s ON i.assigned_to = s.id
           WHERE i.batch_id = ?
             AND i.assigned_to IS NOT NULL
             AND i.github_issue_number IS NOT NULL
             AND i.status NOT IN ('completed')""",
        (batch_id,),
    )

    fixed = []
    skipped = []
    errors = []

    for issue in issues:
        gh_username = issue.get("github_username")
        if not gh_username:
            skipped.append({
                "issue_number": issue["github_issue_number"],
                "reason": "student has no github_username",
            })
            continue

        try:
            await github_service.add_assignees_to_issue(
                repo_name=repo_name,
                issue_number=issue["github_issue_number"],
                assignees=[gh_username],
            )
            fixed.append({
                "issue_number": issue["github_issue_number"],
                "title": issue["title"],
                "assigned_to": gh_username,
            })
        except Exception as e:
            logger.error(
                f"Failed to add assignee {gh_username} to issue #{issue['github_issue_number']}: {e}"
            )
            errors.append({
                "issue_number": issue["github_issue_number"],
                "github_username": gh_username,
                "error": str(e),
            })

    return {
        "status": "done",
        "batch_id": batch_id,
        "repo": repo_name,
        "fixed": len(fixed),
        "skipped": len(skipped),
        "errors": len(errors),
        "details": {"fixed": fixed, "skipped": skipped, "errors": errors},
    }


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


@router.delete("/students/{student_id}", summary="Delete student and all associated records")
async def delete_student(student_id: int, _: str = Depends(require_admin)):
    """
    Permanently delete a student and all their associated records from the database:
    - Submissions
    - Weekly progress
    - Assigned issues
    - Certificates
    - Payment records
    - Batch enrollments
    - Referral codes & referral conversions
    - OTP login tokens
    - Email logs for their address
    - Any dedicated 1-student batches created for them
    - The Student profile itself

    After deletion, when this user returns they will act as a completely new user.
    """
    student = await db.fetch_one("SELECT * FROM students WHERE id = ?", (student_id,))
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    email = student["email"]

    try:
        # 1. Fetch batches enrolled by this student
        enrolled_batches = await db.fetch_all(
            "SELECT batch_id FROM enrollments WHERE student_id = ?", (student_id,)
        )
        batch_ids = [b["batch_id"] for b in enrolled_batches]

        # 2. Delete all student-specific tracking and progress
        await db.execute("DELETE FROM submissions WHERE student_id = ?", (student_id,))
        await db.execute("DELETE FROM progress WHERE student_id = ?", (student_id,))
        await db.execute("DELETE FROM issues WHERE assigned_to = ?", (student_id,))
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

        # 3. Clean up any dedicated 1-student batches and their GitHub repos
        deleted_repos = []
        for b_id in batch_ids:
            batch = await db.fetch_one("SELECT max_students, repo_name FROM batches WHERE id = ?", (b_id,))
            if batch and batch.get("max_students") == 1:
                active_enrollments = await db.fetch_one(
                    "SELECT COUNT(*) as count FROM enrollments WHERE batch_id = ?", (b_id,)
                )
                if not active_enrollments or active_enrollments["count"] == 0:
                    # Delete the GitHub repo if it exists
                    repo_name = batch.get("repo_name")
                    if repo_name:
                        try:
                            deleted = await github_service.delete_repo(repo_name)
                            if deleted:
                                deleted_repos.append(repo_name)
                                logger.info(f"Deleted GitHub repo: {github_service.org}/{repo_name}")
                            else:
                                logger.warning(f"Could not delete GitHub repo: {github_service.org}/{repo_name} (may not exist or insufficient permissions)")
                        except Exception as repo_err:
                            logger.warning(f"Failed to delete GitHub repo {repo_name}: {repo_err}")

                    await db.execute("DELETE FROM issues WHERE batch_id = ?", (b_id,))
                    await db.execute("DELETE FROM progress WHERE batch_id = ?", (b_id,))
                    await db.execute("DELETE FROM submissions WHERE batch_id = ?", (b_id,))
                    await db.execute("DELETE FROM batches WHERE id = ?", (b_id,))
                    logger.info(f"Cleaned up dedicated 1-student batch {b_id}")

        # 4. Clean up any error/monitor logs
        try:
            await db.execute("DELETE FROM monitor_alerts WHERE student_id = ? OR LOWER(student_email) = LOWER(?)", (student_id, email))
            await db.execute("DELETE FROM frontend_errors WHERE LOWER(student_email) = LOWER(?)", (email,))
        except Exception:
            pass

        # 5. Delete the student record itself
        await db.execute("DELETE FROM students WHERE id = ?", (student_id,))

        logger.info(f"Admin permanently deleted student #{student_id} ({student['first_name']} {student['last_name']} - {email})")
        return {
            "status": "deleted",
            "student_id": student_id,
            "email": email,
            "deleted_repos": deleted_repos,
            "message": f"Student #{student_id} ({email}) has been completely wiped from the database{' and ' + str(len(deleted_repos)) + ' GitHub repo(s) deleted' if deleted_repos else ''}. When they return, they will be treated as a brand-new user."
        }
    except Exception as e:
        logger.error(f"Failed to delete student {student_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database error while deleting student: {str(e)}")


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
    - PR stats (submitted, merged, failed)
    - Revenue from certificate payments
    """
    batch = await db.fetch_one("SELECT * FROM batches WHERE id = ?", (batch_id,))
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    # Enrollment stats
    enrollment_stats = await db.fetch_one(
        """SELECT
             COUNT(*) as total,
             SUM(CASE WHEN e.status = 'enrolled' OR e.status = 'active' THEN 1 ELSE 0 END) as active,
             SUM(CASE WHEN e.status = 'dropped' THEN 1 ELSE 0 END) as dropped,
             SUM(CASE WHEN e.status = 'completed' THEN 1 ELSE 0 END) as completed
           FROM enrollments e WHERE e.batch_id = ?""",
        (batch_id,)
    )

    # Per-week progress aggregates
    weekly_progress = await db.fetch_all(
        """SELECT week,
             SUM(issues_assigned) as assigned,
             SUM(issues_completed) as completed,
             SUM(prs_submitted) as prs_submitted,
             SUM(prs_merged) as prs_merged
           FROM progress WHERE batch_id = ?
           GROUP BY week ORDER BY week""",
        (batch_id,)
    )

    # PR stats from submissions table
    pr_stats = await db.fetch_one(
        """SELECT
             COUNT(*) as total_prs,
             SUM(CASE WHEN status = 'merged' THEN 1 ELSE 0 END) as merged,
             SUM(CASE WHEN status = 'tests_failed' THEN 1 ELSE 0 END) as failed,
             SUM(CASE WHEN status IN ('open','tests_passed') THEN 1 ELSE 0 END) as open_prs
           FROM submissions WHERE batch_id = ?""",
        (batch_id,)
    )

    # Revenue from payments
    revenue = await db.fetch_one(
        """SELECT
             COUNT(*) as total_payments,
             SUM(CASE WHEN status = 'paid' THEN amount ELSE 0 END) as total_paise
           FROM payments WHERE batch_id = ?""",
        (batch_id,)
    )

    # Per-student progress grid
    student_grid = await db.fetch_all(
        """SELECT s.id, s.first_name, s.last_name, s.github_username,
                  e.status as enrollment_status,
                  (SELECT COUNT(*) FROM issues i WHERE i.batch_id = e.batch_id AND (i.assigned_to = s.id OR i.assigned_to IS NULL)) as tasks_assigned,
                  SUM(p.issues_completed) as tasks_completed,
                  SUM(p.prs_merged) as prs_merged
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
        "pr_stats": dict(pr_stats) if pr_stats else {},
        "revenue": {
            "total_payments": revenue["total_payments"] if revenue else 0,
            "total_inr": (revenue["total_paise"] or 0) // 100 if revenue else 0,
        },
        "student_grid": [dict(s) for s in student_grid],
    }


# ──────────────────────────────────────────────
# GitHub Invite Reminder Emails
# ──────────────────────────────────────────────

@router.get("/emails/pending-github-invite", summary="List students with pending GitHub invites")
async def list_pending_github_invites(_: str = Depends(require_admin)):
    """
    Returns all enrolled students whose GitHub collaborator invite is still pending.
    Use this to preview who the invite reminder email will be sent to before firing it.
    """
    rows = await db.fetch_all(
        """SELECT
             s.id, s.first_name, s.last_name, s.email,
             s.github_username, s.domain,
             e.github_invite_status, e.joined_at,
             b.repo_name, b.domain as batch_domain, b.id as batch_id
           FROM enrollments e
           JOIN students s ON s.id = e.student_id
           JOIN batches b ON b.id = e.batch_id
           WHERE e.github_invite_status = 'pending'
             AND e.status NOT IN ('dropped')
           ORDER BY e.joined_at ASC"""
    )

    students = []
    org = settings.github_org or "skill-me-intern"
    for r in rows:
        repo_url = f"https://github.com/{org}/{r['repo_name']}" if r.get("repo_name") else None
        students.append({
            "student_id":          r["id"],
            "name":                f"{r['first_name']} {r['last_name']}",
            "first_name":          r["first_name"],
            "email":               r["email"],
            "github_username":     r["github_username"],
            "domain":              r["batch_domain"] or r["domain"],
            "repo_name":           r["repo_name"],
            "repo_url":            repo_url,
            "batch_id":            r["batch_id"],
            "invite_status":       r["github_invite_status"],
            "joined_at":           r["joined_at"],
        })

    return {
        "count": len(students),
        "students": students,
        "message": f"{len(students)} student(s) have a pending GitHub collaborator invite.",
    }


from fastapi import Body

@router.post("/emails/send-github-invite-reminder", summary="Send GitHub invite reminder to pending students")
async def send_github_invite_reminders(
    background_tasks: BackgroundTasks,
    student_ids: list[int] | None = Body(None),
    _: str = Depends(require_admin),
):
    """
    Sends a GitHub collaboration invite reminder email to all enrolled students
    whose invite_status is still 'pending'. 

    - If `student_ids` is provided (JSON body list of ints), only those students are emailed.
    - If omitted, ALL pending-invite students are emailed.

    Emails are dispatched in the background so the API responds immediately.
    Returns the list of students the email is being sent to.
    """
    # Build the query — filter by student_ids if provided
    rows = await db.fetch_all(
        """SELECT
             s.id, s.first_name, s.last_name, s.email,
             s.github_username, s.domain,
             b.repo_name, b.domain as batch_domain, b.id as batch_id
           FROM enrollments e
           JOIN students s ON s.id = e.student_id
           JOIN batches b ON b.id = e.batch_id
           WHERE e.github_invite_status = 'pending'
             AND e.status NOT IN ('dropped')
           ORDER BY e.joined_at ASC"""
    )

    org = settings.github_org or "skill-me-intern"
    targets = []
    for r in rows:
        if student_ids and r["id"] not in student_ids:
            continue
        targets.append(dict(r))

    if not targets:
        return {
            "status": "no_targets",
            "message": "No students with pending GitHub invites found (or none matched the provided IDs).",
            "sent_to": [],
        }

    async def _fire_emails():
        for t in targets:
            repo_url = f"https://github.com/{org}/{t['repo_name']}" if t.get("repo_name") else None
            domain = t.get("batch_domain") or t.get("domain") or "web-dev"
            try:
                await email_service.send_github_invite_reminder(
                    first_name=t["first_name"],
                    last_name=t["last_name"],
                    email=t["email"],
                    domain=domain,
                    repo_url=repo_url,
                    github_email=t["email"],
                )
                logger.info(
                    f"GitHub invite reminder sent → {t['email']} "
                    f"(student_id={t['id']}, repo={t.get('repo_name')})"
                )
            except Exception as exc:
                logger.error(f"Failed to send invite reminder to {t['email']}: {exc}")

    background_tasks.add_task(_fire_emails)

    sent_to = [
        {
            "student_id":      t["id"],
            "name":            f"{t['first_name']} {t['last_name']}",
            "email":           t["email"],
            "github_username": t.get("github_username"),
            "repo_name":       t.get("repo_name"),
        }
        for t in targets
    ]

    return {
        "status": "dispatched",
        "message": f"Reminder emails are being sent to {len(targets)} student(s) in the background.",
        "sent_to": sent_to,
    }

