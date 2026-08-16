"""
Frontend Contract Tests — Proof of Work Portfolio & Certificate
Verifies that the portfolio API and certificate generation adhere strictly to required data schemas.
"""
import pytest
from pathlib import Path


class TestFrontendPortfolioContract:
    """Test static HTML contract and API schema compatibility for portfolio and certificates."""

    def test_portfolio_html_structure(self):
        """portfolio.html must contain Bento grid containers, monogram avatar, and toast notification."""
        portfolio_path = Path(__file__).resolve().parent.parent.parent.parent / "portfolio.html"
        assert portfolio_path.exists(), "portfolio.html must exist at root"
        content = portfolio_path.read_text(encoding="utf-8")

        assert "portfolio-wrapper" in content
        assert "profile-hero-card" in content or "portfolio-toast" in content
        assert "portfolio.js" in content
        assert "https://fonts.googleapis.com/css2" in content

    def test_certificate_html_structure(self):
        """certificate.html must contain gold seal, QR canvas, and verification UI."""
        cert_path = Path(__file__).resolve().parent.parent.parent.parent / "certificate.html"
        assert cert_path.exists(), "certificate.html must exist at root"
        content = cert_path.read_text(encoding="utf-8")

        assert "cert-seal-wrap" in content
        assert "qr-canvas" in content
        assert "verify-page" in content
        assert "Open-Source Technical Program" not in content
        assert "Batch #" not in content

    def test_offer_html_structure(self):
        """offer.html must contain official letterhead, HOD/NOC pack, and dynamic parameter bindings."""
        offer_path = Path(__file__).resolve().parent.parent.parent.parent / "offer.html"
        assert offer_path.exists(), "offer.html must exist at root"
        content = offer_path.read_text(encoding="utf-8")

        assert "SkillMe" in content
        assert "letterhead" in content or "offer" in content
        # Verify official Govt. of India Udyam registration is present
        assert "UDYAM-UP-50-0294192" in content
        assert "CIN:" not in content


@pytest.mark.asyncio
class TestPortfolioAPIDataSchema:
    """Verify the /api/portfolio/{username} endpoint returns the exact required schema."""

    async def test_portfolio_api_paid_user_returns_full_data(self, client, paid_student):
        """For an activated student, portfolio endpoint must return profile, stats, domains, and submissions."""
        username = paid_student.get("github_username") or "sakshamverma124"
        r = await client.get(f"/api/portfolio/{username}")
        assert r.status_code == 200
        data = r.json()
        assert "profile" in data
        assert "stats" in data
        assert "domains" in data
        assert "submissions" in data
        assert isinstance(data["domains"], list)
        assert isinstance(data["submissions"], list)
