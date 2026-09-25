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


@pytest.mark.portfolio
class TestPortfolioById:
    """GET /api/portfolio/id/{student_id} — the link the dashboard shares."""

    async def _approve(self, student, week, note="internal reviewer note"):
        return await test_db.insert(
            """INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status, admin_note, reviewed_at)
               VALUES (?, ?, ?, ?, 'approved', ?, '2026-08-12 14:30:00')""",
            (student["id"], student["batch_id"], week,
             f"https://www.linkedin.com/feed/update/urn:li:activity:{week}", note),
        )

    async def test_by_id_not_found(self, client):
        r = await client.get("/api/portfolio/id/999999")
        assert r.status_code == 404

    async def test_by_id_payment_required(self, client, enrolled_student):
        r = await client.get(f"/api/portfolio/id/{enrolled_student['id']}")
        assert r.status_code == 403
        assert r.json()["detail"] == "payment_required"

    async def test_by_id_matches_username_endpoint(self, client, paid_student):
        by_id = (await client.get(f"/api/portfolio/id/{paid_student['id']}")).json()
        by_gh = (await client.get(f"/api/portfolio/{paid_student['github_username']}")).json()
        assert by_id == by_gh
        assert by_id["profile"]["id"] == paid_student["id"]
        assert by_id["profile"]["name"]

    async def test_submissions_ordered_with_domain_and_no_admin_note(self, client, paid_student):
        await self._approve(paid_student, 2)
        await self._approve(paid_student, 1)
        r = await client.get(f"/api/portfolio/id/{paid_student['id']}")
        subs = r.json()["submissions"]
        assert [s["week"] for s in subs] == [1, 2]
        for s in subs:
            assert s["domain"] == "web-dev"
            assert "admin_note" not in s

    async def test_unapproved_submissions_hidden(self, client, paid_student):
        await test_db.insert(
            """INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status)
               VALUES (?, ?, 1, 'https://www.linkedin.com/feed/update/x', 'pending')""",
            (paid_student["id"], paid_student["batch_id"]),
        )
        r = await client.get(f"/api/portfolio/id/{paid_student['id']}")
        assert r.json()["submissions"] == []
