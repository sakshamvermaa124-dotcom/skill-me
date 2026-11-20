"""
Admin Tests — LinkedIn Submission Review Queue
Tests the submit → list → approve/reject → bulk-approve/bulk-reject flow.
"""
import pytest
from tests.conftest import test_db, seed_batch, seed_enrollment, auth_headers


@pytest.mark.admin
class TestSubmitTask:
    async def test_submit_task_pending(self, client, enrolled_student):
        r = await client.post(
            "/api/students/submit-task",
            headers=auth_headers(enrolled_student["id"]),
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

    async def test_submit_task_stores_and_emails_task_feedback(self, client, enrolled_student):
        """Submitting generates feedback from that week's deliverables, stores it, and emails it."""
        import routes.students as students_route
        from services.project_curriculum import get_project_track_for_student
        r = await client.post(
            "/api/students/submit-task",
            headers=auth_headers(enrolled_student["id"]),
            json={
                "student_id": enrolled_student["id"],
                "batch_id": enrolled_student["batch_id"],
                "week": 2,
                "linkedin_url": "https://www.linkedin.com/posts/test-post",
            },
        )
        assert r.status_code == 200
        data = r.json()
        week2 = get_project_track_for_student("web-dev", enrolled_student["id"])["weeks"]["2"]
        assert data["feedback"]["task_title"] == week2["title"]
        assert data["feedback"]["checklist"] == week2["deliverables"]
        assert len(data["feedback"]["general_tips"]) == 3

        row = await test_db.fetch_one("SELECT feedback FROM submissions WHERE id = ?", (data["submission_id"],))
        assert week2["deliverables"][0] in row["feedback"]

        send = students_route.email_service.send_submission_feedback
        assert send.call_count == 1
        assert send.call_args.kwargs["week"] == 2
        assert send.call_args.kwargs["email"] == enrolled_student["email"]

        progress = (await client.get(f"/api/students/progress/{enrolled_student['email']}", headers=auth_headers(enrolled_student["id"]))).json()
        assert progress["submissions"][0]["feedback"] == row["feedback"]

    async def test_submit_task_rejects_non_linkedin_url(self, client, enrolled_student):
        r = await client.post(
            "/api/students/submit-task",
            headers=auth_headers(enrolled_student["id"]),
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
            headers=auth_headers(test_student["id"]),
            json={
                "student_id": test_student["id"],
                "batch_id": test_batch["id"],
                "week": 1,
                "linkedin_url": "https://www.linkedin.com/posts/test-post",
            },
        )
        assert r.status_code == 400

    async def test_submit_task_needs_own_session(self, client, enrolled_student):
        from tests.conftest import seed_student
        payload = {
            "student_id": enrolled_student["id"],
            "batch_id": enrolled_student["batch_id"],
            "week": 1,
            "linkedin_url": "https://www.linkedin.com/posts/test-post",
        }
        assert (await client.post("/api/students/submit-task", json=payload)).status_code == 401
        other = await seed_student(test_db, email="intruder@example.com")
        r = await client.post("/api/students/submit-task", json=payload, headers=auth_headers(other))
        assert r.status_code == 403

    async def test_duplicate_pending_submission_rejected(self, client, enrolled_student):
        payload = {
            "student_id": enrolled_student["id"],
            "batch_id": enrolled_student["batch_id"],
            "week": 1,
            "linkedin_url": "https://www.linkedin.com/posts/test-post",
        }
        await client.post("/api/students/submit-task", json=payload, headers=auth_headers(enrolled_student["id"]))
        r2 = await client.post("/api/students/submit-task", json=payload, headers=auth_headers(enrolled_student["id"]))
        assert r2.status_code == 400


@pytest.mark.admin
class TestUpdatePendingLink:
    def _payload(self, student, url, week=1):
        return {"student_id": student["id"], "batch_id": student["batch_id"], "week": week, "linkedin_url": url}

    async def test_update_link_while_pending(self, client, enrolled_student):
        import routes.students as students_route
        h = auth_headers(enrolled_student["id"])
        first = await client.post("/api/students/submit-task", json=self._payload(enrolled_student, "https://www.linkedin.com/posts/wrong"), headers=h)
        sid = first.json()["submission_id"]
        before = await test_db.fetch_one("SELECT submitted_at, attempts FROM submissions WHERE id = ?", (sid,))
        emails_before = students_route.email_service.send_submission_feedback.call_count

        r = await client.put("/api/students/submit-task", json=self._payload(enrolled_student, "https://www.linkedin.com/posts/right"), headers=h)
        assert r.status_code == 200
        assert r.json() == {"submission_id": sid, "status": "pending", "linkedin_url": "https://www.linkedin.com/posts/right"}

        row = await test_db.fetch_one("SELECT linkedin_url, status, submitted_at, attempts FROM submissions WHERE id = ?", (sid,))
        assert row["linkedin_url"] == "https://www.linkedin.com/posts/right"
        assert row["status"] == "pending"
        # Keeps its queue position, isn't counted as a new attempt, and doesn't re-email feedback
        assert row["submitted_at"] == before["submitted_at"]
        assert row["attempts"] == before["attempts"]
        assert students_route.email_service.send_submission_feedback.call_count == emails_before

    async def test_update_link_blocked_after_review(self, client, admin_headers, enrolled_student):
        h = auth_headers(enrolled_student["id"])
        sub = await client.post("/api/students/submit-task", json=self._payload(enrolled_student, "https://www.linkedin.com/posts/a"), headers=h)
        sid = sub.json()["submission_id"]
        await client.post(f"/api/admin/submissions/{sid}/approve", json={}, headers=admin_headers)

        r = await client.put("/api/students/submit-task", json=self._payload(enrolled_student, "https://www.linkedin.com/posts/b"), headers=h)
        assert r.status_code == 400
        row = await test_db.fetch_one("SELECT linkedin_url FROM submissions WHERE id = ?", (sid,))
        assert row["linkedin_url"] == "https://www.linkedin.com/posts/a"

    async def test_update_link_blocked_after_rejection(self, client, admin_headers, enrolled_student):
        h = auth_headers(enrolled_student["id"])
        sub = await client.post("/api/students/submit-task", json=self._payload(enrolled_student, "https://www.linkedin.com/posts/a"), headers=h)
        await client.post(f"/api/admin/submissions/{sub.json()['submission_id']}/reject", json={"admin_note": "x"}, headers=admin_headers)
        r = await client.put("/api/students/submit-task", json=self._payload(enrolled_student, "https://www.linkedin.com/posts/b"), headers=h)
        assert r.status_code == 400

    async def test_update_link_validation(self, client, enrolled_student):
        h = auth_headers(enrolled_student["id"])
        # Nothing submitted yet
        r = await client.put("/api/students/submit-task", json=self._payload(enrolled_student, "https://www.linkedin.com/posts/a"), headers=h)
        assert r.status_code == 400
        await client.post("/api/students/submit-task", json=self._payload(enrolled_student, "https://www.linkedin.com/posts/a"), headers=h)
        # Not a LinkedIn link
        r = await client.put("/api/students/submit-task", json=self._payload(enrolled_student, "https://github.com/x"), headers=h)
        assert r.status_code == 400
        # Same link
        r = await client.put("/api/students/submit-task", json=self._payload(enrolled_student, "https://www.linkedin.com/posts/a"), headers=h)
        assert r.status_code == 400

    async def test_update_link_needs_own_session(self, client, enrolled_student):
        from tests.conftest import seed_student
        await client.post("/api/students/submit-task", json=self._payload(enrolled_student, "https://www.linkedin.com/posts/a"), headers=auth_headers(enrolled_student["id"]))
        payload = self._payload(enrolled_student, "https://www.linkedin.com/posts/b")
        assert (await client.put("/api/students/submit-task", json=payload)).status_code == 401
        other = await seed_student(test_db, email="intruder2@example.com")
        assert (await client.put("/api/students/submit-task", json=payload, headers=auth_headers(other))).status_code == 403


@pytest.mark.admin
class TestSubmissionReviewQueue:
    async def test_list_pending_submissions(self, client, admin_headers, enrolled_student):
        await client.post(
            "/api/students/submit-task",
            headers=auth_headers(enrolled_student["id"]),
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
            headers=auth_headers(enrolled_student["id"]),
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
        sub = await client.post("/api/students/submit-task", json=payload, headers=auth_headers(enrolled_student["id"]))
        submission_id = sub.json()["submission_id"]

        r = await client.post(
            f"/api/admin/submissions/{submission_id}/reject",
            json={"admin_note": "Please tag @SkillMe"},
            headers=admin_headers,
        )
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"

        import routes.admin as admin_route
        send = admin_route.email_service.send_task_rejected
        assert send.call_count == 1
        assert send.call_args.kwargs["week"] == 1
        assert send.call_args.kwargs["email"] == enrolled_student["email"]
        assert send.call_args.kwargs["admin_note"] == "Please tag @SkillMe"

        # Rejecting again doesn't send a duplicate email
        await client.post(f"/api/admin/submissions/{submission_id}/reject", json={"admin_note": "x"}, headers=admin_headers)
        assert send.call_count == 1

        # Resubmission should now succeed
        r2 = await client.post("/api/students/submit-task", json=payload, headers=auth_headers(enrolled_student["id"]))
        assert r2.status_code == 200
        assert r2.json()["status"] == "pending"

    async def test_reject_without_note_uses_default_and_new_link_resubmits(self, client, admin_headers, enrolled_student):
        import routes.admin as admin_route
        from services.submission_service import DEFAULT_REJECT_NOTE
        h = auth_headers(enrolled_student["id"])
        payload = {"student_id": enrolled_student["id"], "batch_id": enrolled_student["batch_id"],
                   "week": 3, "linkedin_url": "https://www.linkedin.com/posts/broken"}
        sid = (await client.post("/api/students/submit-task", json=payload, headers=h)).json()["submission_id"]

        r = await client.post(f"/api/admin/submissions/{sid}/reject", json={"admin_note": "  "}, headers=admin_headers)
        assert r.json()["admin_note"] == DEFAULT_REJECT_NOTE
        row = await test_db.fetch_one("SELECT admin_note FROM submissions WHERE id = ?", (sid,))
        assert row["admin_note"] == DEFAULT_REJECT_NOTE
        assert admin_route.email_service.send_task_rejected.call_args.kwargs["admin_note"] == DEFAULT_REJECT_NOTE

        # Rejected student submits a fixed link → back to pending with the new URL
        payload["linkedin_url"] = "https://www.linkedin.com/posts/fixed"
        r2 = await client.post("/api/students/submit-task", json=payload, headers=h)
        assert r2.status_code == 200 and r2.json()["status"] == "pending"
        row = await test_db.fetch_one("SELECT linkedin_url, status FROM submissions WHERE id = ?", (sid,))
        assert (row["linkedin_url"], row["status"]) == ("https://www.linkedin.com/posts/fixed", "pending")

    async def test_approved_blocks_resubmit_and_shows_on_dashboard(self, client, admin_headers, enrolled_student):
        payload = {
            "student_id": enrolled_student["id"],
            "batch_id": enrolled_student["batch_id"],
            "week": 1,
            "linkedin_url": "https://www.linkedin.com/posts/test-post",
        }
        submission_id = (await client.post("/api/students/submit-task", json=payload, headers=auth_headers(enrolled_student["id"]))).json()["submission_id"]
        await client.post(f"/api/admin/submissions/{submission_id}/approve", json={}, headers=admin_headers)

        r = await client.post("/api/students/submit-task", json=payload, headers=auth_headers(enrolled_student["id"]))
        assert r.status_code == 400

        dash = (await client.get(f"/api/students/progress/id/{enrolled_student['id']}", headers=auth_headers(enrolled_student["id"]))).json()
        assert dash["summary"]["completed_tasks"] == 1
        assert [(s["week"], s["status"]) for s in dash["submissions"]] == [(1, "approved")]

    async def test_reject_after_approve_rolls_back_progress(self, client, admin_headers, enrolled_student):
        sub = await client.post(
            "/api/students/submit-task",
            headers=auth_headers(enrolled_student["id"]),
            json={
                "student_id": enrolled_student["id"],
                "batch_id": enrolled_student["batch_id"],
                "week": 1,
                "linkedin_url": "https://www.linkedin.com/posts/test-post",
            },
        )
        submission_id = sub.json()["submission_id"]
        await client.post(f"/api/admin/submissions/{submission_id}/approve", json={}, headers=admin_headers)
        await client.post(f"/api/admin/submissions/{submission_id}/reject", json={}, headers=admin_headers)

        progress = await test_db.fetch_one(
            "SELECT issues_completed, score FROM progress WHERE student_id = ? AND batch_id = ? AND week = 1",
            (enrolled_student["id"], enrolled_student["batch_id"]),
        )
        assert progress["issues_completed"] == 0
        assert progress["score"] == 0

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
                headers=auth_headers(sid),
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
                headers=auth_headers(sid),
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

        import routes.admin as admin_route
        send = admin_route.email_service.send_task_rejected
        assert send.call_count == 2
        assert {c.kwargs["email"] for c in send.call_args_list} == {"bulkreject0@example.com", "bulkreject1@example.com"}
        assert all(c.kwargs["admin_note"] == "Missing @SkillMe tag" for c in send.call_args_list)
