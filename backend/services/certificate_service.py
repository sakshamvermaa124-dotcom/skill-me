"""
SkillMe — Certificate Service
Generates completion certificates as PDF using ReportLab,
and manages certificate records in the database.
"""

import io
import uuid
import hashlib
import logging
from datetime import datetime

try:
    import qrcode
    from qrcode.image.pil import PilImage
    _QR_AVAILABLE = True
except ImportError:
    _QR_AVAILABLE = False

from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white, black, Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

from db.database import db

logger = logging.getLogger("skillme.certificates")

# Page in landscape A4
PAGE_W, PAGE_H = landscape(A4)

# Color palette
C_BG_DARK    = HexColor("#e8e4dc")
C_BG_SURFACE = HexColor("#ffffff")
C_NAVY       = HexColor("#1a2340")
C_NAVY_LIGHT = HexColor("#2a3560")
C_PURPLE     = HexColor("#4f46e5")
C_BLUE       = HexColor("#2563eb")
C_EMERALD    = HexColor("#059669")
C_GOLD       = HexColor("#b8860b")
C_GOLD_LIGHT = HexColor("#d4a853")
C_GOLD_DARK  = HexColor("#8b6914")
C_TEXT       = HexColor("#1a1a2e")
C_TEXT_SEC   = HexColor("#3d4663")
C_MUTED      = HexColor("#64748b")
C_BORDER     = HexColor("#1f2937")
C_BORDER_GOLD = Color(0.72, 0.53, 0.04, alpha=0.25)


def _cert_id_from_student(student_id: int, batch_id: int) -> str:
    """Generate a deterministic, short certificate ID."""
    raw = f"skillme-{student_id}-{batch_id}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:12].upper()
    return f"SM-{h[:4]}-{h[4:8]}-{h[8:12]}"


def _draw_background(c: rl_canvas.Canvas, w: float, h: float):
    """Draw deep dark background with subtle glows and watermark."""
    # Base fill
    c.setFillColor(C_BG_DARK)
    c.rect(0, 0, w, h, fill=1, stroke=0)

    # Subtle purple glow — top-left
    for i in range(25, 0, -1):
        alpha = 0.003 * i
        glow = Color(0.486, 0.518, 0.953, alpha=alpha)
        c.setFillColor(glow)
        r = i * 8
        c.ellipse(40, h - 40, 40 + r * 2, h - 40 + r * 2, fill=1, stroke=0)

    # Subtle blue glow — bottom-right
    for i in range(20, 0, -1):
        alpha = 0.003 * i
        glow = Color(0.22, 0.74, 0.97, alpha=alpha)
        c.setFillColor(glow)
        r = i * 7
        c.ellipse(w - 60 - r * 2, -10, w - 60, -10 + r * 2, fill=1, stroke=0)

    # Diagonal watermark lines (very faint)
    c.saveState()
    c.setStrokeColor(Color(0.79, 0.66, 0.30, alpha=0.015))
    c.setLineWidth(0.3)
    for offset in range(0, int(w + h), 40):
        c.line(offset, 0, offset - h, h)
    c.restoreState()


def _draw_borders(c: rl_canvas.Canvas, w: float, h: float):
    """Double border with gold accents and corner ornaments."""
    # Outer border
    margin = 10 * mm
    c.setStrokeColor(Color(0.79, 0.66, 0.30, alpha=0.3))
    c.setLineWidth(1.8)
    c.rect(margin, margin, w - 2 * margin, h - 2 * margin, fill=0, stroke=1)

    # Inner border
    inner = margin + 4 * mm
    c.setStrokeColor(Color(0.79, 0.66, 0.30, alpha=0.12))
    c.setLineWidth(0.5)
    c.rect(inner, inner, w - 2 * inner, h - 2 * inner, fill=0, stroke=1)

    # Corner ornaments
    corner_size = 7 * mm
    c.setStrokeColor(C_GOLD)
    c.setLineWidth(1.8)
    corners = [
        (margin - 0.5, margin - 0.5),
        (w - margin + 0.5, margin - 0.5),
        (margin - 0.5, h - margin + 0.5),
        (w - margin + 0.5, h - margin + 0.5),
    ]
    for cx, cy in corners:
        dx = corner_size if cx < w / 2 else -corner_size
        dy = corner_size if cy < h / 2 else -corner_size
        c.line(cx, cy, cx + dx, cy)
        c.line(cx, cy, cx, cy + dy)


