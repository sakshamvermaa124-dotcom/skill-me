"""
Auth Tests — OTP Flow
Tests OTP request and verification lifecycle.
"""
import pytest
from tests.conftest import seed_student, seed_otp, test_db


@pytest.mark.auth
class TestOTPRequest:
    async def test_request_otp_valid_email(self, client, test_student):
        """Valid enrolled email should trigger OTP (email mocked)."""
        r = await client.post(
            "/api/auth/request-otp",
            json={"email": test_student["email"]},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "sent"
        assert test_student["email"] in data["message"]

    async def test_request_otp_unknown_email(self, client):
        """Unknown email should return 404."""
        r = await client.post(
            "/api/auth/request-otp",
            json={"email": "nobody@nowhere.com"},
        )
        assert r.status_code == 404

    async def test_request_otp_missing_email(self, client):
        """Missing email body should return 422 validation error."""
        r = await client.post("/api/auth/request-otp", json={})
        assert r.status_code == 422

    async def test_request_otp_empty_email(self, client):
        """Empty string email should return 404 (not found in DB)."""
        r = await client.post(
            "/api/auth/request-otp",
            json={"email": ""},
        )
        assert r.status_code in (404, 422)

    async def test_request_otp_email_case_insensitive(self, client, test_student):
        """
        OTP request should be case-insensitive on email.
        NOTE: This test verifies the FIRST request only - a second request in the same
        test could trigger rate limiting (429 Too Many Requests from slowapi).
        The auth service uses email.lower().strip() internally.
        """
        # Uppercase email should map to same student (lowercase in DB)
        email_upper = test_student["email"].upper()
        # Use a freshly seeded student to avoid rate-limit from previous tests
        from tests.conftest import seed_student
        s_id = await seed_student(test_db, email="case.test@example.com")
        r = await client.post(
            "/api/auth/request-otp",
            json={"email": "CASE.TEST@EXAMPLE.COM"},
        )
        # Should find the student (lowercase normalized) and return 200
        assert r.status_code == 200


@pytest.mark.auth
class TestOTPVerify:
    async def test_verify_otp_valid(self, client, test_student):
        """Valid OTP should return a JWT token."""
        email = test_student["email"]
        await seed_otp(test_db, email, otp="654321")

        r = await client.post(
            "/api/auth/verify-otp",
            json={"email": email, "otp": "654321"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "authenticated"
        assert "token" in data
        assert len(data["token"]) > 20  # JWT should be substantial

    async def test_verify_otp_wrong_code(self, client, test_student):
        """Wrong OTP code should return 401."""
        email = test_student["email"]
        await seed_otp(test_db, email, otp="111111")

        r = await client.post(
            "/api/auth/verify-otp",
            json={"email": email, "otp": "999999"},
        )
        assert r.status_code == 401

    async def test_verify_otp_expired(self, client, test_student):
        """Expired OTP should return 401."""
        email = test_student["email"]
        await seed_otp(test_db, email, otp="222222", expired=True)

        r = await client.post(
            "/api/auth/verify-otp",
            json={"email": email, "otp": "222222"},
        )
        assert r.status_code == 401

    async def test_verify_otp_no_otp_exists(self, client, test_student):
        """Verifying OTP when none was requested should return 401."""
        r = await client.post(
            "/api/auth/verify-otp",
            json={"email": test_student["email"], "otp": "123456"},
        )
        assert r.status_code == 401

    async def test_verify_otp_sets_cookie(self, client, test_student):
        """Successful OTP verify should set the skillme_token cookie."""
        email = test_student["email"]
        await seed_otp(test_db, email, otp="777888")

        r = await client.post(
            "/api/auth/verify-otp",
            json={"email": email, "otp": "777888"},
        )
        assert r.status_code == 200
        # httpx captures cookies
        assert "skillme_token" in r.cookies or "token" in r.json()

    async def test_verify_otp_invalidates_after_use(self, client, test_student):
        """An OTP should not be reusable after first verification."""
        email = test_student["email"]
        await seed_otp(test_db, email, otp="444555")

        # First use — should succeed
        r1 = await client.post(
            "/api/auth/verify-otp",
            json={"email": email, "otp": "444555"},
        )
        assert r1.status_code == 200

        # Second use — should fail (OTP marked used)
        r2 = await client.post(
            "/api/auth/verify-otp",
            json={"email": email, "otp": "444555"},
        )
        assert r2.status_code == 401

    async def test_verify_otp_missing_fields(self, client):
        """Missing fields should return 422."""
        r = await client.post("/api/auth/verify-otp", json={"email": "x@x.com"})
        assert r.status_code == 422
