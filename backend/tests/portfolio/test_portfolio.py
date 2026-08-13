"""
Portfolio Tests — GET /api/portfolio/{github_username}
"""
import pytest
from tests.conftest import test_db


@pytest.mark.portfolio
class TestPortfolio:
    async def test_portfolio_not_found(self, client):
        """Unknown GitHub username should return 404."""
        r = await client.get("/api/portfolio/nonexistentuser12345")
        assert r.status_code == 404

    async def test_portfolio_payment_required(self, client, enrolled_student):
        """Student without payment should return 403 with payment_required."""
        r = await client.get(f"/api/portfolio/{enrolled_student['github_username']}")
        assert r.status_code == 403
        assert "payment_required" in r.json().get("detail", "")

    async def test_portfolio_paid_student_returns_data(self, client, paid_student):
        """Paid student should get portfolio data."""
        r = await client.get(f"/api/portfolio/{paid_student['github_username']}")
        assert r.status_code == 200
        data = r.json()
        assert "profile" in data
        assert "stats" in data
        assert "domains" in data
        assert "submissions" in data

    async def test_portfolio_profile_has_name(self, client, paid_student):
        r = await client.get(f"/api/portfolio/{paid_student['github_username']}")
        profile = r.json()["profile"]
        assert "name" in profile
        assert "github_username" in profile

    async def test_portfolio_case_insensitive_username(self, client, paid_student):
        """GitHub username lookup should be case-insensitive."""
        upper = paid_student["github_username"].upper()
        r = await client.get(f"/api/portfolio/{upper}")
        assert r.status_code == 200

    async def test_portfolio_domains_list(self, client, paid_student):
        """Domains should be a list."""
        r = await client.get(f"/api/portfolio/{paid_student['github_username']}")
        assert isinstance(r.json()["domains"], list)

    async def test_portfolio_submissions_list(self, client, paid_student):
        """Submissions should be a list (possibly empty)."""
        r = await client.get(f"/api/portfolio/{paid_student['github_username']}")
        assert isinstance(r.json()["submissions"], list)
