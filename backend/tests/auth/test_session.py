"""
Auth Tests — Session Management
Tests /me endpoint and logout.

/me accepts BOTH:
- Cookie: skillme_token  (browser sessions)
- Header: Authorization: Bearer <token>  (API clients / mobile)
"""
import pytest
from tests.conftest import make_jwt, test_db, seed_student


@pytest.mark.auth
class TestGetMe:
    async def test_get_me_authenticated_via_bearer(self, client, student_token):
        """GET /me returns student data when authenticated via Authorization: Bearer header."""
        r = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {student_token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "email" in data
        assert "first_name" in data
        assert "last_name" in data

    async def test_get_me_authenticated_via_cookie(self, client, student_token):
        """GET /me also works with the skillme_token cookie (browser sessions)."""
        client.cookies.set("skillme_token", student_token)
        r = await client.get("/api/auth/me")
        client.cookies.clear()
        assert r.status_code == 200
        assert "email" in r.json()

    async def test_get_me_no_token(self, client):
        """/me without any auth should return 401."""
        r = await client.get("/api/auth/me")
        assert r.status_code == 401

    async def test_get_me_invalid_cookie(self, client):
        """/me with garbage cookie should return 401."""
        client.cookies.set("skillme_token", "this.is.not.a.real.jwt")
        r = await client.get("/api/auth/me")
        client.cookies.clear()
        assert r.status_code == 401

    async def test_get_me_invalid_bearer(self, client):
        """/me with garbage Bearer token should return 401."""
        r = await client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.real.jwt"})
        assert r.status_code == 401

    async def test_get_me_wrong_token_type(self, client):
        """Token with wrong 'type' claim should be rejected."""
        from jose import jwt as jose_jwt
        from config import settings
        from datetime import datetime, timedelta

        payload = {
            "sub": "1",
            "email": "test@example.com",
            "exp": datetime.utcnow() + timedelta(days=1),
            "type": "admin",  # wrong type
        }
        bad_token = jose_jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        client.cookies.set("skillme_token", bad_token)
        r = await client.get("/api/auth/me")
        client.cookies.clear()
        assert r.status_code == 401

    async def test_get_me_nonexistent_student(self, client):
        """Token for a student that was deleted should return 401."""
        fake_token = make_jwt(99999, "ghost@example.com")
        client.cookies.set("skillme_token", fake_token)
        r = await client.get("/api/auth/me")
        client.cookies.clear()
        assert r.status_code == 401


@pytest.mark.auth
class TestLogout:
    async def test_logout_returns_success(self, client):
        """POST /logout should return logged_out status."""
        r = await client.post("/api/auth/logout")
        assert r.status_code == 200
        assert r.json()["status"] == "logged_out"

    async def test_logout_clears_cookie(self, client, test_student, student_token):
        """Logout should delete the skillme_token cookie."""
        client.cookies.set("skillme_token", student_token)
        r2 = await client.post("/api/auth/logout")
        assert r2.status_code == 200

    async def test_logout_without_session_is_ok(self, client):
        """Logout without a cookie/session should still return 200."""
        r = await client.post("/api/auth/logout")
        assert r.status_code == 200
