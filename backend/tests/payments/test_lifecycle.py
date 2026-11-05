"""
Payment lifecycle: created → pending → paid | failed (abandoned is derived).
Covers idempotent verify, ownership checks, failure recording, and the Razorpay webhook
(signature, replay protection, ordering against the browser callback).
"""
import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import auth_headers, seed_student, seed_batch, seed_enrollment, test_db
from tests.payments.test_payments import _make_razorpay_mock, _sign_payment

WEBHOOK_SECRET = "whsec_test"


@pytest.fixture
async def eligible(client):
    """An enrolled student with 3 approved weeks (past the payment gate)."""
    sid = await seed_student(test_db, email="pay@x.com")
    b = await seed_batch(test_db)
    await seed_enrollment(test_db, sid, b)
    for w in (1, 2, 3):
        await test_db.insert(
            "INSERT INTO progress (student_id, batch_id, week, issues_completed, score) VALUES (?,?,?,1,25)", (sid, b, w))
        await test_db.insert(
            "INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status) VALUES (?,?,?,'u','approved')", (sid, b, w))
    return {"id": sid, "batch_id": b, "email": "pay@x.com"}


async def _order(client, s, order_id="order_L1", **extra):
    mock = _make_razorpay_mock(order_id=order_id)
    with patch("routes.payments.httpx.AsyncClient", return_value=mock):
        r = await client.post("/api/payments/create-order", headers=auth_headers(s["id"], s["email"]),
                              json={"student_id": s["id"], "batch_id": s["batch_id"], **extra})
    return r, mock


async def _verify(client, s, order_id="order_L1", payment_id="pay_L1"):
    return await client.post("/api/payments/verify", json={
        "razorpay_order_id": order_id, "razorpay_payment_id": payment_id,
        "razorpay_signature": _sign_payment(order_id, payment_id),
        "student_id": s["id"], "batch_id": s["batch_id"]})


async def _row(order_id="order_L1"):
    return await test_db.fetch_one("SELECT * FROM payments WHERE razorpay_order_id = ?", (order_id,))


@pytest.mark.payments
class TestCreateOrderRecords:
    async def test_order_is_created_with_lifecycle_fields(self, client, eligible):
        r, _ = await _order(client, eligible, discount_code="blackyy",
                            last_touch_source="linkedin", last_touch_campaign="nov-push")
        assert r.status_code == 200
        p = await _row()
        assert p["status"] == "created" and p["initiated_at"] is not None
        assert p["completed_at"] is None and p["failure_reason"] is None
        assert p["discount_code"] == "BLACKYY" and p["amount"] == 500
        assert (p["last_touch_source"], p["last_touch_campaign"]) == ("linkedin", "nov-push")
        assert p["is_test"] == 1        # conftest configures rzp_test_* keys => orders are test transactions

    async def test_live_keys_create_real_orders(self, client, eligible):
        from config import settings
        with patch.object(settings, "razorpay_key_id", "rzp_live_abc"):
            await _order(client, eligible)
        assert (await _row())["is_test"] == 0

    async def test_recent_unpaid_order_is_reused_not_duplicated(self, client, eligible):
        r1, m1 = await _order(client, eligible)
        r2, m2 = await _order(client, eligible, order_id="order_SHOULD_NOT_BE_USED")
        assert r1.json()["order_id"] == r2.json()["order_id"] == "order_L1"
        m2.post.assert_not_called()
        n = await test_db.fetch_one("SELECT COUNT(*) n FROM payments WHERE student_id = ?", (eligible["id"],))
        assert n["n"] == 1

    async def test_old_open_order_is_not_reused(self, client, eligible):
        await _order(client, eligible)
        await test_db.execute("UPDATE payments SET initiated_at = datetime('now', '-2 hours')")
        r, _ = await _order(client, eligible, order_id="order_L2")
        assert r.json()["order_id"] == "order_L2"

    async def test_cannot_create_order_for_someone_else(self, client, eligible):
        other = await seed_student(test_db, email="other@x.com", domain="python")
        r = await client.post("/api/payments/create-order", headers=auth_headers(other, "other@x.com"),
                              json={"student_id": eligible["id"], "batch_id": eligible["batch_id"]})
        assert r.status_code == 403

    async def test_requires_login(self, client, eligible):
        r = await client.post("/api/payments/create-order", json={"student_id": eligible["id"]})
        assert r.status_code == 401


