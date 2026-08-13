"""
Smoke Tests — All HTML Pages Load
Verifies each page route returns 200 with HTML content.
"""
import pytest


@pytest.mark.smoke
class TestPagesLoad:
    """Every defined page route must respond with 200."""

    @pytest.mark.parametrize("path", [
        "/",
        "/index",
        "/apply",
        "/quiz",
        "/dashboard",
        "/admin",
        "/certificate",
        "/verify",
        "/lor",
        "/offer",
        "/contact",
        "/privacy",
        "/terms",
        "/refunds",
    ])
    async def test_page_returns_200(self, client, path):
        r = await client.get(path)
        assert r.status_code == 200, f"Page {path} returned {r.status_code}"

    @pytest.mark.parametrize("path", [
        "/",
        "/index",
        "/apply",
        "/dashboard",
    ])
    async def test_page_returns_html(self, client, path):
        r = await client.get(path)
        content_type = r.headers.get("content-type", "")
        assert "text/html" in content_type, f"{path} did not return HTML"

    async def test_portfolio_page_loads(self, client):
        """Portfolio page route /p/{username} should return 200."""
        r = await client.get("/p/anyuser")
        assert r.status_code == 200

    async def test_unknown_route_returns_4xx_or_200(self, client):
        """A completely unknown route should not crash the server (returns 404 or index fallback)."""
        r = await client.get("/this-route-does-not-exist-xyz123")
        # FastAPI returns 404 for truly unknown routes
        assert r.status_code in (200, 404)

    async def test_404_does_not_return_500(self, client):
        """A missing API route should never return 500."""
        r = await client.get("/api/nonexistent-endpoint")
        assert r.status_code != 500

