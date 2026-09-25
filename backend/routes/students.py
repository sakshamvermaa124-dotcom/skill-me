"""
SkillMe — Student API Routes
Public endpoints for student applications, status checks, and LinkedIn task submissions.
"""

import logging

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from db.database import db
from services.email_service import email_service, _domain_label
from services.submission_service import submission_service
from services.urgent_request_service import urgent_request_service
from services.enrollment_service import enrollment_service

logger = logging.getLogger("skillme.students")
router = APIRouter(prefix="/api/students", tags=["students"])


# ──────────────────────────────────────────────
# Request Models
# ──────────────────────────────────────────────

class ApplicationRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=5, max_length=200)
    phone: str | None = Field(None, max_length=20)
    linkedin_url: str | None = Field(None, max_length=300)
    college: str | None = Field(None, max_length=200)
    year_of_study: str | None = Field(None, max_length=50)
    domain: str = Field(..., description="Preferred domain")
    motivation: str | None = Field(None, max_length=1000)
    referral_source: str | None = Field(None, max_length=100)


class SubmitTaskRequest(BaseModel):
    student_id: int
    batch_id: int | None = None  # internal enrollment reference, validated server-side
    week: int = Field(..., ge=1, le=4)
    linkedin_url: str = Field(..., max_length=500)


