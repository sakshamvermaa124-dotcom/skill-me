"""
Admin Tests — Issue Assignment
Tests assigning issues to batches.
"""
import pytest
from tests.conftest import test_db


@pytest.mark.admin
class TestAssignIssues:
    async def test_assign_issues_returns_assigned(self, client, admin_headers, enrolled_student):
        batch_id = enrolled_student["batch_id"]
        r = await client.post(
            f"/api/admin/batches/{batch_id}/assign-issues",
            json={
                "week_number": 1,
                "issues": [
                    {
                        "title": "Build the homepage",
                        "body": "Create a responsive homepage",
                        "assigned_to_student_id": enrolled_student["id"],
                    }
                ],
            },
            headers=admin_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "assigned"
        assert data["week"] == 1
        assert data["issues_created"] == 1

    async def test_assign_multiple_issues(self, client, admin_headers, enrolled_student):
        batch_id = enrolled_student["batch_id"]
        r = await client.post(
            f"/api/admin/batches/{batch_id}/assign-issues",
            json={
                "week_number": 2,
                "issues": [
                    {"title": "Task A", "body": "Do A", "assigned_to_student_id": enrolled_student["id"]},
                    {"title": "Task B", "body": "Do B", "assigned_to_student_id": enrolled_student["id"]},
                    {"title": "Task C", "body": "Do C", "assigned_to_student_id": enrolled_student["id"]},
                ],
            },
            headers=admin_headers,
        )
        assert r.status_code == 200
        assert r.json()["issues_created"] == 3

    async def test_assign_issues_invalid_week(self, client, admin_headers, test_batch):
        """Week number must be 1-4."""
        r = await client.post(
            f"/api/admin/batches/{test_batch['id']}/assign-issues",
            json={"week_number": 5, "issues": []},
            headers=admin_headers,
        )
        assert r.status_code == 422

    async def test_assign_issues_week_zero_fails(self, client, admin_headers, test_batch):
        r = await client.post(
            f"/api/admin/batches/{test_batch['id']}/assign-issues",
            json={"week_number": 0, "issues": []},
            headers=admin_headers,
        )
        assert r.status_code == 422

    async def test_assign_issues_missing_week(self, client, admin_headers, test_batch):
        r = await client.post(
            f"/api/admin/batches/{test_batch['id']}/assign-issues",
            json={"issues": []},
            headers=admin_headers,
        )
        assert r.status_code == 422

    async def test_assign_issues_no_auth(self, client, enrolled_student):
        r = await client.post(
            f"/api/admin/batches/{enrolled_student['batch_id']}/assign-issues",
            json={"week_number": 1, "issues": []},
        )
        assert r.status_code == 403


@pytest.mark.admin
class TestAutoAssign:
    async def test_toggle_auto_assign_on(self, client, admin_headers, test_batch):
        r = await client.patch(
            f"/api/admin/batches/{test_batch['id']}/auto-assign?enabled=true",
            headers=admin_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["auto_assign"] is True

    async def test_toggle_auto_assign_off(self, client, admin_headers, test_batch):
        r = await client.patch(
            f"/api/admin/batches/{test_batch['id']}/auto-assign?enabled=false",
            headers=admin_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["auto_assign"] is False

    async def test_toggle_auto_assign_nonexistent_batch(self, client, admin_headers):
        r = await client.patch(
            "/api/admin/batches/99999/auto-assign?enabled=true",
            headers=admin_headers,
        )
        assert r.status_code == 404


@pytest.mark.admin
class TestScheduler:
    async def test_scheduler_status_returns_data(self, client, admin_headers):
        r = await client.get("/api/admin/scheduler/status", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert "scheduler_running" in data
        assert "next_run" in data
        assert "auto_assign_batches" in data

    async def test_trigger_scheduler(self, client, admin_headers):
        r = await client.post("/api/admin/scheduler/trigger", headers=admin_headers)
        assert r.status_code == 200
