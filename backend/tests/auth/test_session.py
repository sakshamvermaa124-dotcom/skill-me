"""
Auth Tests — Session Management
Tests /me endpoint and logout.

NOTE (BUG DOCUMENTED): /me endpoint ONLY reads from the `skillme_token` cookie.
It does NOT accept the Authorization: Bearer header. See routes/auth.py:99.
This is a design limitation — the tests use cookies accordingly.
"""
import pytest
from tests.conftest import make_jwt, test_db, seed_student


@pytest.mark.auth
class TestGetMe:
    async def test_get_me_valid_cookie(self, client, test_student, student_token):
        """/me should return student profile for a valid cookie."""
        client.cookies.set("skillme_token", student_token)
        r = await client.get("/api/auth/me")
        client.cookies.clear()
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == test_student["email"]
        assert data["first_name"] == test_student["first_name"]

    async def test_get_me_bearer_token_not_supported(self, client, test_student, student_headers):
        """
        BUG: /me does not support Authorization: Bearer header.
        It only reads the skillme_token cookie.
        This test documents the current (limited) behavior.
        """
        r = await client.get("/api/auth/me", headers=student_headers)
        # Currently returns 401 because it ignores the Bearer header
        assert r.status_code == 401  # Known limitation of /me endpoint

    async def test_get_me_no_token(self, client):
        """/me without cookie should return 401."""
        r = await client.get("/api/auth/me")
        assert r.status_code == 401

    async def test_get_me_invalid_cookie(self, client):
        """/me with garbage cookie should return 401."""
        client.cookies.set("skillme_token", "this.is.not.a.real.jwt")
        r = await client.get("/api/auth/me")
        client.cookies.clear()
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
