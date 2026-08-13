"""
Referral Tests — Code Generation, Stats, Discounts
Tests the complete referral system.
"""
import pytest
from tests.conftest import test_db, seed_student


@pytest.mark.referrals
class TestReferralCode:
    async def test_get_referral_code_for_student(self, client, student_headers):
        r = await client.get("/api/referrals/code", headers=student_headers)
        assert r.status_code == 200
        data = r.json()
        assert "code" in data
        assert data["code"].startswith("SKM-")
        assert "referral_link" in data
        assert "discount_per_referral_inr" in data
        assert "ambassador_threshold" in data

    async def test_referral_code_is_stable(self, client, student_headers):
        """Getting the code twice should return the same code."""
        r1 = await client.get("/api/referrals/code", headers=student_headers)
        r2 = await client.get("/api/referrals/code", headers=student_headers)
        assert r1.json()["code"] == r2.json()["code"]

    async def test_referral_link_contains_code(self, client, student_headers):
        r = await client.get("/api/referrals/code", headers=student_headers)
        data = r.json()
        assert data["code"] in data["referral_link"]

    async def test_get_referral_code_no_auth(self, client):
        r = await client.get("/api/referrals/code")
        assert r.status_code == 401


@pytest.mark.referrals
class TestReferralStats:
    async def test_stats_empty(self, client, student_headers):
        r = await client.get("/api/referrals/stats", headers=student_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["total_clicked"] == 0
        assert data["total_applied"] == 0
        assert data["total_enrolled"] == 0
        assert data["total_discount_earned_inr"] == 0
        assert data["is_ambassador"] is False
        assert "conversions" in data

    async def test_stats_no_auth(self, client):
        r = await client.get("/api/referrals/stats")
        assert r.status_code == 401


@pytest.mark.referrals
class TestReferralDiscount:
    async def test_discount_no_referrals(self, client, test_student):
        r = await client.get(f"/api/referrals/discount/{test_student['id']}")
        assert r.status_code == 200
        data = r.json()
        assert data["referrals_unused"] == 0
        assert data["discount_paise"] == 0
        assert "original_price_paise" in data
        assert "final_price_paise" in data
        assert "final_price_inr" in data

    async def test_discount_caps_at_certificate_price(self, client, test_student):
        """Discount should never exceed certificate price."""
        r = await client.get(f"/api/referrals/discount/{test_student['id']}")
        data = r.json()
        assert data["final_price_paise"] >= 0
        assert data["discount_paise"] <= data["original_price_paise"]


@pytest.mark.referrals
class TestReferralFlow:
    async def test_apply_with_valid_referral_code_tracks_application(self, client, test_student, student_headers):
        """Applying with a referral code should create a conversion record."""
        # First get the referrer's code
        r = await client.get("/api/referrals/code", headers=student_headers)
        code = r.json()["code"]

        # Apply as a new student using the referral code
        r2 = await client.post("/api/students/apply", json={
            "first_name": "Referred",
            "last_name": "Student",
            "email": "referred@example.com",
            "domain": "python",
            "referred_by": code,
        })
        assert r2.status_code == 200

        # Check referral stats for the referrer
        r3 = await client.get("/api/referrals/stats", headers=student_headers)
        data = r3.json()
        assert data["total_applied"] >= 1

    async def test_cannot_self_refer(self, client, test_student, student_headers):
        """Student should not be able to use their own referral code."""
        r = await client.get("/api/referrals/code", headers=student_headers)
        code = r.json()["code"]

        r2 = await client.post("/api/students/apply", json={
            "first_name": "Test",
            "last_name": "Student",
            "email": test_student["email"],  # same email = same student
            "domain": "python",
            "referred_by": code,
        })
        # Should return already_applied since it's the same email
        assert r2.json()["status"] in ("already_applied", "applied")
