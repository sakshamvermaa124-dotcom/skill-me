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