@pytest.mark.payments
class TestVerifyIsIdempotent:
    async def test_double_verify_pays_once_and_emails_once(self, client, eligible):
        await _order(client, eligible)
        with patch("routes.payments.email_service.send_certificate_ready", new=AsyncMock()) as mail:
            r1 = await _verify(client, eligible)
            first = await _row()
            r2 = await _verify(client, eligible)
            second = await _row()
        assert r1.status_code == r2.status_code == 200
        assert r1.json()["cert_id"] == r2.json()["cert_id"]
        assert mail.await_count == 1
        assert first["status"] == "paid" and first["confirmed_via"] == "verify" and first["completed_at"]
        assert (second["completed_at"], second["updated_at"], second["razorpay_payment_id"]) == \
               (first["completed_at"], first["updated_at"], first["razorpay_payment_id"])
        certs = await test_db.fetch_all("SELECT * FROM certificates WHERE student_id = ?", (eligible["id"],))
        assert len(certs) == 1 and certs[0]["issued_via"] == "payment" and certs[0]["payment_id"] == first["id"]

    async def test_unknown_order_cannot_mint_a_certificate(self, client, eligible):
        r = await _verify(client, eligible, order_id="order_never_created", payment_id="pay_X")
        assert r.status_code == 400
        assert (await test_db.fetch_one("SELECT COUNT(*) n FROM certificates"))["n"] == 0
        assert (await test_db.fetch_one("SELECT COUNT(*) n FROM payments"))["n"] == 0

    async def test_order_of_another_student_is_rejected(self, client, eligible):
        await _order(client, eligible)
        other = await seed_student(test_db, email="o@x.com", domain="python")
        r = await client.post("/api/payments/verify", json={
            "razorpay_order_id": "order_L1", "razorpay_payment_id": "pay_L1",
            "razorpay_signature": _sign_payment("order_L1", "pay_L1"), "student_id": other})
        assert r.status_code == 400
        assert (await _row())["status"] == "created"

    async def test_bad_signature_changes_nothing(self, client, eligible):
        await _order(client, eligible)
        r = await client.post("/api/payments/verify", json={
            "razorpay_order_id": "order_L1", "razorpay_payment_id": "pay_L1", "razorpay_signature": "bad",
            "student_id": eligible["id"], "batch_id": eligible["batch_id"]})
        assert r.status_code == 400 and (await _row())["status"] == "created"


@pytest.mark.payments
class TestFailedAttempts:
    async def test_failure_is_recorded_with_reason_then_retry_succeeds(self, client, eligible):
        await _order(client, eligible)
        h = auth_headers(eligible["id"], eligible["email"])
        r = await client.post("/api/payments/failed", headers=h, json={
            "razorpay_order_id": "order_L1", "code": "BAD_REQUEST_ERROR", "reason": "Card declined"})
        assert r.json()["status"] == "recorded"
        p = await _row()
        assert (p["status"], p["failure_code"], p["failure_reason"]) == ("failed", "BAD_REQUEST_ERROR", "Card declined")
        assert (await _verify(client, eligible)).status_code == 200    # student retries on the same order
        p = await _row()
        assert p["status"] == "paid" and p["failure_reason"] is None

    async def test_failed_never_overrides_paid(self, client, eligible):
        await _order(client, eligible)
        await _verify(client, eligible)
        r = await client.post("/api/payments/failed", headers=auth_headers(eligible["id"], eligible["email"]),
                              json={"razorpay_order_id": "order_L1", "reason": "late failure event"})
        assert r.json()["status"] == "ignored" and (await _row())["status"] == "paid"

    async def test_cannot_mark_someone_elses_order_failed(self, client, eligible):
        await _order(client, eligible)
        other = await seed_student(test_db, email="o2@x.com", domain="python")
        r = await client.post("/api/payments/failed", headers=auth_headers(other, "o2@x.com"),
                              json={"razorpay_order_id": "order_L1"})
        assert r.status_code == 404 and (await _row())["status"] == "created"


