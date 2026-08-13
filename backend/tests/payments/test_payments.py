"""
Payment Tests — Create Order, Verify, Status
Tests the full Razorpay payment flow with mocked Razorpay API.

NOTE: The payments route creates its OWN httpx.AsyncClient inside the endpoint function:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post("https://api.razorpay.com/v1/orders", ...)
We patch `httpx.AsyncClient` at the module level.
"""
import hashlib
import hmac
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


def _make_razorpay_mock(order_id="order_test123", status_code=200):
    """Return a mock for httpx.AsyncClient that simulates a Razorpay API response."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = {
        "id": order_id,
        "amount": 9900,
        "currency": "INR",
        "status": "created",
    }
    mock_resp.text = f'{{"id": "{order_id}"}}'
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)
    return mock_client


def _sign_payment(order_id: str, payment_id: str, secret: str = "test_secret") -> str:
    """Generate a valid Razorpay HMAC-SHA256 signature."""
    body = f"{order_id}|{payment_id}"
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


@pytest.mark.payments
class TestCreateOrder:
    async def test_create_order_success(self, client, enrolled_student, test_batch):
        """Create payment order for a student with Razorpay mocked."""
        mock_client = _make_razorpay_mock()
        with patch("routes.payments.httpx.AsyncClient", return_value=mock_client):
            r = await client.post("/api/payments/create-order", json={
                "student_id": enrolled_student["id"],
                "batch_id": test_batch["id"],
            })
        assert r.status_code == 200
        data = r.json()
        assert "order_id" in data
        assert "key_id" in data
        assert "amount" in data

    async def test_create_order_missing_student(self, client, test_batch):
        mock_client = _make_razorpay_mock()
        with patch("routes.payments.httpx.AsyncClient", return_value=mock_client):
            r = await client.post("/api/payments/create-order", json={
                "student_id": 99999,
                "batch_id": test_batch["id"],
            })
        assert r.status_code == 404

    async def test_create_order_already_paid_returns_flag(self, client, paid_student, test_batch):
        """If already paid, should return already_paid=True without calling Razorpay."""
        r = await client.post("/api/payments/create-order", json={
            "student_id": paid_student["id"],
            "batch_id": test_batch["id"],
        })
        assert r.status_code == 200
        data = r.json()
        assert data.get("already_paid") is True

    async def test_create_order_discount_code(self, client, enrolled_student, test_batch):
        """BLACKYY discount code should set amount to 500 paise."""
        mock_client = _make_razorpay_mock(order_id="order_discount")
        mock_client.post.return_value.json.return_value = {"id": "order_discount", "amount": 500}
        with patch("routes.payments.httpx.AsyncClient", return_value=mock_client):
            r = await client.post("/api/payments/create-order", json={
                "student_id": enrolled_student["id"],
                "batch_id": test_batch["id"],
                "discount_code": "BLACKYY",
            })
        assert r.status_code == 200
        data = r.json()
        assert data.get("amount") == 500

    async def test_create_order_razorpay_failure_returns_502(self, client, enrolled_student, test_batch):
        """Razorpay 500 should propagate as 502 Bad Gateway."""
        mock_client = _make_razorpay_mock(status_code=500)
        mock_client.post.return_value.text = "Internal Server Error"
        with patch("routes.payments.httpx.AsyncClient", return_value=mock_client):
            r = await client.post("/api/payments/create-order", json={
                "student_id": enrolled_student["id"],
                "batch_id": test_batch["id"],
            })
        assert r.status_code == 502

    async def test_create_order_missing_fields(self, client):
        r = await client.post("/api/payments/create-order", json={})
        assert r.status_code == 422



@pytest.mark.payments
class TestVerifyPayment:
    async def test_verify_valid_payment(self, client, enrolled_student, test_batch):
        """Valid signature should succeed and issue certificate."""
        # First create a pending payment record
        from tests.conftest import test_db
        await test_db.insert(
            "INSERT INTO payments (student_id, batch_id, razorpay_order_id, amount, status) VALUES (?,?,?,?,'pending')",
            (enrolled_student["id"], test_batch["id"], "order_abc123", 9900),
        )

        sig = _sign_payment("order_abc123", "pay_xyz789")
        r = await client.post("/api/payments/verify", json={
            "razorpay_order_id": "order_abc123",
            "razorpay_payment_id": "pay_xyz789",
            "razorpay_signature": sig,
            "student_id": enrolled_student["id"],
            "batch_id": test_batch["id"],
        })
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "success"
        assert "cert_id" in data

    async def test_verify_invalid_signature(self, client, enrolled_student, test_batch):
        """Invalid HMAC signature should return 400."""
        r = await client.post("/api/payments/verify", json={
            "razorpay_order_id": "order_abc",
            "razorpay_payment_id": "pay_xyz",
            "razorpay_signature": "invalid_signature_here",
            "student_id": enrolled_student["id"],
            "batch_id": test_batch["id"],
        })
        assert r.status_code == 400

    async def test_verify_missing_fields(self, client):
        r = await client.post("/api/payments/verify", json={})
        assert r.status_code == 422


@pytest.mark.payments
class TestPaymentStatus:
    async def test_status_not_paid(self, client, enrolled_student, test_batch):
        r = await client.get(
            f"/api/payments/status/{enrolled_student['id']}/{test_batch['id']}"
        )
        assert r.status_code == 200
        assert r.json()["status"] == "not_paid"

    async def test_status_paid(self, client, paid_student, test_batch):
        r = await client.get(
            f"/api/payments/status/{paid_student['id']}/{test_batch['id']}"
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "paid"
        assert "amount_paise" in data
        assert "amount_rupees" in data

    async def test_status_amount_rupees_conversion(self, client, paid_student, test_batch):
        """9900 paise should equal 99 rupees."""
        r = await client.get(
            f"/api/payments/status/{paid_student['id']}/{test_batch['id']}"
        )
        data = r.json()
        assert data["amount_paise"] == 9900
        assert data["amount_rupees"] == 99.0
