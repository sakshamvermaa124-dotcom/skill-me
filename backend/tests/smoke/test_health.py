"""
Smoke Tests — Health & Startup
Verifies the app is fundamentally alive and all routes respond.
"""
import pytest


@pytest.mark.smoke
class TestHealthEndpoint:
    async def test_health_returns_200(self, client):
        r = await client.get("/health")
        assert r.status_code == 200

    async def test_health_response_structure(self, client):
        r = await client.get("/health")
        data = r.json()
        assert "status" in data
        assert data["status"] == "healthy"
        assert "database" in data

    async def test_health_database_connected(self, client):
        r = await client.get("/health")
        assert r.json()["database"] == "connected"

    async def test_api_docs_available(self, client):
        r = await client.get("/docs")
        assert r.status_code == 200

    async def test_openapi_json_available(self, client):
        r = await client.get("/openapi.json")
        assert r.status_code == 200
        data = r.json()
        assert "paths" in data
        assert "info" in data
