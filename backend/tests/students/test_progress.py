"""
Student Tests — Status Checks
Tests GET /api/students/status/{email}.
"""
import pytest
from tests.conftest import test_db, seed_student, seed_batch, seed_enrollment


@pytest.mark.students
class TestStudentStatus:
    async def test_check_status_existing_student(self, client, test_student):
        r = await client.get(f"/api/students/status/{test_student['email']}")
        assert r.status_code == 200
        data = r.json()
        assert "student" in data
        assert data["student"]["email"] == test_student["email"]
        assert data["student"]["status"] == "applied"

    async def test_check_status_unknown_email(self, client):
        r = await client.get("/api/students/status/nobody@nowhere.com")
        assert r.status_code == 404

    async def test_check_status_includes_enrollments(self, client, enrolled_student):
        r = await client.get(f"/api/students/status/{enrolled_student['email']}")
        assert r.status_code == 200
        data = r.json()
        assert "enrollments" in data
        assert len(data["enrollments"]) == 1

    async def test_check_status_no_enrollments(self, client, test_student):
        """Student with no enrollments should return empty list."""
        r = await client.get(f"/api/students/status/{test_student['email']}")
        assert r.status_code == 200
        data = r.json()
        assert data["enrollments"] == []

    async def test_check_status_case_insensitive_email(self, client, test_student):
        """Email lookup should be case-insensitive."""
        r = await client.get(f"/api/students/status/{test_student['email'].upper()}")
        assert r.status_code == 200

    async def test_check_status_url_encoded_email(self, client, test_student):
        """Emails with + should be URL-encoded."""
        # Standard emails work; test+ emails need encoding
        r = await client.get("/api/students/status/test%40example.com")
        assert r.status_code == 200


@pytest.mark.students
class TestStudentProgress:
    async def test_progress_enrolled_student(self, client, enrolled_student):
        r = await client.get(f"/api/students/progress/{enrolled_student['email']}")
        assert r.status_code == 200
        data = r.json()
        assert "student" in data
        assert "progress" in data
        assert "submissions" in data
        assert "summary" in data

    async def test_progress_student_not_found(self, client):
        r = await client.get("/api/students/progress/ghost@nowhere.com")
        assert r.status_code == 404

    async def test_progress_summary_has_required_fields(self, client, enrolled_student):
        r = await client.get(f"/api/students/progress/{enrolled_student['email']}")
        summary = r.json()["summary"]
        assert "total_tasks" in summary
        assert "completed_tasks" in summary
        assert "completion_pct" in summary

    async def test_progress_completion_pct_is_bounded(self, client, enrolled_student):
        """Completion percentage should be between 0 and 100."""
        r = await client.get(f"/api/students/progress/{enrolled_student['email']}")
        pct = r.json()["summary"]["completion_pct"]
        assert 0 <= pct <= 100

    async def test_progress_by_id(self, client, enrolled_student):
        r = await client.get(f"/api/students/progress/id/{enrolled_student['id']}")
        assert r.status_code == 200

    async def test_progress_by_invalid_id(self, client):
        r = await client.get("/api/students/progress/id/999999")
        assert r.status_code == 404

    async def test_completing_all_4_weeks_reaches_100_percent(self, client, admin_headers, enrolled_student):
        """
        Regression test: a student can only ever get ONE approved submission per week
        (submissions.UNIQUE(student_id, batch_id, week)), so completion_pct must be
        calculated as (distinct weeks credited / 4), NOT as a sum of issues_completed
        divided by a legacy per-domain issue count (8/12) — that old divisor assumed
        multiple GitHub issues per week and made 100% unreachable under the new
        one-submission-per-week model.
        """
        for week in [1, 2, 3, 4]:
            sub = await client.post(
                "/api/students/submit-task",
                json={
                    "student_id": enrolled_student["id"],
                    "batch_id": enrolled_student["batch_id"],
                    "week": week,
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

        r = await client.get(f"/api/students/progress/{enrolled_student['email']}")
        summary = r.json()["summary"]
        assert summary["completed_tasks"] == 4
        assert summary["completion_pct"] == 100


@pytest.mark.students
class TestProgressSingleEnrollment:
    async def test_progress_ignores_stale_dropped_enrollment(self, client, test_student):
        """Only the current enrollment's rows reach the dashboard."""
        old = await seed_batch(test_db, domain="python", batch_number=50)
        new = await seed_batch(test_db, domain="web-dev", batch_number=51)
        await seed_enrollment(test_db, test_student["id"], old)
        await test_db.execute("UPDATE enrollments SET status = 'dropped' WHERE batch_id = ?", (old,))
        await test_db.insert(
            "INSERT INTO progress (student_id, batch_id, week, issues_completed, score) VALUES (?, ?, 3, 1, 100)",
            (test_student["id"], old),
        )
        await seed_enrollment(test_db, test_student["id"], new)

        data = (await client.get(f"/api/students/progress/{test_student['email']}")).json()
        assert {p["batch_id"] for p in data["progress"]} == {new}
        assert data["summary"]["completed_tasks"] == 0
        assert not any("batch_number" in p for p in data["progress"])

    async def test_dropped_student_without_progress_has_no_enrollment(self, client, enrolled_student):
        await test_db.execute("UPDATE enrollments SET status = 'dropped' WHERE student_id = ?", (enrolled_student["id"],))
        data = (await client.get(f"/api/students/progress/{enrolled_student['email']}")).json()
        assert data["progress"] == []

    async def test_tasks_with_wrong_batch_id_use_own_enrollment(self, client, enrolled_student):
        r = await client.get(f"/api/tasks/current/{enrolled_student['id']}/987654")
        assert r.status_code == 200
        assert r.json()["enrollment"]["batch_id"] == enrolled_student["batch_id"]

    async def test_tasks_for_unenrolled_student_404(self, client, test_student):
        r = await client.get(f"/api/tasks/current/{test_student['id']}/1")
        assert r.status_code == 404


class TestPublicActivity:
    async def test_stats_are_real_counts_not_padded(self, client, test_student):
        r = await client.get("/api/students/public-activity")
        assert r.status_code == 200
        data = r.json()
        assert data["stats"]["total_students"] == 1
        assert data["stats"]["total_submissions_approved"] == 0
        assert data["activities"] == []