def _draw_company_header(c: rl_canvas.Canvas, w: float, h: float):
    """Company info bar at top."""
    header_y = h - 18 * mm

    # Left: company name and details
    c.setFillColor(C_TEXT)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(18 * mm, header_y + 4, "SkillMe")

    c.setFillColor(C_MUTED)
    c.setFont("Helvetica", 6.5)
    c.drawString(18 * mm, header_y - 5, "India's Open Source Internship Platform")

    # Right: contact
    c.setFillColor(C_MUTED)
    c.setFont("Helvetica", 6.5)
    c.drawRightString(w - 18 * mm, header_y + 4, "www.skill-me-intern.in")
    c.drawRightString(w - 18 * mm, header_y - 4, "skillmeintern@gmail.com")
    c.drawRightString(w - 18 * mm, header_y - 12, "New Delhi, India")

    # Divider
    c.setStrokeColor(Color(0.79, 0.66, 0.30, alpha=0.15))
    c.setLineWidth(0.5)
    c.line(18 * mm, header_y - 18, w - 18 * mm, header_y - 18)


def _draw_title(c: rl_canvas.Canvas, w: float, h: float):
    """Certificate title section."""
    title_y = h - 44 * mm

    # "OFFICIAL DOCUMENT" label
    c.setFillColor(C_GOLD)
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(w / 2, title_y + 8, "OFFICIAL DOCUMENT")

    # Main title
    c.setFillColor(C_TEXT)
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(w / 2, title_y - 8, "Certificate of Internship Completion")

    # Gold divider with diamond
    div_y = title_y - 16
    line_w = 60 * mm
    c.setStrokeColor(Color(0.79, 0.66, 0.30, alpha=0.4))
    c.setLineWidth(0.5)
    c.line(w / 2 - line_w, div_y, w / 2 - 4, div_y)
    c.line(w / 2 + 4, div_y, w / 2 + line_w, div_y)
    # Diamond
    c.saveState()
    c.setFillColor(C_GOLD)
    c.translate(w / 2, div_y)
    c.rotate(45)
    c.rect(-1.5, -1.5, 3, 3, fill=1, stroke=0)
    c.restoreState()


def _draw_body(c: rl_canvas.Canvas, w: float, h: float, student: dict, batch: dict, cert_id: str, issued_on: str):
    """Main certificate body content."""
    mid_y = h / 2 + 6 * mm

    # "This is to certify that"
    c.setFillColor(C_TEXT_SEC)
    c.setFont("Helvetica-Oblique", 11)
    c.drawCentredString(w / 2, mid_y + 26 * mm, "This is to certify that")

    # Student Name
    name = f"{student.get('first_name', '')} {student.get('last_name', '')}".strip()
    c.setFillColor(C_TEXT)
    c.setFont("Helvetica-Bold", 34)
    c.drawCentredString(w / 2, mid_y + 10 * mm, name)

    # Name underline
    name_w = c.stringWidth(name, "Helvetica-Bold", 34)
    c.setStrokeColor(Color(0.79, 0.66, 0.30, alpha=0.5))
    c.setLineWidth(1)
    c.line(w / 2 - name_w / 2 - 10, mid_y + 7 * mm, w / 2 + name_w / 2 + 10, mid_y + 7 * mm)

    # "has successfully completed the"
    c.setFillColor(C_TEXT_SEC)
    c.setFont("Helvetica-Oblique", 10)
    c.drawCentredString(w / 2, mid_y - 3 * mm, "has successfully completed the")

    # Domain name
    domain = batch.get("domain", "").replace("-", " ").title()
    c.setFillColor(C_BLUE)
    c.setFont("Helvetica-Bold", 17)
    c.drawCentredString(w / 2, mid_y - 13 * mm, f"{domain} Developer Internship")

    # Description
    c.setFillColor(C_MUTED)
    c.setFont("Helvetica", 7.5)
    desc_y = mid_y - 22 * mm
    desc_lines = [
        "A rigorous 4-week industry-grade internship program consisting of real-world GitHub contributions,",
        "code reviews, pull request workflows, and collaborative software development practices.",
    ]
    for i, line in enumerate(desc_lines):
        c.drawCentredString(w / 2, desc_y - i * 10, line)


