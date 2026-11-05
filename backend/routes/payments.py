"""
SkillMe — Payment Routes (Razorpay)

Flow:
  1. POST /api/payments/create-order  → creates a Razorpay order, returns order_id + key_id
  2. Frontend opens Razorpay Checkout modal with order_id
  3. Student pays → Razorpay calls onSuccess with {payment_id, order_id, signature}
  4. POST /api/payments/verify        → verifies HMAC signature, issues certificate
"""

import base64
import hashlib
import hmac
import logging

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from config import settings
from db.database import db
from services.certificate_service import certificate_service
from services.enrollment_service import enrollment_service
from services.email_service import email_service
from services import payment_service
from middleware.student_auth import require_student

logger = logging.getLogger("skillme.payments")
router = APIRouter(prefix="/api/payments", tags=["payments"])

# Payment is asked for at the end: 3 of the 4 weekly tasks must be approved
PAYMENT_UNLOCK_TASKS = 3


# ──────────────────────────────────────────────
# Request Models
# ──────────────────────────────────────────────

class CreateOrderRequest(BaseModel):
    student_id: int = Field(..., description="Student database ID")
    batch_id: int | None = Field(None, description="Internal enrollment reference (validated server-side)")
    discount_code: str | None = Field(None, description="Optional discount code")
    last_touch_source: str | None = Field(None, max_length=100)
    last_touch_campaign: str | None = Field(None, max_length=150)


class PaymentFailedRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str | None = None
    code: str | None = Field(None, max_length=100)
    reason: str | None = Field(None, max_length=300)


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    student_id: int
    batch_id: int | None = None  # ignored when the order is on record — the order's own enrollment wins


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _razorpay_auth_header() -> str:
    """Basic Auth header for Razorpay API."""
    encoded = base64.b64encode(
        f"{settings.razorpay_key_id}:{settings.razorpay_key_secret}".encode()
    ).decode()
    return f"Basic {encoded}"