class UrgentRequestRequest(BaseModel):
    student_id: int
    batch_id: int | None = None  # internal enrollment reference, validated server-side
    request_type: str = Field("all", description="certificate | lor | portfolio | all")
    note: str | None = Field(None, max_length=500)


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

        # Insert student record
        student_id = await db.insert(
            """INSERT INTO students
               (first_name, last_name, email, phone, linkedin_url,
                college, year_of_study, domain, motivation, referral_source, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'applied')""",
            (
                req.first_name,
                req.last_name,
                req.email,
                req.phone,
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
        )

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

    enrollment = await enrollment_service.get_current_enrollment(student["id"])
    enrollments = (
        [{"domain": enrollment["domain"], "enrollment_status": enrollment["status"]}]
        if enrollment else []
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

    # Everything on the dashboard is scoped to the student's single current enrollment,
    # so stale rows from an old/dropped enrollment can never leak in.
    enrollment = await enrollment_service.get_current_enrollment(student["id"])
    progress: list[dict] = []
    submissions: list[dict] = []
    if enrollment:
        batch_id = enrollment["batch_id"]
        progress = await db.fetch_all(
            """SELECT week, issues_completed, score, ? AS domain, ? AS batch_id, ? AS start_date
               FROM progress
               WHERE student_id = ? AND batch_id = ?
               ORDER BY week""",
            (enrollment["domain"], batch_id, enrollment["start_date"], student["id"], batch_id),
        )
        if not progress and enrollment["status"] != "dropped":
            # No approved work yet — still expose the enrollment so the dashboard can load tasks
            progress = [{
                "week": 1, "issues_completed": 0, "score": 0,
                "domain": enrollment["domain"], "batch_id": batch_id,
                "start_date": enrollment["start_date"],
            }]
        submissions = await db.fetch_all(
            """SELECT id, week, linkedin_url, status, admin_note, feedback,
                      submitted_at, reviewed_at, ? AS domain
               FROM submissions
               WHERE student_id = ? AND batch_id = ?
               ORDER BY week ASC""",
            (enrollment["domain"], student["id"], batch_id),
        )

    primary_domain = student.get("domain") or (enrollment["domain"] if enrollment else "Web Development")
    payment_unlocked = bool(enrollment and enrollment["payment_unlocked_at"])

    return {
        "student": {
            "id": student["id"],
            "first_name": student["first_name"],
            "last_name": student["last_name"],
            "name": f"{student['first_name']} {student['last_name']}",
            "email": student["email"],
            "domain": primary_domain,
            "college": student.get("college"),
        },
        "progress": [dict(p) for p in progress],
        "submissions": [dict(s) for s in submissions],
        "summary": {
            "total_tasks": 4,
            # Count of distinct weeks with any credit (not a raw sum) — this stays correct
            # both for legacy weeks that had multiple merged PRs and for the new one-
            # submission-per-week model, where issues_completed can only ever be 0 or 1.
            "completed_tasks": len({int(p["week"]) for p in progress if int(p["issues_completed"]) > 0}),
            "completion_pct": min(100, round(
                len({int(p["week"]) for p in progress if int(p["issues_completed"]) > 0}) / 4 * 100
            )),
            "payment_unlocked": payment_unlocked,
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

    return await get_progress(student["email"])


@router.post("/submit-task", summary="Submit a LinkedIn post URL for a week's task")
async def submit_task(req: SubmitTaskRequest, background_tasks: BackgroundTasks):
    """
    Student submits a LinkedIn post URL for a given week's task.
    The submission is queued as 'pending' until an admin reviews it, and the student is
    emailed automatic feedback for that task.
    """
    batch_id = await enrollment_service.resolve_batch_id(req.student_id, req.batch_id)
    if not batch_id:
        raise HTTPException(status_code=400, detail="You are not enrolled in an internship yet.")
    try:
        result = await submission_service.submit_linkedin_url(
            student_id=req.student_id,
            batch_id=batch_id,
            week=req.week,
            linkedin_url=req.linkedin_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    student = await db.fetch_one(
        """SELECT s.first_name, s.last_name, s.email, COALESCE(b.domain, s.domain) AS domain
           FROM students s LEFT JOIN batches b ON b.id = ?
           WHERE s.id = ?""",
        (batch_id, req.student_id),
    )
    if student:
        background_tasks.add_task(
            email_service.send_submission_feedback,
            first_name=student["first_name"],
            last_name=student["last_name"],
            email=student["email"],
            domain=student["domain"] or "web-dev",
            week=req.week,
            feedback=result["feedback"],
            student_id=req.student_id,
            batch_id=batch_id,
        )
    return result


@router.post("/urgent-request", summary="Request 24h expedited certificate/LOR/portfolio processing")
async def create_urgent_request(req: UrgentRequestRequest):
    """
    Student requests urgent (24h) processing of their certificate, LOR, or portfolio.
    Open to students below the payment threshold (3 of 4 tasks approved), who don't otherwise have direct
    payment access — an admin reviews and, if fulfilled, unlocks payment for them.
    """
    batch_id = await enrollment_service.resolve_batch_id(req.student_id, req.batch_id)
    if not batch_id:
        raise HTTPException(status_code=400, detail="You are not enrolled in an internship yet.")
    try:
        return await urgent_request_service.create_request(
            student_id=req.student_id,
            batch_id=batch_id,
            request_type=req.request_type,
            note=req.note,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/urgent-request/status/{student_id}/{batch_id}", summary="Get latest urgent request status")
async def get_urgent_request_status(student_id: int, batch_id: int):
    """Returns the student's most recent urgent request, or null if none exists."""
    resolved = await enrollment_service.resolve_batch_id(student_id, batch_id)
    if not resolved:
        return {"request": None}
    row = await db.fetch_one(
        """SELECT * FROM urgent_requests
           WHERE student_id = ? AND batch_id = ?
           ORDER BY created_at DESC, id DESC LIMIT 1""",
        (student_id, resolved),
    )
    return {"request": dict(row) if row else None}


@router.get("/public-activity", summary="Get live public proof-of-work activity feed")
async def get_public_activity():
    """
    Real platform metrics and the latest admin-approved submissions (names anonymised,
    no photos). Every number and entry comes from the database — nothing is padded or
    invented, so an empty or small feed is expected early on.
    """
    import datetime

    def _time_ago(ts) -> str:
        try:
            then = datetime.datetime.fromisoformat(str(ts).replace("Z", "").split(".")[0])
        except ValueError:
            return "Recently"
        minutes = int((datetime.datetime.utcnow() - then).total_seconds() // 60)
        if minutes < 1:
            return "Just now"
        if minutes < 60:
            return f"{minutes}m ago"
        if minutes < 60 * 24:
            return f"{minutes // 60}h ago"
        return f"{minutes // (60 * 24)}d ago"

    try:
        db_approved = await db.fetch_one("SELECT count(id) as count FROM submissions WHERE status = 'approved'")
        db_students = await db.fetch_one("SELECT count(id) as count FROM students")
        db_certs = await db.fetch_one("SELECT count(id) as count FROM certificates")
        db_colleges = await db.fetch_one("SELECT count(DISTINCT college) as count FROM students WHERE college IS NOT NULL AND TRIM(college) != ''")
        db_review = await db.fetch_one(
            """SELECT AVG((julianday(reviewed_at) - julianday(submitted_at)) * 24) AS hours
               FROM submissions
               WHERE status = 'approved' AND reviewed_at IS NOT NULL
                 AND julianday('now') - julianday(reviewed_at) <= 30"""
        )

        activities = []
        recent_subs = await db.fetch_all(
            """SELECT s.id, s.week, s.submitted_at, s.reviewed_at,
                      st.first_name, st.last_name, st.college, st.domain
               FROM submissions s
               JOIN students st ON s.student_id = st.id
               WHERE s.status = 'approved'
               ORDER BY s.reviewed_at DESC LIMIT 12"""
        )
        for sub in recent_subs:
            fname = (sub["first_name"] or "").strip()
            lname = (sub["last_name"] or "").strip()
            initials = f"{fname[0].upper() if fname else 'S'}{lname[0].upper() if lname else 'M'}"
            anon_name = f"{fname.capitalize()} {lname[0].upper()}." if (fname and lname) else "Student Contributor"
            college = (sub["college"] or "Engineering College").strip()
            if len(college) > 20 and "(" in college:
                college = college.split("(")[0].strip()

            domain_raw = (sub["domain"] or "web-dev").lower()
            domain_name = _domain_label(domain_raw)
            week = sub["week"] or 1

            activities.append({
                "id": f"db-sub-{sub['id']}",
                "type": "submission_approved",
                "student_initials": initials,
                "student_name": anon_name,
                "college": college[:24],
                "domain": domain_name,
                "domain_slug": domain_raw,
                "badge_text": f"Week {week} Approved",
                "action_text": f"had their Week {week} milestone approved",
                "time_ago": _time_ago(sub["reviewed_at"] or sub["submitted_at"]),
                "icon": "check-circle",
                "verified": True
            })

        hours = db_review["hours"] if db_review else None
        return {
            "status": "success",
            "stats": {
                "total_submissions_approved": db_approved["count"] if db_approved else 0,
                "total_students": db_students["count"] if db_students else 0,
                "total_certificates": db_certs["count"] if db_certs else 0,
                "total_colleges": db_colleges["count"] if db_colleges else 0,
                "avg_review_hours": round(float(hours), 1) if hours is not None else None,
            },
            "activities": activities,
            "timestamp": datetime.datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.warning("public-activity failed: %s", e)
        return {"status": "unavailable", "stats": None, "activities": []}