def _hook(event, order_id="order_L1", payment_id="pay_W1", event_id="evt_1", **entity):
    body = json.dumps({"event": event, "payload": {"payment": {"entity": {
        "id": payment_id, "order_id": order_id, **entity}}}}).encode()
    sig = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return {"content": body, "headers": {"X-Razorpay-Signature": sig, "X-Razorpay-Event-Id": event_id,
                                         "Content-Type": "application/json"}}


@pytest.fixture
def webhook_secret():
    from config import settings
    with patch.object(settings, "razorpay_webhook_secret", WEBHOOK_SECRET):
        yield


@pytest.mark.payments
@pytest.mark.webhooks
@pytest.mark.usefixtures("webhook_secret")
class TestRazorpayWebhook:
    async def test_rejects_bad_signature_and_missing_secret(self, client, eligible):
        await _order(client, eligible)
        bad = _hook("payment.captured")
        bad["headers"]["X-Razorpay-Signature"] = "nope"
        assert (await client.post("/api/webhooks/razorpay", **bad)).status_code == 400
        from config import settings
        with patch.object(settings, "razorpay_webhook_secret", ""):
            assert (await client.post("/api/webhooks/razorpay", **_hook("payment.captured"))).status_code == 400
        assert (await _row())["status"] == "created"

    async def test_captured_pays_issues_certificate_and_emails_once(self, client, eligible):
        await _order(client, eligible)
        with patch("routes.webhooks.email_service.send_certificate_ready", new=AsyncMock()) as mail:
            r = await client.post("/api/webhooks/razorpay", **_hook("payment.captured"))
            assert r.json()["status"] == "ok"
            replay = await client.post("/api/webhooks/razorpay", **_hook("payment.captured"))
            assert replay.json()["status"] == "duplicate"
            # same capture re-delivered under a NEW event id, and the browser callback arriving late
            again = await client.post("/api/webhooks/razorpay", **_hook("payment.captured", event_id="evt_2"))
            assert again.json()["status"] == "ok"
        p = await _row()
        assert p["status"] == "paid" and p["confirmed_via"] == "webhook" and p["razorpay_payment_id"] == "pay_W1"
        assert mail.await_count == 1
        cert = await test_db.fetch_one("SELECT * FROM certificates WHERE student_id = ?", (eligible["id"],))
        assert cert["issued_via"] == "payment"
        with patch("routes.payments.email_service.send_certificate_ready", new=AsyncMock()) as late_mail:
            assert (await _verify(client, eligible, payment_id="pay_W1")).status_code == 200
        assert late_mail.await_count == 0 and (await _row())["confirmed_via"] == "webhook"
        assert (await test_db.fetch_one("SELECT COUNT(*) n FROM payment_events"))["n"] == 2

    async def test_authorized_then_failed_then_captured(self, client, eligible):
        await _order(client, eligible)
        await client.post("/api/webhooks/razorpay", **_hook("payment.authorized", event_id="e1"))
        assert (await _row())["status"] == "pending"
        await client.post("/api/webhooks/razorpay", **_hook(
            "payment.failed", event_id="e2", error_code="GATEWAY_ERROR", error_description="Bank timeout"))
        p = await _row()
        assert (p["status"], p["failure_code"], p["failure_reason"]) == ("failed", "GATEWAY_ERROR", "Bank timeout")
        await client.post("/api/webhooks/razorpay", **_hook("payment.captured", event_id="e3"))
        assert (await _row())["status"] == "paid"

    async def test_late_failed_or_authorized_event_never_downgrades_paid(self, client, eligible):
        await _order(client, eligible)
        await client.post("/api/webhooks/razorpay", **_hook("payment.captured", event_id="e1"))
        await client.post("/api/webhooks/razorpay", **_hook("payment.failed", event_id="e2"))
        await client.post("/api/webhooks/razorpay", **_hook("payment.authorized", event_id="e3"))
        assert (await _row())["status"] == "paid"

    async def test_event_for_unknown_order_is_recorded_and_ignored(self, client, eligible):
        r = await client.post("/api/webhooks/razorpay", **_hook("payment.captured", order_id="order_ghost"))
        assert r.status_code == 200
        assert (await test_db.fetch_one("SELECT COUNT(*) n FROM certificates"))["n"] == 0
