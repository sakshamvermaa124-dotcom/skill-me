from fastapi import APIRouter, HTTPException
from db.database import db

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


async def _completion_pct(student_id: int) -> int:
    """
    Completion % across all of a student's batches: distinct (batch_id, week)
    pairs with issues_completed > 0, out of 4 tasks per batch they're in.
    """
    progress_rows = await db.fetch_all(
        "SELECT DISTINCT batch_id, week FROM progress WHERE student_id = ? AND issues_completed > 0",
        (student_id,),
    )
    batch_ids = await db.fetch_all(
        """SELECT DISTINCT batch_id FROM (
               SELECT batch_id FROM progress WHERE student_id = ?
               UNION
               SELECT batch_id FROM enrollments WHERE student_id = ?
           )""",
        (student_id, student_id),
    )
    num_batches = max(1, len(batch_ids))
    completed = len({(r["batch_id"], r["week"]) for r in progress_rows})
    return min(100, round(completed / (4 * num_batches) * 100))


@router.get("/{github_username}")
async def get_portfolio(github_username: str):
    """
    Fetch a student's portfolio data using their GitHub username.
    This endpoint requires the student to have at least one 'paid' payment record.
    """
    # 1. Look up student by github_username (case-insensitive)
    student = await db.fetch_one(
        "SELECT id, first_name, last_name, github_username, email, college, domain FROM students WHERE LOWER(github_username) = LOWER(?)",
        (github_username,)
    )
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    student_id = student["id"]

    # 2. Check completion — portfolio unlocks only past 50% task completion
    completion_pct = await _completion_pct(student_id)
    if completion_pct < 50:
        raise HTTPException(status_code=403, detail="incomplete_progress")

    # 3. Check if student has paid for the certificate/portfolio
    payment = await db.fetch_one(
        "SELECT id FROM payments WHERE student_id = ? AND status = 'paid' LIMIT 1",
        (student_id,)
    )

    if not payment:
        # We return a specific error code so the frontend knows to show "Portfolio not activated - Ask to pay"
        raise HTTPException(status_code=403, detail="payment_required")

    # 3. Aggregate progress stats across all batches
    stats = await db.fetch_one(
        """SELECT
             COALESCE(SUM(issues_completed), 0) as total_tasks_completed,
             COALESCE(SUM(score), 0) as total_score
           FROM progress WHERE student_id = ?""",
        (student_id,)
    )

    # 4. Fetch the batches/domains they successfully completed/enrolled in
    batches = await db.fetch_all(
        """SELECT b.domain, b.batch_number, e.status
           FROM enrollments e
           JOIN batches b ON e.batch_id = b.id
           WHERE e.student_id = ? AND e.status IN ('enrolled', 'active', 'completed')""",
        (student_id,)
    )

    # 5. Fetch their approved LinkedIn submissions to act as "Proof of Work"
    submissions = await db.fetch_all(
        """SELECT s.linkedin_url, s.week, s.reviewed_at, s.submitted_at, b.domain
           FROM submissions s
           JOIN batches b ON s.batch_id = b.id
           WHERE s.student_id = ? AND s.status = 'approved'
           ORDER BY COALESCE(s.reviewed_at, s.submitted_at) DESC
           LIMIT 10""",
        (student_id,)
    )

    return {
        "profile": {
            "name": f"{student['first_name']} {student['last_name']}",
            "github_username": student["github_username"],
            "college": student["college"]
        },
        "stats": stats,
        "domains": [b["domain"] for b in batches],
        "submissions": submissions
    }




@router.get("/id/{student_id}")
async def get_portfolio_by_id(student_id: int):
    # 1. Look up student by id
    student = await db.fetch_one(
        "SELECT id, first_name, last_name, github_username, email, college, domain FROM students WHERE id = ?",
        (student_id,)
    )
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # 2. Check completion — portfolio unlocks only past 50% task completion
    completion_pct = await _completion_pct(student_id)
    if completion_pct < 50:
        raise HTTPException(status_code=403, detail="incomplete_progress")

    # 3. Check if student has paid for the certificate/portfolio
    payment = await db.fetch_one(
        "SELECT id FROM payments WHERE student_id = ? AND status = 'paid' LIMIT 1",
        (student_id,)
    )

    if not payment:
        raise HTTPException(status_code=403, detail="payment_required")

    # 3. Aggregate progress stats across all batches
    stats = await db.fetch_one(
        "SELECT COALESCE(SUM(issues_completed), 0) as total_tasks_completed, COALESCE(SUM(score), 0) as total_score FROM progress WHERE student_id = ?",
        (student_id,)
    )

    # 4. Fetch the batches/domains they successfully completed/enrolled in
    batches = await db.fetch_all(
        "SELECT b.domain, b.batch_number, e.status FROM enrollments e JOIN batches b ON e.batch_id = b.id WHERE e.student_id = ? AND e.status IN ('enrolled', 'active', 'completed')",
        (student_id,)
    )

    # 5. Fetch their approved LinkedIn submissions
    submissions = await db.fetch_all(
        "SELECT id, linkedin_url, week, admin_note, status, created_at FROM submissions WHERE student_id = ? AND status = 'approved' ORDER BY week ASC",
        (student_id,)
    )

    return {
        "student": {
            "first_name": student["first_name"],
            "last_name": student["last_name"],
            "github_username": student["github_username"] or "",
            "college": student["college"],
            "domain": student["domain"]
        },
        "stats": dict(stats),
        "domains": [b["domain"] for b in batches],
        "submissions": [dict(s) for s in submissions]
    }
