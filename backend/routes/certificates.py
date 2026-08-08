"""
SkillMe — Certificate Routes
Endpoints for generating, downloading, and verifying certificates.
"""

import logging
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import Response, HTMLResponse
from middleware.auth import require_admin
from services.certificate_service import certificate_service, generate_certificate_pdf
from services.email_service import email_service
from db.database import db

logger = logging.getLogger("skillme.certificates")
router = APIRouter(prefix="/api/certificates", tags=["certificates"])


# ─── Public: verify a cert by ID ───
@router.get("/verify/{cert_id}", summary="Verify a certificate")
async def verify_certificate(cert_id: str):
    """Public endpoint to verify if a certificate ID is genuine."""
    row = await db.fetch_one(
        """SELECT c.*, s.first_name, s.last_name, b.domain, b.batch_number
           FROM certificates c
           JOIN students s ON c.student_id = s.id
           JOIN batches b ON c.batch_id = b.id
           WHERE c.cert_id = ?""",
        (cert_id.upper(),),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Certificate not found or invalid.")
    return {
        "valid": True,
        "cert_id": row["cert_id"],
        "holder": f"{row['first_name']} {row['last_name']}",
        "domain": row["domain"],
        "batch_number": row["batch_number"],
        "issued_at": row["issued_at"],
    }


# ─── Student: download own certificate as PDF ───
@router.get("/download/{student_id}/{batch_id}", summary="Download certificate PDF")
async def download_certificate(student_id: int, batch_id: int):
    """Generate and download a certificate as PDF. Requires completed payment."""
    student = await db.fetch_one("SELECT * FROM students WHERE id = ?", (student_id,))
    if not student:
        raise HTTPException(status_code=404, detail=f"Student {student_id} not found")

    batch = await db.fetch_one("SELECT * FROM batches WHERE id = ?", (batch_id,))
    if not batch:
        # Try to find the batch via enrollment
        enrollment = await db.fetch_one(
            "SELECT b.* FROM enrollments e JOIN batches b ON e.batch_id = b.id WHERE e.student_id = ? LIMIT 1",
            (student_id,)
        )
        if not enrollment:
            raise HTTPException(status_code=404, detail=f"No batch found for student {student_id}")
        batch = enrollment

    # ── Payment gate ──────────────────────────────────────────────────────────
    # Certificate download is only available after successful payment
    payment = await db.fetch_one(
        "SELECT id FROM payments WHERE student_id = ? AND batch_id = ? AND status = 'paid'",
        (student_id, batch["id"]),
    )
    if not payment:
        raise HTTPException(
            status_code=402,
            detail="Payment required. Please complete the ₹99 payment from your dashboard to download your certificate."
        )
    # ─────────────────────────────────────────────────────────────────────────

    # Record certificate issuance (idempotent)
    try:
        await certificate_service.issue_certificate(student["id"], batch["id"])
    except Exception:
        pass  # Already issued or non-critical

    try:
        pdf_bytes, cert_id = generate_certificate_pdf(dict(student), dict(batch))
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
    try:
        cert_data = await certificate_service.issue_certificate(student_id, batch_id)

        # Fetch student + batch for email
        student = await db.fetch_one(
            "SELECT first_name, last_name, email FROM students WHERE id = ?",
            (student_id,)
        )
        batch = await db.fetch_one(
            "SELECT domain, batch_number FROM batches WHERE id = ?",
            (batch_id,)
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
                issued_date=cert_data.get("issued_at", ""),
            )

        return {
            "status": "issued",
            "cert_id": cert_data["cert_id"],
            "issued_at": cert_data["issued_at"],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Student: get own certificate metadata ───
@router.get("/metadata/{student_id}/{batch_id}", summary="Get certificate metadata")
async def get_cert_metadata(student_id: int, batch_id: int):
    """Public endpoint for a student to get their own certificate metadata."""
    cert = await db.fetch_one(
        "SELECT * FROM certificates WHERE student_id = ? AND batch_id = ?",
        (student_id, batch_id)
    )
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
    
    # Get student info
    student = await db.fetch_one("SELECT first_name, last_name FROM students WHERE id = ?", (student_id,))
    # Get batch info
    batch = await db.fetch_one("SELECT domain, batch_number FROM batches WHERE id = ?", (batch_id,))

    return {
        "cert_id": cert["cert_id"],
        "student_id": cert["student_id"],
        "batch_id": cert["batch_id"],
        "issued_at": cert["issued_at"],
        "first_name": student["first_name"] if student else "",
        "last_name": student["last_name"] if student else "",
        "domain": batch["domain"] if batch else "",
        "batch_number": batch["batch_number"] if batch else 1,
    }


# ─── Admin: list all certificates ───
@router.get("/", summary="List all certificates (admin)")
async def list_certificates(_: str = Depends(require_admin)):
    """List all issued certificates."""
    rows = await db.fetch_all(
        """SELECT c.*, s.first_name, s.last_name, s.email,
                  b.domain, b.batch_number
           FROM certificates c
           JOIN students s ON c.student_id = s.id
           JOIN batches b ON c.batch_id = b.id
           ORDER BY c.issued_at DESC"""
    )
    return {"certificates": rows, "count": len(rows)}
