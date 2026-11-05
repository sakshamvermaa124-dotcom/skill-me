"""
Acquisition attribution is captured at application time and survives into the analytics and
the payment journey; duplicate applications are caught across track spellings.
"""
import pytest

from tests.conftest import auth_headers, seed_student, seed_batch, seed_enrollment, test_db

BASE = {"first_name": "Asha", "last_name": "Rao", "email": "asha@x.com", "domain": "python"}
ATTR = {
    "utm_source": "linkedin", "utm_medium": "social", "utm_campaign": "nov-push", "utm_content": "post-3",
    "referral_code": "skm-abc123", "landing_page": "/p/python?utm_source=linkedin",
    "referrer": "https://www.linkedin.com/", "first_touch_source": "instagram",
    "first_touch_at": "2026-11-01T10:00:00Z", "last_touch_source": "linkedin",
    "last_touch_campaign": "nov-push", "last_touch_at": "2026-11-05T10:00:00Z",
}


async def _student(email="asha@x.com"):
    return await test_db.fetch_one("SELECT * FROM students WHERE lower(email) = lower(?)", (email,))


@pytest.mark.students
class TestAttributionCapture:
    async def test_full_first_and_last_touch_is_persisted(self, client):
        r = await client.post("/api/students/apply", json={**BASE, "attribution": ATTR})
        assert r.json()["status"] == "applied"
        s = await _student()
        assert (s["utm_source"], s["utm_medium"], s["utm_campaign"], s["utm_content"]) == \
               ("linkedin", "social", "nov-push", "post-3")
        assert s["referral_code"] == "SKM-ABC123"                       # normalised
        assert s["landing_page"].startswith("/p/python") and s["referrer"] == "https://www.linkedin.com/"
        # first touch (instagram) and last touch (linkedin) are different and both kept
        assert s["first_touch_source"] == "instagram" and s["last_touch_source"] == "linkedin"
        assert s["last_touch_campaign"] == "nov-push" and s["attribution_captured"] == 1

    async def test_direct_visit_is_tracked_not_unknown(self, client):
        await client.post("/api/students/apply", json={**BASE, "attribution": {"first_touch_source": "direct"}})
        s = await _student()
        assert s["attribution_captured"] == 1 and s["first_touch_source"] == "direct" and s["utm_source"] is None

    async def test_no_attribution_stays_pre_tracking_unknown(self, client):
        await client.post("/api/students/apply", json=BASE)
        s = await _student()
        assert s["attribution_captured"] == 0 and s["first_touch_source"] is None

    async def test_oversized_attribution_is_rejected(self, client):
        r = await client.post("/api/students/apply", json={**BASE, "attribution": {"utm_source": "x" * 500}})
        assert r.status_code == 422

    async def test_attribution_reaches_analytics_by_source_and_campaign(self, client, admin_headers):
        await client.post("/api/students/apply", json={**BASE, "attribution": ATTR})
        await client.post("/api/students/apply", json={**BASE, "email": "b@x.com", "attribution": {"first_touch_source": "google"}})
        await client.post("/api/students/apply", json={**BASE, "email": "c@x.com"})
        a = (await client.get("/api/admin/analytics?fresh=true", headers=admin_headers)).json()["acquisition"]
        src = {s["key"]: s["applications"] for s in a["sources"]}
        assert src == {"instagram": 1, "google": 1, "unknown (pre-tracking)": 1}
        assert a["coverage"]["pre_tracking_unknown"] == 1
        assert [c["key"] for c in a["campaigns"]] == ["instagram / nov-push"]
        # filtering by the first-touch source narrows every section
        only = (await client.get("/api/admin/analytics?source=google", headers=admin_headers)).json()
        assert only["overview"]["applicants"] == 1


@pytest.mark.students
class TestReferralLinking:
    async def test_known_code_links_the_referrer(self, client):
        referrer = await seed_student(test_db, email="ref@x.com")
        await test_db.insert("INSERT INTO referral_codes (student_id, code) VALUES (?, 'SKM-ABC123')", (referrer,))
        await client.post("/api/students/apply", json={**BASE, "attribution": ATTR})
        conv = await test_db.fetch_one("SELECT * FROM referral_conversions")
        assert conv["referrer_student_id"] == referrer and conv["status"] == "applied"
        assert conv["referred_student_id"] == (await _student())["id"]

    async def test_unknown_code_is_kept_but_links_nothing(self, client):
        await client.post("/api/students/apply", json={**BASE, "attribution": ATTR})
        assert (await _student())["referral_code"] == "SKM-ABC123"
        assert (await test_db.fetch_one("SELECT COUNT(*) n FROM referral_conversions"))["n"] == 0


@pytest.mark.students
class TestNoDuplicateApplications:
    @pytest.mark.parametrize("second", ["Data Science", "data-science", "DATA SCIENCE"])
    async def test_track_spelling_variants_are_one_application(self, client, second):
        r1 = await client.post("/api/students/apply", json={**BASE, "domain": "data-science"})
        r2 = await client.post("/api/students/apply", json={**BASE, "email": "ASHA@x.com", "domain": second})
        assert r1.json()["status"] == "applied" and r2.json()["status"] == "already_applied"
        assert (await test_db.fetch_one("SELECT COUNT(*) n FROM students"))["n"] == 1

    async def test_a_different_track_is_still_allowed(self, client):
        await client.post("/api/students/apply", json={**BASE, "domain": "python"})
        r = await client.post("/api/students/apply", json={**BASE, "domain": "web-dev"})
        assert r.json()["status"] == "applied"


@pytest.mark.payments
class TestAttributionOnThePaymentJourney:
    async def test_last_touch_is_stored_on_the_order(self, client):
        from unittest.mock import patch
        from tests.payments.test_payments import _make_razorpay_mock
        sid = await seed_student(test_db, email="pay@x.com")
        b = await seed_batch(test_db)
        await seed_enrollment(test_db, sid, b)
        for w in (1, 2, 3):
            await test_db.insert("INSERT INTO progress (student_id, batch_id, week, issues_completed, score) VALUES (?,?,?,1,25)", (sid, b, w))
        with patch("routes.payments.httpx.AsyncClient", return_value=_make_razorpay_mock(order_id="order_attr")):
            r = await client.post("/api/payments/create-order", headers=auth_headers(sid, "pay@x.com"), json={
                "student_id": sid, "batch_id": b, "last_touch_source": "whatsapp", "last_touch_campaign": "reminder-2"})
        assert r.status_code == 200
        p = await test_db.fetch_one("SELECT last_touch_source, last_touch_campaign FROM payments WHERE razorpay_order_id = 'order_attr'")
        assert (p["last_touch_source"], p["last_touch_campaign"]) == ("whatsapp", "reminder-2")
