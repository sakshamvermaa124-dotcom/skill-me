"""
End-to-end: does the portfolio actually reflect a fresh task approval?
Exercises the real admin approve_submission service (not a stub) then re-fetches
the portfolio to check stats/domains/submissions all update.
"""
import pytest
from tests.conftest import test_db, seed_student, seed_batch, seed_enrollment, seed_payment


@pytest.mark.asyncio
async def test_portfolio_reflects_new_approval_live(client, admin_headers):
    student_id = await seed_student(test_db, email="e2e@example.com", github_username="e2euser")
    batch_id = await seed_batch(test_db, domain="web-dev")
    await seed_enrollment(test_db, student_id, batch_id)
    await seed_payment(test_db, student_id, batch_id)

    # Before any submission: portfolio should show zero milestones, but still load (paid).
    before = await client.get(f"/api/portfolio/id/{student_id}")
    assert before.status_code == 200
    assert before.json()["submissions"] == []
    assert before.json()["stats"]["total_score"] == 0

    # Student submits a milestone (pending) — should NOT show up yet.
    sub_id = await test_db.insert(
        """INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status)
           VALUES (?, ?, 1, 'https://www.linkedin.com/feed/update/urn:li:activity:999', 'pending')""",
        (student_id, batch_id),
    )
    mid = await client.get(f"/api/portfolio/id/{student_id}")
    assert mid.json()["submissions"] == [], "pending submission leaked into public portfolio"

    # Admin approves it via the REAL route (exercises submission_service + progress table).
    approve = await client.post(f"/api/admin/submissions/{sub_id}/approve", headers=admin_headers)
    assert approve.status_code == 200, approve.text
    assert approve.json()["status"] == "approved"

    # Portfolio must now show the milestone AND updated score/tasks-completed.
    after = await client.get(f"/api/portfolio/id/{student_id}")
    data = after.json()
    assert len(data["submissions"]) == 1, data
    assert data["submissions"][0]["week"] == 1
    assert data["submissions"][0]["domain"] == "web-dev"
    assert data["stats"]["total_score"] > 0, "score did not update after approval"
    assert data["stats"]["total_tasks_completed"] == 1
    assert "web-dev" in data["domains"]
