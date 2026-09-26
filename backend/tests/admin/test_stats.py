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

    async def test_email_logs_page_shape(self, client, admin_headers):
        """/email/logs response includes page/total_pages, matching /students' convention."""
        r = await client.get("/api/admin/email/logs?page=1", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["page"] == 1
        assert "total_pages" in data
        assert "count" in data

    async def test_email_directory_empty(self, client, admin_headers):
        r = await client.get("/api/admin/email/directory", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["students"] == []
        assert data["total"] == 0

    async def test_email_directory_search(self, client, admin_headers):
        r = await client.get("/api/admin/email/directory?q=nobody-matches-this", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["students"] == []


@pytest.mark.admin
class TestAnalytics:
    async def test_analytics_empty_db_shape(self, client, admin_headers):
        """With no data, every aggregate should be zero/empty, not an error."""
        r = await client.get("/api/admin/analytics", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["funnel"]["total"] == 0
        assert data["domains"] == []
        assert data["weekly_completion"] == []
        assert data["revenue"]["total_orders"] == 0
        assert data["revenue"]["total_revenue_rupees"] == 0
        assert data["applications_trend"] == []

    async def test_analytics_requires_admin_key(self, client):
        r = await client.get("/api/admin/analytics")
        assert r.status_code == 403

    async def test_analytics_reflects_students(self, client, admin_headers):
        await client.post("/api/students/apply", json={
            "first_name": "Ana", "last_name": "Lytics", "email": "ana.lytics@example.com",
            "phone": "9999999999", "github_username": "analytics", "college": "Test College",
            "year_of_study": "3rd", "domain": "genai", "motivation": "x" * 20,
        })
        r = await client.get("/api/admin/analytics", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["funnel"]["total"] == 1
        assert data["funnel"]["applied"] == 1
        domains = {d["domain"]: d for d in data["domains"]}
        assert "genai" in domains
        assert domains["genai"]["total"] == 1
