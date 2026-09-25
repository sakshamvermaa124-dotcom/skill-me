"""
SkillMe — Certificate Routes
Endpoints for generating, downloading, and verifying certificates.

`batch_id` in these URLs is the student's internal enrollment reference (kept for
link compatibility and because certificate IDs are derived from it). It is resolved
server-side, so a stale or missing value still finds the student's own certificate.
"""

import logging
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import Response
from middleware.auth import require_admin
from services.certificate_service import certificate_service, generate_certificate_pdf
from services.enrollment_service import enrollment_service
from services.email_service import email_service
from db.database import db

logger = logging.getLogger("skillme.certificates")
router = APIRouter(prefix="/api/certificates", tags=["certificates"])


async def _student_certificate(student_id: int, batch_id: int) -> dict | None:
    """The certificate for (student, enrollment); falls back to the student's latest one."""
    cert = await db.fetch_one(
        "SELECT * FROM certificates WHERE student_id = ? AND batch_id = ?",
        (student_id, batch_id),
    )
    if cert:
        return cert
    return await db.fetch_one(
        "SELECT * FROM certificates WHERE student_id = ? ORDER BY issued_at DESC, id DESC LIMIT 1",
        (student_id,),
    )


# ─── Public: verify a cert by ID ───
@router.get("/verify/{cert_id}", summary="Verify a certificate")
async def verify_certificate(cert_id: str):
    """Public endpoint to verify if a certificate ID is genuine."""
    row = await db.fetch_one(
        """SELECT c.*, s.first_name, s.last_name,
                  COALESCE(b.domain, s.domain) AS domain
           FROM certificates c
           JOIN students s ON c.student_id = s.id
           LEFT JOIN batches b ON c.batch_id = b.id
           WHERE c.cert_id = ?""",
        (cert_id.strip().upper(),),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Certificate not found or invalid.")
    return {
        "valid": True,
        "cert_id": row["cert_id"],
        "holder": f"{row['first_name']} {row['last_name']}",
        "domain": row["domain"],
        "issued_at": row["issued_at"],
    }


# ─── Student: download own certificate as PDF ───
@router.get("/download/{student_id}/{batch_id}", summary="Download certificate PDF")
async def download_certificate(student_id: int, batch_id: int):
    """Generate and download a certificate as PDF. Requires completed payment."""
    student = await db.fetch_one("SELECT * FROM students WHERE id = ?", (student_id,))
    if not student:
        raise HTTPException(status_code=404, detail=f"Student {student_id} not found")

    resolved = await enrollment_service.resolve_batch_id(student_id, batch_id)
    enrollment = await db.fetch_one("SELECT * FROM batches WHERE id = ?", (resolved,)) if resolved else None
    if not enrollment:
        raise HTTPException(status_code=404, detail=f"No enrollment found for student {student_id}")

    # Completion is enforced upstream, at payment order creation (see routes/payments.py
    # create_order): below 3 of 4 approved tasks, an order can only be created once an admin has unlocked
    # payment via a fulfilled urgent request. A 'paid' row here is therefore already
    # sufficient proof of eligibility — no separate completion check is needed.

    # ── Payment gate ──────────────────────────────────────────────────────────
    # Certificate download is only available after successful payment
    payment = await db.fetch_one(
        "SELECT id FROM payments WHERE student_id = ? AND batch_id = ? AND status = 'paid'",
        (student_id, enrollment["id"]),
    )
    if not payment:
        raise HTTPException(
            status_code=402,
            detail="Payment required. Please complete the ₹129 payment from your dashboard to download your certificate."
        )
    # ─────────────────────────────────────────────────────────────────────────

    # Record certificate issuance (idempotent).
    # suppress_email=False (default): if this is the student's first download
    # and the payment flow somehow didn't send the email, this will catch it.
    cert_id = None
    try:
        cert_id = (await certificate_service.issue_certificate(student["id"], enrollment["id"]))["cert_id"]
    except Exception:
        pass  # Already issued or non-critical

    try:
        pdf_bytes, cert_id = generate_certificate_pdf(dict(student), dict(enrollment), cert_id=cert_id)
    except Exception as e:
        logger.error(f"PDF generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Certificate generation failed: {e}")

    filename = f"SkillMe-Certificate-{cert_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── Admin: issue certificate for a student ───
@router.post("/issue/{student_id}/{batch_id}", summary="Issue certificate")
async def issue_cert(
    student_id: int, batch_id: int,
    background_tasks: BackgroundTasks,
    _: str = Depends(require_admin)
):
    """Issue a new certificate and send certificate-ready email to the student."""
    resolved = await enrollment_service.resolve_batch_id(student_id, batch_id)
    if not resolved:
        raise HTTPException(status_code=400, detail="Student has no enrollment — enroll them first.")
    try:
        cert_data = await certificate_service.issue_certificate(student_id, resolved, suppress_email=True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    student = await db.fetch_one(
        "SELECT first_name, last_name, email FROM students WHERE id = ?",
        (student_id,)
    )
    if student:
        background_tasks.add_task(
            email_service.send_certificate_ready,
            first_name=student["first_name"],
            last_name=student["last_name"],
            email=student["email"],
            domain=cert_data["domain"],
            cert_id=cert_data["cert_id"],
            issued_date=cert_data.get("issued_on", ""),
        )

    return {
        "status": "issued",
        "cert_id": cert_data["cert_id"],
        "batch_id": resolved,
        "issued_at": cert_data.get("issued_on", ""),  # service returns 'issued_on'
    }


# ─── Student: get own certificate metadata ───
@router.get("/metadata/{student_id}/{batch_id}", summary="Get certificate metadata")
async def get_cert_metadata(student_id: int, batch_id: int):
    """Student's own certificate metadata — used by certificate.html and lor.html to
    render the on-page view. Requires completed payment; the cert_id printed on it
    can then be checked by anyone via the separate public /verify endpoint."""
    cert = await _student_certificate(student_id, batch_id)
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")

    payment = await db.fetch_one(
        "SELECT id FROM payments WHERE student_id = ? AND batch_id = ? AND status = 'paid'",
        (student_id, cert["batch_id"]),
    )
    if not payment:
        raise HTTPException(status_code=402, detail="payment_required")

    info = await db.fetch_one(
        """SELECT s.first_name, s.last_name, COALESCE(b.domain, s.domain) AS domain
           FROM students s LEFT JOIN batches b ON b.id = ?
           WHERE s.id = ?""",
        (cert["batch_id"], student_id),
    )

    return {
        "cert_id": cert["cert_id"],
        "student_id": cert["student_id"],
        "batch_id": cert["batch_id"],
        "issued_at": cert["issued_at"],
        "first_name": info["first_name"] if info else "",
        "last_name": info["last_name"] if info else "",
        "domain": (info["domain"] if info else "") or "",
    }


# ─── Admin: list all certificates ───
@router.get("/", summary="List all certificates (admin)")
async def list_certificates(_: str = Depends(require_admin)):
    """List all issued certificates."""
    rows = await db.fetch_all(
        """SELECT c.*, s.first_name, s.last_name, s.email,
                  COALESCE(b.domain, s.domain) AS domain
           FROM certificates c
           JOIN students s ON c.student_id = s.id
           LEFT JOIN batches b ON c.batch_id = b.id
           ORDER BY c.issued_at DESC"""
    )
    return {"certificates": rows, "count": len(rows)}