def _verify_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """Verify Razorpay payment signature using HMAC-SHA256."""
    body = f"{order_id}|{payment_id}"
    expected = hmac.new(
        settings.razorpay_key_secret.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────

@router.post("/create-order", summary="Create a Razorpay payment order for certificate")
async def create_order(req: CreateOrderRequest, me: dict = Depends(require_student)):
    """
    Creates a Razorpay order for the student to pay for their certificate.
    Returns the order_id and key_id needed by the frontend Razorpay Checkout.
    """
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise HTTPException(
            status_code=503,
            detail="Payment gateway not configured. Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET to .env"
        )

    if me["id"] != req.student_id:
        raise HTTPException(status_code=403, detail="You can only pay for your own internship.")

    # Validate student exists
    student = await db.fetch_one(
        "SELECT id, first_name, last_name, email FROM students WHERE id = ?",
        (req.student_id,)
    )
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    batch_id = await enrollment_service.resolve_batch_id(req.student_id, req.batch_id)
    if not batch_id:
        raise HTTPException(status_code=400, detail="You are not enrolled in an internship yet.")

    # Gate: payment unlocks once 3 of 4 tasks are approved, or earlier only if an admin
    # has fulfilled an urgent request for this enrollment (see urgent_request_service).
    progress = await db.fetch_all(
        "SELECT week, issues_completed FROM progress WHERE student_id = ? AND batch_id = ?",
        (req.student_id, batch_id),
    )
    completed_tasks = len({int(p["week"]) for p in progress if int(p["issues_completed"]) > 0})
    if completed_tasks < PAYMENT_UNLOCK_TASKS:
        enrollment = await db.fetch_one(
            "SELECT payment_unlocked_at FROM enrollments WHERE student_id = ? AND batch_id = ?",
            (req.student_id, batch_id),
        )
        if not (enrollment and enrollment["payment_unlocked_at"]):
            raise HTTPException(
                status_code=403,
                detail="Payment unlocks once 3 of your 4 weekly tasks are approved, or once an admin approves your urgent processing request.",
            )

    # Check if already paid
    paid = await db.fetch_one(
        "SELECT id FROM payments WHERE student_id = ? AND batch_id = ? AND status = 'paid'",
        (req.student_id, batch_id)
    )
    if paid:
        # Certificate already purchased — check if cert exists
        cert = await db.fetch_one(
            "SELECT cert_id FROM certificates WHERE student_id = ? AND batch_id = ?",
            (req.student_id, batch_id)
        )
        return {
            "already_paid": True,
            "cert_id": cert["cert_id"] if cert else None,
            "message": "Certificate already purchased. Download it below.",
        }

    amount = settings.certificate_price_paise

    # Handle special discount code for 5 INR (500 paise)
    if req.discount_code and req.discount_code.strip().upper() == "BLACKYY":
        amount = 500

    # Reuse a recent unpaid order for the same enrollment and price instead of creating one
    # per click — keeps "checkout initiated" meaning one attempt, not one button press.
    open_order = await db.fetch_one(
        """SELECT razorpay_order_id FROM payments
           WHERE student_id = ? AND batch_id = ? AND status IN ('created', 'pending')
             AND amount = ? AND razorpay_order_id IS NOT NULL
             AND datetime(COALESCE(initiated_at, created_at)) >= datetime('now', '-30 minutes')
           ORDER BY id DESC LIMIT 1""",
        (req.student_id, batch_id, amount),
    )
    if open_order:
        return {
            "order_id": open_order["razorpay_order_id"],
            "amount": amount,
            "currency": "INR",
            "key_id": settings.razorpay_key_id,
            "student_name": f"{student['first_name']} {student['last_name']}",
            "student_email": student["email"],
        }

    # Create order via Razorpay API
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://api.razorpay.com/v1/orders",
            headers={
                "Authorization": _razorpay_auth_header(),
                "Content-Type": "application/json",
            },
            json={
                "amount": amount,
                "currency": "INR",
                "receipt": f"sm_{req.student_id}_{batch_id}",
                "notes": {
                    "student_id": str(req.student_id),
                    "batch_id": str(batch_id),
                    "student_name": f"{student['first_name']} {student['last_name']}",
                    "email": student["email"],
                },
            },
        )

    if resp.status_code not in (200, 201):
        logger.error("Razorpay order creation failed: %s", resp.text)
        raise HTTPException(status_code=502, detail="Payment service temporarily unavailable")

    order = resp.json()

    # Record the checkout. Razorpay test-mode keys produce real-looking pay_ ids, so flag the
    # order as a test transaction from the key itself rather than guessing from the id later.
    is_test = 1 if (settings.razorpay_key_id or "").startswith("rzp_test") else 0
    code = (req.discount_code or "").strip().upper()[:50] or None
    await db.execute(
        """INSERT INTO payments (student_id, batch_id, razorpay_order_id, amount, status, is_test,
                                 initiated_at, discount_code, last_touch_source, last_touch_campaign)
           VALUES (?, ?, ?, ?, 'created', ?, CURRENT_TIMESTAMP, ?, ?, ?)
           ON CONFLICT(razorpay_order_id) DO NOTHING""",
        (req.student_id, batch_id, order["id"], amount, is_test, code,
         (req.last_touch_source or "").strip() or None, (req.last_touch_campaign or "").strip() or None),
    )

    logger.info("Created Razorpay order %s for student %s", order["id"], req.student_id)
    return {
        "order_id": order["id"],
        "amount": amount,
        "currency": "INR",
        "key_id": settings.razorpay_key_id,
        "student_name": f"{student['first_name']} {student['last_name']}",
        "student_email": student["email"],
    }