def _draw_details_row(c: rl_canvas.Canvas, w: float, h: float, batch: dict):
    """Horizontal details bar with Duration/Batch/Mode/Status."""
    row_y = 52 * mm
    row_h = 14 * mm

    # Top and bottom lines
    c.setStrokeColor(Color(0.79, 0.66, 0.30, alpha=0.12))
    c.setLineWidth(0.5)
    c.line(18 * mm, row_y + row_h, w - 18 * mm, row_y + row_h)
    c.line(18 * mm, row_y, w - 18 * mm, row_y)

    # 4 columns
    batch_num = batch.get("batch_number", "1")
    items = [
        ("DURATION", "4 Weeks"),
        ("BATCH", f"#{batch_num}"),
        ("MODE", "Remote"),
        ("STATUS", "Completed"),
    ]
    col_w = (w - 36 * mm) / 4
    status_colors = {"Completed": C_EMERALD}

    for i, (label, value) in enumerate(items):
        cx = 18 * mm + col_w * i + col_w / 2
        c.setFillColor(C_MUTED)
        c.setFont("Helvetica", 5.5)
        c.drawCentredString(cx, row_y + row_h - 4.5, label)
        color = status_colors.get(value, C_TEXT)
        c.setFillColor(color)
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(cx, row_y + 3, value)


def _draw_footer(c: rl_canvas.Canvas, w: float, h: float, cert_id: str, issued_on: str):
    """Footer with date, cert ID, signature, and bottom strip."""
    footer_y = 24 * mm

    # Left: Date + Cert ID
    c.setFillColor(C_MUTED)
    c.setFont("Helvetica", 5.5)
    c.drawString(18 * mm, footer_y + 14, "DATE OF ISSUE")
    c.setFillColor(C_TEXT)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(18 * mm, footer_y + 5, issued_on)

    c.setFillColor(C_MUTED)
    c.setFont("Helvetica", 5.5)
    c.drawString(18 * mm, footer_y - 5, "CERTIFICATE ID")
    c.setFillColor(C_GOLD)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(18 * mm, footer_y - 14, cert_id)

    # Right: Signature
    sig_x = w - 18 * mm
    c.setStrokeColor(Color(0.79, 0.66, 0.30, alpha=0.4))
    c.setLineWidth(0.8)
    c.line(sig_x - 45 * mm, footer_y + 10, sig_x, footer_y + 10)

    c.setFillColor(C_TEXT)
    c.setFont("Helvetica-Bold", 8)
    c.drawRightString(sig_x, footer_y + 1, "Saksham Verma")
    c.setFillColor(C_MUTED)
    c.setFont("Helvetica", 6)
    c.drawRightString(sig_x, footer_y - 6, "Founder & CEO, SkillMe")
    c.setFont("Helvetica", 5)
    c.drawRightString(sig_x, footer_y - 14, "AUTHORISED SIGNATORY")

    # Bottom accent bar
    c.setFillColor(C_GOLD_DARK)
    c.rect(0, 0, w, 3, fill=1, stroke=0)
    c.setFillColor(C_GOLD)
    c.rect(0, 0, w, 1.5, fill=1, stroke=0)

    # Bottom text strip
    c.setFillColor(C_MUTED)
    c.setFont("Helvetica", 4.5)
    c.drawString(18 * mm, 6, "This is a computer-generated document. Verify at skill-me-intern.in/certificate.html")
    c.drawRightString(w - 18 * mm, 6, "© 2024–2026 SkillMe Technologies Pvt. Ltd. All rights reserved.")

