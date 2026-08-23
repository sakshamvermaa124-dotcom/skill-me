"""
Admin Tests — LinkedIn Submission Review Queue
Tests the submit → list → approve/reject → bulk-approve/bulk-reject flow.
"""
import pytest
from tests.conftest import test_db, seed_batch, seed_enrollment


@pytest.mark.admin
class TestSubmitTask:
    async def test_submit_task_pending(self, client, enrolled_student):
        r = await client.post(
            "/api/students/submit-task",
            json={
                "student_id": enrolled_student["id"],
                "batch_id": enrolled_student["batch_id"],
                "week": 1,
                "linkedin_url": "https://www.linkedin.com/posts/test-post",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "pending"

    async def test_submit_task_rejects_non_linkedin_url(self, client, enrolled_student):
        r = await client.post(
            "/api/students/submit-task",
            json={
                "student_id": enrolled_student["id"],
                "batch_id": enrolled_student["batch_id"],
                "week": 1,
                "linkedin_url": "https://example.com/not-linkedin",
            },
        )
        assert r.status_code == 400

    async def test_submit_task_not_enrolled(self, client, test_student, test_batch):
        r = await client.post(
            "/api/students/submit-task",
            json={
                "student_id": test_student["id"],
                "batch_id": test_batch["id"],
                "week": 1,
                "linkedin_url": "https://www.linkedin.com/posts/test-post",
            },
        )
        assert r.status_code == 400

    async def test_duplicate_pending_submission_rejected(self, client, enrolled_student):
        payload = {
            "student_id": enrolled_student["id"],
            "batch_id": enrolled_student["batch_id"],
            "week": 1,
            "linkedin_url": "https://www.linkedin.com/posts/test-post",
        }
        await client.post("/api/students/submit-task", json=payload)
        r2 = await client.post("/api/students/submit-task", json=payload)
        assert r2.status_code == 400


@pytest.mark.admin
class TestSubmissionReviewQueue:
    async def test_list_pending_submissions(self, client, admin_headers, enrolled_student):
        await client.post(
            "/api/students/submit-task",
            json={
                "student_id": enrolled_student["id"],
                "batch_id": enrolled_student["batch_id"],
                "week": 1,
                "linkedin_url": "https://www.linkedin.com/posts/test-post",
            },
        )
        r = await client.get("/api/admin/submissions?status=pending", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 1

    async def test_approve_submission_increments_progress(self, client, admin_headers, enrolled_student):
        sub = await client.post(
            "/api/students/submit-task",
            json={
                "student_id": enrolled_student["id"],
                "batch_id": enrolled_student["batch_id"],
                "week": 1,
                "linkedin_url": "https://www.linkedin.com/posts/test-post",
            },
        )
        submission_id = sub.json()["submission_id"]

        r = await client.post(
            f"/api/admin/submissions/{submission_id}/approve",
            json={},
            headers=admin_headers,
        )
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

        progress = await test_db.fetch_one(
            "SELECT issues_completed, score FROM progress WHERE student_id = ? AND batch_id = ? AND week = 1",
            (enrolled_student["id"], enrolled_student["batch_id"]),
        )
        assert progress["issues_completed"] == 1
        assert progress["score"] == 25

    async def test_reject_submission_allows_resubmit(self, client, admin_headers, enrolled_student):
        payload = {
            "student_id": enrolled_student["id"],
            "batch_id": enrolled_student["batch_id"],
            "week": 1,
            "linkedin_url": "https://www.linkedin.com/posts/test-post",
        }
        sub = await client.post("/api/students/submit-task", json=payload)
        submission_id = sub.json()["submission_id"]

        r = await client.post(
            f"/api/admin/submissions/{submission_id}/reject",
            json={"admin_note": "Please tag @SkillMe"},
            headers=admin_headers,
        )
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"

        # Resubmission should now succeed
        r2 = await client.post("/api/students/submit-task", json=payload)
        assert r2.status_code == 200
        assert r2.json()["status"] == "pending"

    async def test_bulk_approve_submissions(self, client, admin_headers, test_batch):
        student_ids = []
        from tests.conftest import seed_student
        for i in range(3):
            sid = await seed_student(test_db, email=f"bulk{i}@example.com")
            await seed_enrollment(test_db, sid, test_batch["id"])
            student_ids.append(sid)

        submission_ids = []
        for sid in student_ids:
            r = await client.post(
                "/api/students/submit-task",
                json={
                    "student_id": sid,
                    "batch_id": test_batch["id"],
                    "week": 1,
                    "linkedin_url": "https://www.linkedin.com/posts/test-post",
                },
            )
            submission_ids.append(r.json()["submission_id"])

        r = await client.post(
            "/api/admin/submissions/bulk-approve",
            json={"submission_ids": submission_ids},
            headers=admin_headers,
        )
        assert r.status_code == 200
        results = r.json()["results"]
        assert all(res["status"] == "approved" for res in results)

    async def test_bulk_reject_submissions(self, client, admin_headers, test_batch):
        student_ids = []
        from tests.conftest import seed_student
        for i in range(2):
            sid = await seed_student(test_db, email=f"bulkreject{i}@example.com")
            await seed_enrollment(test_db, sid, test_batch["id"])
            student_ids.append(sid)

        submission_ids = []
        for sid in student_ids:
            r = await client.post(
                "/api/students/submit-task",
                json={
                    "student_id": sid,
                    "batch_id": test_batch["id"],
                    "week": 2,
                    "linkedin_url": "https://www.linkedin.com/posts/test-post",
                },
            )
            submission_ids.append(r.json()["submission_id"])

        r = await client.post(
            "/api/admin/submissions/bulk-reject",
            json={"submission_ids": submission_ids, "admin_note": "Missing @SkillMe tag"},
            headers=admin_headers,
        )
        assert r.status_code == 200
        results = r.json()["results"]
        assert all(res["status"] == "rejected" for res in results)
