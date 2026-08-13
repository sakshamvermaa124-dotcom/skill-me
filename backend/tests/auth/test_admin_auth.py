"""
Auth Tests — Admin API Key
Tests X-Admin-Key header enforcement on all admin endpoints.
"""
import pytest


@pytest.mark.auth
class TestAdminAuthEnforced:
    """Every admin endpoint must reject requests without a valid API key."""

    async def test_admin_stats_no_key_returns_403(self, client):
        r = await client.get("/api/admin/stats")
        assert r.status_code == 403

    async def test_admin_stats_wrong_key_returns_403(self, client):
        r = await client.get(
            "/api/admin/stats",
            headers={"X-Admin-Key": "wrong-key"},
        )
        assert r.status_code == 403

    async def test_admin_stats_valid_key_returns_200(self, client, admin_headers):
        r = await client.get("/api/admin/stats", headers=admin_headers)
        assert r.status_code == 200

    async def test_admin_list_batches_no_key(self, client):
        r = await client.get("/api/admin/batches")
        assert r.status_code == 403

    async def test_admin_list_students_no_key(self, client):
        r = await client.get("/api/admin/students")
        assert r.status_code == 403

    async def test_admin_create_batch_no_key(self, client):
        r = await client.post(
            "/api/admin/batches",
            json={"domain": "web-dev", "batch_number": 1},
        )
        assert r.status_code == 403

    async def test_admin_github_status_no_key(self, client):
        r = await client.get("/api/admin/github/status")
        assert r.status_code == 403

    async def test_admin_email_logs_no_key(self, client):
        r = await client.get("/api/admin/email/logs")
        assert r.status_code == 403

    async def test_admin_scheduler_status_no_key(self, client):
        r = await client.get("/api/admin/scheduler/status")
        assert r.status_code == 403

    async def test_certificate_list_no_key(self, client):
        """Certificate list endpoint requires admin auth."""
        r = await client.get("/api/certificates/")
        assert r.status_code == 403

    async def test_certificate_issue_no_key(self, client):
        r = await client.post("/api/certificates/issue/1/1")
        assert r.status_code == 403

    async def test_empty_api_key_returns_403(self, client):
        r = await client.get(
            "/api/admin/stats",
            headers={"X-Admin-Key": ""},
        )
        assert r.status_code == 403
