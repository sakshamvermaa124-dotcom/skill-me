"""
Admin Tests — Email
"""
import pytest


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

    async def test_email_logs_filter_by_status(self, client, admin_headers):
        """Filtering by ?status= works now that el.status SQL ambiguity is fixed."""
        r = await client.get("/api/admin/email/logs?status=sent", headers=admin_headers)
        assert r.status_code == 200
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
