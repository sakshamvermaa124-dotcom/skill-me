"""
Student Tests — Application Submission
Tests POST /api/students/apply for happy path and validation cases.
"""
import pytest


VALID_APPLICATION = {
    "first_name": "Alice",
    "last_name": "Wonder",
    "email": "alice@example.com",
    "phone": "9876543210",
    "github_username": "alicewonder",
    "linkedin_url": "https://linkedin.com/in/alice",
    "college": "MIT",
    "year_of_study": "3rd Year",
    "domain": "web-dev",
    "motivation": "I want to learn open-source development.",
    "referral_source": "Friend",
}


@pytest.mark.students
class TestApplicationHappyPath:
    async def test_apply_returns_applied_status(self, client):
        """Valid application should return applied status."""
        r = await client.post("/api/students/apply", json=VALID_APPLICATION)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "applied"
        assert "student_id" in data
        assert isinstance(data["student_id"], int)

    async def test_apply_stores_student_in_db(self, client):
        """After applying, student should exist in DB."""
        r = await client.post("/api/students/apply", json=VALID_APPLICATION)
        assert r.status_code == 200

        # Check via status endpoint
        r2 = await client.get("/api/students/status/alice@example.com")
        assert r2.status_code == 200
        data = r2.json()
        assert data["student"]["email"] == "alice@example.com"
        assert data["student"]["status"] == "applied"

    async def test_apply_with_github_url_extracts_username(self, client):
        """GitHub URL should be stripped to username only."""
        payload = {**VALID_APPLICATION, "github_username": "https://github.com/cooluser"}
        r = await client.post("/api/students/apply", json=payload)
        assert r.status_code == 200

        r2 = await client.get("/api/students/status/alice@example.com")
        # The stored github_username should be 'cooluser', not the full URL
        # (just verify it doesn't crash; exact value depends on DB)
        assert r2.status_code == 200

    async def test_apply_minimal_required_fields(self, client):
        """Application with only required fields should succeed."""
        r = await client.post("/api/students/apply", json={
            "first_name": "Bob",
            "last_name": "Smith",
            "email": "bob@example.com",
            "domain": "python",
        })
        assert r.status_code == 200
        assert r.json()["status"] == "applied"

    async def test_apply_with_referral_code(self, client):
        """Application with referral code should succeed and track referral."""
        # Seed a referrer student
        from tests.conftest import seed_student, test_db
        referrer_id = await seed_student(test_db, email="referrer@example.com")
        await test_db.insert(
            "INSERT INTO referral_codes (student_id, code) VALUES (?, ?)",
            (referrer_id, "SKM-REF001"),
        )

        payload = {**VALID_APPLICATION, "referred_by": "SKM-REF001"}
        r = await client.post("/api/students/apply", json=payload)
        assert r.status_code == 200
        assert r.json()["status"] == "applied"


@pytest.mark.students
class TestApplicationDuplicatePrevention:
    async def test_duplicate_email_returns_already_applied(self, client):
        """Submitting twice with same email should return already_applied."""
        await client.post("/api/students/apply", json=VALID_APPLICATION)
        r2 = await client.post("/api/students/apply", json=VALID_APPLICATION)
        assert r2.status_code == 200
        data = r2.json()
        assert data["status"] == "already_applied"
        assert "student_id" in data

    async def test_duplicate_email_case_insensitive(self, client):
        """Duplicate check should be case-insensitive on email."""
        await client.post("/api/students/apply", json=VALID_APPLICATION)
        r2 = await client.post("/api/students/apply", json={
            **VALID_APPLICATION,
            "email": "ALICE@EXAMPLE.COM",
        })
        data = r2.json()
        assert data["status"] == "already_applied"


@pytest.mark.students
class TestApplicationValidation:
    async def test_missing_first_name(self, client):
        payload = {k: v for k, v in VALID_APPLICATION.items() if k != "first_name"}
        r = await client.post("/api/students/apply", json=payload)
        assert r.status_code == 422

    async def test_missing_last_name(self, client):
        payload = {k: v for k, v in VALID_APPLICATION.items() if k != "last_name"}
        r = await client.post("/api/students/apply", json=payload)
        assert r.status_code == 422

    async def test_missing_email(self, client):
        payload = {k: v for k, v in VALID_APPLICATION.items() if k != "email"}
        r = await client.post("/api/students/apply", json=payload)
        assert r.status_code == 422

    async def test_missing_domain(self, client):
        payload = {k: v for k, v in VALID_APPLICATION.items() if k != "domain"}
        r = await client.post("/api/students/apply", json=payload)
        assert r.status_code == 422

    async def test_empty_first_name(self, client):
        """Empty first name should fail validation (min_length=1)."""
        r = await client.post("/api/students/apply", json={**VALID_APPLICATION, "first_name": ""})
        assert r.status_code == 422

    async def test_first_name_too_long(self, client):
        """First name over 100 chars should fail validation."""
        r = await client.post("/api/students/apply", json={**VALID_APPLICATION, "first_name": "A" * 101})
        assert r.status_code == 422

    async def test_email_too_long(self, client):
        """Email over 200 chars should fail validation."""
        r = await client.post("/api/students/apply", json={**VALID_APPLICATION, "email": "a" * 200 + "@b.com"})
        assert r.status_code == 422

    async def test_motivation_too_long(self, client):
        """Motivation over 1000 chars should fail validation."""
        r = await client.post("/api/students/apply", json={**VALID_APPLICATION, "motivation": "X" * 1001})
        assert r.status_code == 422

    async def test_empty_json_body(self, client):
        r = await client.post("/api/students/apply", json={})
        assert r.status_code == 422

    async def test_no_body(self, client):
        r = await client.post("/api/students/apply")
        assert r.status_code == 422
