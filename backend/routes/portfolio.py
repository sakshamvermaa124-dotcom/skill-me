from fastapi import APIRouter, HTTPException
from db.database import db

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

_STUDENT_COLUMNS = "id, first_name, last_name, github_username, college, domain"


async def _build_portfolio(student) -> dict:
    """
    Assemble the public portfolio payload for a student row.
    Requires at least one 'paid' payment record, otherwise raises 403 payment_required.
    """
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    student_id = student["id"]

    # Completion eligibility is enforced upstream at payment order creation (see
    # routes/payments.py create_order) — below 3 of 4 approved tasks, an order requires an admin-unlocked
    # urgent request. A 'paid' record here is therefore sufficient proof on its own.
    payment = await db.fetch_one(
        "SELECT id FROM payments WHERE student_id = ? AND status = 'paid' LIMIT 1",
        (student_id,)
    )
    if not payment:
        # Specific error code so the frontend can show "Portfolio not activated"
        raise HTTPException(status_code=403, detail="payment_required")

    stats = await db.fetch_one(
        """SELECT
             COALESCE(SUM(issues_completed), 0) as total_tasks_completed,
             COALESCE(SUM(score), 0) as total_score
           FROM progress WHERE student_id = ?""",
        (student_id,)
    )

    # Domains they completed/enrolled in (paid enrollments count even if later dropped)
    enrolled_domains = await db.fetch_all(
        """SELECT DISTINCT b.domain
           FROM enrollments e
           JOIN batches b ON e.batch_id = b.id
           WHERE e.student_id = ?
             AND (e.status IN ('enrolled', 'active', 'completed')
                  OR EXISTS (SELECT 1 FROM payments p WHERE p.student_id = e.student_id
                             AND p.batch_id = e.batch_id AND p.status = 'paid'))""",
        (student_id,)
    )
    domains = [d["domain"] for d in enrolled_domains if d["domain"]]
    if not domains and student["domain"]:
        domains = [student["domain"]]

    # Approved LinkedIn milestone posts act as "Proof of Work".
    # admin_note is internal reviewer context and must never be exposed here.
    submissions = await db.fetch_all(
        """SELECT s.id, s.week, s.linkedin_url, s.submitted_at, s.reviewed_at, b.domain
           FROM submissions s
           LEFT JOIN batches b ON s.batch_id = b.id
           WHERE s.student_id = ? AND s.status = 'approved'
           ORDER BY s.week ASC, COALESCE(s.reviewed_at, s.submitted_at) ASC""",
        (student_id,)
    )

    first = student["first_name"] or ""
    last = student["last_name"] or ""
    return {
        "profile": {
            "id": student_id,
            "name": f"{first} {last}".strip(),
            "first_name": first,
            "last_name": last,
            "github_username": student["github_username"] or "",
            "college": student["college"],
            "domain": student["domain"],
        },
        "stats": dict(stats) if stats else {"total_tasks_completed": 0, "total_score": 0},
        "domains": domains,
        "submissions": [dict(s) for s in submissions],
    }


@router.get("/id/{student_id}")
async def get_portfolio_by_id(student_id: int):
    """Fetch a student's portfolio by student ID (the link shared from the dashboard)."""
    student = await db.fetch_one(
        f"SELECT {_STUDENT_COLUMNS} FROM students WHERE id = ?",
        (student_id,)
    )
    return await _build_portfolio(student)


@router.get("/{github_username}")
async def get_portfolio(github_username: str):
    """Fetch a student's portfolio by GitHub username (legacy /p/:github links, case-insensitive)."""
    student = await db.fetch_one(
        f"SELECT {_STUDENT_COLUMNS} FROM students WHERE LOWER(github_username) = LOWER(?)",
        (github_username,)
    )
    return await _build_portfolio(student)
