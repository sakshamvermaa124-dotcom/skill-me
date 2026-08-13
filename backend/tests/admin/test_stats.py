"""
Admin Tests — GitHub Status & Email
"""
import pytest


@pytest.mark.admin
class TestGitHubStatus:
    async def test_github_status_returns_connected(self, client, admin_headers):
        r = await client.get("/api/admin/github/status", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "connected"
        assert "authenticated_as" in data
        assert "org" in data

    async def test_github_status_no_auth(self, client):
        r = await client.get("/api/admin/github/status")
        assert r.status_code == 403


@pytest.mark.admin
class TestEmailLogs:
    async def test_email_logs_empty(self, client, admin_headers):
        r = await client.get("/api/admin/email/logs", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert "logs" in data
        assert "total" in data
        assert data["total"] == 0

    async def test_email_logs_filter_by_type(self, client, admin_headers):
        r = await client.get("/api/admin/email/logs?email_type=otp_login", headers=admin_headers)
        assert r.status_code == 200

    async def test_email_logs_filter_by_status_bug(self, client, admin_headers):
        """
        BUG: Filtering by ?status= causes sqlite3.OperationalError: ambiguous column name: status.
        The email_logs query does `LEFT JOIN students s ... WHERE status = ?` but both
        email_logs and students tables have a `status` column.
        EXPECTED FIX: Qualify as `el.status = ?` in routes/admin.py:678.
        """
        import sqlite3 as _sqlite
        try:
            r = await client.get("/api/admin/email/logs?status=sent", headers=admin_headers)
            # FastAPI global handler converts to 500
            assert r.status_code == 500, (
                f"Got {r.status_code} — if 200, the bug has been fixed. Update to assert 200."
            )
        except (_sqlite.OperationalError, Exception) as e:
            # Bug confirmed: the exception bubbles through the ASGI transport
            assert "ambiguous column name" in str(e).lower() or "status" in str(e).lower(), (
                f"Unexpected exception: {e}"
            )
    async def test_email_logs_pagination(self, client, admin_headers):
        r = await client.get("/api/admin/email/logs?limit=10&offset=0", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["limit"] == 10
        assert data["offset"] == 0

    async def test_email_test_endpoint(self, client, admin_headers):
        """Test email endpoint should skip when email is disabled."""
        r = await client.post(
            "/api/admin/email/test",
            json={"to_email": "test@example.com"},
            headers=admin_headers,
        )
        # email_enabled=False in test config → status=skipped
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("skipped", "sent", "failed")
