"""
SkillMe — Student API Routes
Public endpoints for student applications and status checks.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field, EmailStr
from db.database import db
from services.email_service import email_service

router = APIRouter(prefix="/api/students", tags=["students"])


# ──────────────────────────────────────────────
# Request Models
# ──────────────────────────────────────────────

class ApplicationRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=5, max_length=200)
    phone: str | None = Field(None, max_length=20)
    github_username: str | None = Field(None, max_length=100)
    linkedin_url: str | None = Field(None, max_length=300)
    college: str | None = Field(None, max_length=200)
    year_of_study: str | None = Field(None, max_length=50)
    domain: str = Field(..., description="Preferred domain")
    motivation: str | None = Field(None, max_length=1000)
    referral_source: str | None = Field(None, max_length=100)
    referred_by: str | None = Field(None, max_length=20)  # referral code e.g. SKM-A1B2C3


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────

@router.post("/apply", summary="Submit an application")
async def apply(req: ApplicationRequest, background_tasks: BackgroundTasks):
    """
    Submit a new student application.
    This is called by the apply.html form.
    """
    import traceback
    try:
        # Check for duplicate email
        req.email = req.email.strip()
        existing = await db.fetch_one(
            "SELECT id, status FROM students WHERE lower(email) = lower(?)", (req.email,)
        )
        if existing:
            return {
                "status": "already_applied",
                "message": "An application with this email already exists.",
                "student_id": existing["id"],
                "current_status": existing["status"],
            }

        # Extract GitHub username from URL if full URL provided
        github_username = req.github_username
        if github_username and "github.com/" in github_username:
            github_username = github_username.rstrip("/").split("/")[-1]

        # Insert student record
        student_id = await db.insert(
            """INSERT INTO students 
               (first_name, last_name, email, phone, github_username, linkedin_url, 
                college, year_of_study, domain, motivation, referral_source, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'applied')""",
            (
                req.first_name,
                req.last_name,
                req.email,
                req.phone,
                github_username,
                req.linkedin_url,
                req.college,
                req.year_of_study,
                req.domain,
                req.motivation,
                req.referral_source,
            ),
        )

        # Fire confirmation email in the background (non-blocking)
        background_tasks.add_task(
            email_service.send_application_confirmation,
            first_name=req.first_name,
            last_name=req.last_name,
            email=req.email,
            domain=req.domain,
            github_username=github_username or "",
        )

        # Track referral if a code was provided
        if req.referred_by:
            try:
                from routes.referrals import record_referral_application
                await record_referral_application(req.email, student_id, req.referred_by)
            except Exception:
                pass  # Referral tracking is best-effort

        return {
            "status": "applied",
            "message": "Application submitted successfully! You'll hear from us within 48 hours.",
            "student_id": student_id,
        }
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


@router.get("/status/{email}", summary="Check application status")
async def check_status(email: str):
    """Check the status of a student's application by email."""
    student = await db.fetch_one(
        "SELECT id, first_name, last_name, email, status, created_at FROM students WHERE lower(email) = lower(?)",
        (email.strip(),),
    )
    if not student:
        raise HTTPException(status_code=404, detail="No application found with this email")

    # Get enrollments if any
    enrollments = await db.fetch_all(
        """SELECT b.domain, b.batch_number, e.status as enrollment_status
           FROM enrollments e
           JOIN batches b ON e.batch_id = b.id
           WHERE e.student_id = ?""",
        (student["id"],),
    )

    return {
        "student": student,
        "enrollments": enrollments,
    }


@router.get("/progress/{email}", summary="Get student progress")
async def get_progress(email: str):
    """Get a student's internship progress by email."""
    student = await db.fetch_one(
        "SELECT * FROM students WHERE lower(email) = lower(?)", (email.strip(),)
    )
    if not student:
        raise HTTPException(status_code=404, detail="Student not found with this email.")

    progress = await db.fetch_all(
        """SELECT p.week, p.issues_assigned, p.issues_completed, p.prs_merged, p.score,
                  b.domain, b.batch_number, b.id as batch_id
           FROM progress p
           JOIN batches b ON p.batch_id = b.id
           WHERE p.student_id = ?
           ORDER BY b.domain, p.week""",
        (student["id"],),
    )

    if not progress:
        # Fallback to enrollments table if no progress rows exist yet
        enrollments = await db.fetch_all(
            """SELECT 1 as week, 0 as issues_assigned, 0 as issues_completed, 0 as prs_merged, 0 as score,
                      b.domain, b.batch_number, b.id as batch_id
               FROM enrollments e
               JOIN batches b ON e.batch_id = b.id
               WHERE e.student_id = ? AND e.status != 'dropped'""",
            (student["id"],),
        )
        if enrollments:
            progress = enrollments

    submissions = await db.fetch_all(
        """SELECT s.pr_url, s.pr_number, s.status, s.submitted_at, s.merged_at,
                  i.title as issue_title, i.week_number
           FROM submissions s
           LEFT JOIN issues i ON s.issue_id = i.id
           WHERE s.student_id = ?
           ORDER BY s.submitted_at DESC""",
        (student["id"],),
    )

    return {
        "student": {
            "id": student["id"],
            "name": f"{student['first_name']} {student['last_name']}",
            "email": student["email"],
            "github": student["github_username"],
        },
        "progress": [dict(p) for p in progress],
        "submissions": [dict(s) for s in submissions],
        "summary": {
            "total_tasks": sum(p["issues_assigned"] for p in progress),
            "completed_tasks": sum(p["issues_completed"] for p in progress),
            "prs_merged": sum(p["prs_merged"] for p in progress),
            "total_prs": len([s for s in submissions]),
            "completion_pct": round(
                sum(p["issues_completed"] for p in progress) /
                max(sum(p["issues_assigned"] for p in progress), 1) * 100
            ),
        },
    }


@router.get("/progress/id/{student_id}", summary="Get student progress by ID")
async def get_progress_by_id(student_id: int):
    """Get a student's internship progress by student ID (used by auth'd dashboard)."""
    student = await db.fetch_one(
        "SELECT * FROM students WHERE id = ?", (student_id,)
    )
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")

    # Re-use the same logic via email
    from fastapi import Request
    return await get_progress(student["email"])