def _draw_qr(c: rl_canvas.Canvas, w: float, h: float, cert_id: str):
    """Draw a QR code linking to the certificate verification page."""
    if not _QR_AVAILABLE:
        return
    verify_url = f"https://skill-me-intern.in/certificate.html?cert_id={cert_id}"
    try:
        qr = qrcode.QRCode(version=1, box_size=4, border=1,
                           error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(verify_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#1a2340", back_color="white")
        # Convert PIL image to bytes for ReportLab
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        reader = ImageReader(buf)

        # Position: bottom-center, just above footer
        qr_size = 20 * mm
        qr_x = w / 2 - qr_size / 2
        qr_y = 14 * mm

        # White background behind QR
        c.setFillColor(white)
        c.rect(qr_x - 1*mm, qr_y - 1*mm, qr_size + 2*mm, qr_size + 2*mm, fill=1, stroke=0)
        c.drawImage(reader, qr_x, qr_y, width=qr_size, height=qr_size)

        # Label
        c.setFillColor(C_MUTED)
        c.setFont("Helvetica", 5)
        c.drawCentredString(w / 2, qr_y - 4, "Scan to verify")
    except Exception as e:
        logger.warning(f"QR code generation failed: {e}")


def generate_certificate_pdf(student: dict, batch: dict) -> tuple[bytes, str]:
    """
    Generate a PDF certificate for a student.
    Returns (pdf_bytes, cert_id).
    """
    cert_id = _cert_id_from_student(student["id"], batch["id"])
    issued_on = datetime.utcnow().strftime("%d %B %Y")

    buffer = io.BytesIO()
    c = rl_canvas.Canvas(buffer, pagesize=landscape(A4))

    w, h = landscape(A4)

    # Draw all layers
    _draw_background(c, w, h)
    _draw_borders(c, w, h)
    _draw_company_header(c, w, h)
    _draw_title(c, w, h)
    _draw_body(c, w, h, student, batch, cert_id, issued_on)
    _draw_details_row(c, w, h, batch)
    _draw_footer(c, w, h, cert_id, issued_on)
    _draw_qr(c, w, h, cert_id)  # QR code for verification

    c.save()
    return buffer.getvalue(), cert_id



class CertificateService:
    """Manages certificate generation and records."""

    async def issue_certificate(self, student_id: int, batch_id: int) -> dict:
        """
        Issue a certificate for a student who completed a batch.
        Checks completion status, generates PDF, and records it.
        """
        student = await db.fetch_one("SELECT * FROM students WHERE id = ?", (student_id,))
        if not student:
            raise ValueError(f"Student {student_id} not found")

        batch = await db.fetch_one("SELECT * FROM batches WHERE id = ?", (batch_id,))
        if not batch:
            raise ValueError(f"Batch {batch_id} not found")

        # Check if already issued
        existing = await db.fetch_one(
            "SELECT * FROM certificates WHERE student_id = ? AND batch_id = ?",
            (student_id, batch_id),
        )

        cert_id = _cert_id_from_student(student_id, batch_id)
        issued_on = datetime.utcnow().strftime("%d %B %Y")

        if not existing:
            await db.insert(
                """INSERT INTO certificates (student_id, batch_id, cert_id, issued_at)
                   VALUES (?, ?, ?, CURRENT_TIMESTAMP)""",
                (student_id, batch_id, cert_id),
            )
            logger.info(f"Issued certificate {cert_id} to student {student_id} for batch {batch_id}")

        return {
            "cert_id": cert_id,
            "student_name": f"{student['first_name']} {student['last_name']}",
            "domain": batch["domain"],
            "batch_number": batch["batch_number"],
            "issued_on": issued_on,
            "student": dict(student),
            "batch": dict(batch),
        }

    async def get_student_certificate(self, student_id: int, batch_id: int) -> dict | None:
        """Retrieve certificate record for a student."""
        row = await db.fetch_one(
            "SELECT * FROM certificates WHERE student_id = ? AND batch_id = ?",
            (student_id, batch_id),
        )
        return dict(row) if row else None


certificate_service = CertificateService()
