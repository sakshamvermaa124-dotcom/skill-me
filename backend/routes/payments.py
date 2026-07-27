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
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from config import settings
from db.database import db
from services.certificate_service import certificate_service
from services.email_service import email_service

logger = logging.getLogger("skillme.payments")
router = APIRouter(prefix="/api/payments", tags=["payments"])


# ──────────────────────────────────────────────
# Request Models
# ──────────────────────────────────────────────

class CreateOrderRequest(BaseModel):
    student_id: int = Field(..., description="Student database ID")
    batch_id: int = Field(..., description="Batch database ID")


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    student_id: int
    batch_id: int


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
async def create_order(req: CreateOrderRequest):
    """
    Creates a Razorpay order for the student to pay for their certificate.
    Returns the order_id and key_id needed by the frontend Razorpay Checkout.
    """
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise HTTPException(
            status_code=503,
            detail="Payment gateway not configured. Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET to .env"
        )

    # Validate student exists
    student = await db.fetch_one(
        "SELECT id, first_name, last_name, email FROM students WHERE id = ?",
        (req.student_id,)
    )
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # Check if already paid
    paid = await db.fetch_one(
        "SELECT id FROM payments WHERE student_id = ? AND batch_id = ? AND status = 'paid'",
        (req.student_id, req.batch_id)
    )
    if paid:
        # Certificate already purchased — check if cert exists
        cert = await db.fetch_one(
            "SELECT cert_id FROM certificates WHERE student_id = ? AND batch_id = ?",
            (req.student_id, req.batch_id)
        )
        return {
            "already_paid": True,
            "cert_id": cert["cert_id"] if cert else None,
            "message": "Certificate already purchased. Download it below.",
        }

    amount = settings.certificate_price_paise

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
                "receipt": f"sm_{req.student_id}_{req.batch_id}",
                "notes": {
                    "student_id": str(req.student_id),
                    "batch_id": str(req.batch_id),
                    "student_name": f"{student['first_name']} {student['last_name']}",
                    "email": student["email"],
                },
            },
        )

    if resp.status_code not in (200, 201):
        logger.error("Razorpay order creation failed: %s", resp.text)
        raise HTTPException(status_code=502, detail="Payment service temporarily unavailable")

    order = resp.json()

    # Record pending payment
    await db.execute(
        """INSERT INTO payments (student_id, batch_id, razorpay_order_id, amount, status)
           VALUES (?, ?, ?, ?, 'pending')
           ON CONFLICT(razorpay_order_id) DO NOTHING""",
        (req.student_id, req.batch_id, order["id"], amount),
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

    # Update payment record
    await db.execute(
        """UPDATE payments
           SET razorpay_payment_id = ?, status = 'paid', updated_at = CURRENT_TIMESTAMP
           WHERE razorpay_order_id = ?""",
        (req.razorpay_payment_id, req.razorpay_order_id),
    )

    logger.info(
        "Payment verified: order=%s payment=%s student=%s",
        req.razorpay_order_id, req.razorpay_payment_id, req.student_id
    )

    # Issue certificate (or return existing if already issued)
    try:
        cert_data = await certificate_service.issue_certificate(req.student_id, req.batch_id)
    except ValueError:
        # May already exist — fetch it
        cert = await db.fetch_one(
            "SELECT cert_id, issued_at FROM certificates WHERE student_id = ? AND batch_id = ?",
            (req.student_id, req.batch_id)
        )
        if cert:
            cert_data = {"cert_id": cert["cert_id"], "issued_at": cert["issued_at"]}
        else:
            raise HTTPException(status_code=500, detail="Certificate issuance failed")

    # Send certificate email in background
    student = await db.fetch_one(
        "SELECT first_name, last_name, email FROM students WHERE id = ?",
        (req.student_id,)
    )
    batch = await db.fetch_one(
        "SELECT domain, batch_number FROM batches WHERE id = ?",
        (req.batch_id,)
    )
    if student and batch:
        background_tasks.add_task(
            email_service.send_certificate_ready,
            first_name=student["first_name"],
            last_name=student["last_name"],
            email=student["email"],
            domain=batch["domain"],
            batch_number=batch["batch_number"],
            cert_id=cert_data["cert_id"],
        )

    return {
        "status": "success",
        "cert_id": cert_data["cert_id"],
        "message": "Payment successful! Your certificate has been issued.",
    }


@router.get("/status/{student_id}/{batch_id}", summary="Check payment status for a student+batch")
async def payment_status(student_id: int, batch_id: int):
    """Check if a student has already paid for their certificate."""
    payment = await db.fetch_one(
        """SELECT status, razorpay_payment_id, amount, created_at
           FROM payments WHERE student_id = ? AND batch_id = ?
           ORDER BY created_at DESC LIMIT 1""",
        (student_id, batch_id)
    )
    if not payment:
        return {"status": "not_paid"}
    return {
        "status": payment["status"],
        "amount_paise": payment["amount"],
        "amount_rupees": payment["amount"] / 100,
    }