@router.post("/verify", summary="Verify Razorpay payment and issue certificate")
async def verify_payment(req: VerifyPaymentRequest, background_tasks: BackgroundTasks):
    """
    Called after the student completes payment in the Razorpay modal.
    Verifies the signature, marks payment as successful, and issues the certificate.
    """
    # Signature check
    if not _verify_signature(req.razorpay_order_id, req.razorpay_payment_id, req.razorpay_signature):
        logger.warning("Invalid payment signature for order %s", req.razorpay_order_id)
        raise HTTPException(status_code=400, detail="Payment signature verification failed — possible fraud attempt")

    # The order row is the source of truth. An order we never created (or one belonging to a
    # different student) must not produce a payment or a certificate.
    order_row = await payment_service.get_order(req.razorpay_order_id)
    if not order_row or order_row["student_id"] != req.student_id:
        logger.warning("Verify for unknown/mismatched order %s (student %s)", req.razorpay_order_id, req.student_id)
        raise HTTPException(status_code=400, detail="This payment does not match any order on record")

    # Idempotent: a second verify (or a webhook that got there first) changes nothing.
    order_row, newly_paid = await payment_service.mark_paid(
        req.razorpay_order_id, req.razorpay_payment_id, via="verify"
    )
    student_id = order_row["student_id"]
    batch_id = order_row["batch_id"]

    logger.info(
        "Payment verified: order=%s payment=%s student=%s newly_paid=%s",
        req.razorpay_order_id, req.razorpay_payment_id, student_id, newly_paid
    )

    # Issue certificate (or return existing if already issued)
    try:
        cert_data = await certificate_service.issue_certificate(
            student_id, batch_id, suppress_email=True, via="payment", payment_id=order_row["id"]
        )
    except ValueError:
        # May already exist — fetch it
        cert = await db.fetch_one(
            "SELECT cert_id, issued_at FROM certificates WHERE student_id = ? AND batch_id = ?",
            (student_id, batch_id)
        )
        if cert:
            cert_data = {"cert_id": cert["cert_id"], "issued_at": cert["issued_at"]}
        else:
            raise HTTPException(status_code=500, detail="Certificate issuance failed")

    # Send certificate email in background
    student = await db.fetch_one(
        """SELECT s.first_name, s.last_name, s.email, COALESCE(b.domain, s.domain) AS domain
           FROM students s LEFT JOIN batches b ON b.id = ?
           WHERE s.id = ?""",
        (batch_id, student_id)
    )
    if student and newly_paid:
        background_tasks.add_task(
            email_service.send_certificate_ready,
            first_name=student["first_name"],
            last_name=student["last_name"],
            email=student["email"],
            domain=student["domain"] or "web-dev",
            cert_id=cert_data["cert_id"],
        )

    return {
        "status": "success",
        "cert_id": cert_data["cert_id"],
        "message": "Payment successful! Your certificate has been issued.",
    }


@router.post("/failed", summary="Record a failed checkout attempt (Razorpay payment.failed)")
async def payment_failed(req: PaymentFailedRequest, me: dict = Depends(require_student)):
    """Called by the dashboard when Razorpay reports a failed attempt. Never overrides a paid order."""
    order = await payment_service.get_order(req.razorpay_order_id)
    if not order or order["student_id"] != me["id"]:
        raise HTTPException(status_code=404, detail="Order not found")
    changed = await payment_service.mark_failed(req.razorpay_order_id, req.code, req.reason)
    return {"status": "recorded" if changed else "ignored"}


@router.get("/status/{student_id}/{batch_id}", summary="Check a student's certificate payment status")
async def payment_status(student_id: int, batch_id: int):
    """Check if a student has already paid for their certificate."""
    resolved = await enrollment_service.resolve_batch_id(student_id, batch_id)
    if not resolved:
        return {"status": "not_paid"}
    payment = await db.fetch_one(
        """SELECT status, razorpay_payment_id, amount, created_at
           FROM payments WHERE student_id = ? AND batch_id = ?
           ORDER BY CASE WHEN status = 'paid' THEN 0 ELSE 1 END, created_at DESC, id DESC
           LIMIT 1""",
        (student_id, resolved)
    )
    if not payment:
        return {"status": "not_paid"}
    return {
        "status": payment["status"],
        "amount_paise": payment["amount"],
        "amount_rupees": float(payment["amount"]) / 100 if payment["amount"] else 0,
    }
