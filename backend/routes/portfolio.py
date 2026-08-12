from fastapi import APIRouter, HTTPException
from db.database import db

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

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

    # 2. Check if student has paid for the certificate/portfolio
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
             COALESCE(SUM(prs_merged), 0) as total_prs_merged,
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

    # 5. Fetch their recent merged submissions to act as "Proof of Work"
    submissions = await db.fetch_all(
        """SELECT s.pr_url, s.pr_number, s.merged_at, s.submitted_at, i.title, b.domain 
           FROM submissions s
           JOIN issues i ON s.issue_id = i.id
           JOIN batches b ON s.batch_id = b.id
           WHERE s.student_id = ? AND s.status = 'merged'
           ORDER BY COALESCE(s.merged_at, s.submitted_at) DESC
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
