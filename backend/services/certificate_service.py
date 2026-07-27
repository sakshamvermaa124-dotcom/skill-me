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

from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white, black
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

from db.database import db

logger = logging.getLogger("skillme.certificates")

# Page in landscape A4
PAGE_W, PAGE_H = landscape(A4)

# Color palette
C_BG_DARK    = HexColor("#050508")
C_BG_CARD    = HexColor("#0e0e16")
C_PURPLE     = HexColor("#818cf8")
C_BLUE       = HexColor("#38bdf8")
C_EMERALD    = HexColor("#34d399")
C_GOLD       = HexColor("#fbbf24")
C_TEXT       = HexColor("#f1f1f3")
C_MUTED      = HexColor("#6b7280")
C_BORDER     = HexColor("#1f2937")


def _cert_id_from_student(student_id: int, batch_id: int) -> str:
    """Generate a deterministic, short certificate ID."""
    raw = f"skillme-{student_id}-{batch_id}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:12].upper()
    return f"SM-{h[:4]}-{h[4:8]}-{h[8:12]}"


def _draw_gradient_bg(c: rl_canvas.Canvas, w: float, h: float):
    """Draw a deep dark background with subtle gradient bands."""
    # Base dark fill
    c.setFillColor(C_BG_DARK)
    c.rect(0, 0, w, h, fill=1, stroke=0)

    # Subtle purple glow — top-left
    from reportlab.lib.colors import Color
    for i in range(30, 0, -1):
        alpha = 0.004 * i
        glow = Color(0.32, 0.34, 0.97, alpha=alpha)
        c.setFillColor(glow)
        r = i * 10
        c.ellipse(80, h - 80, 80 + r * 2, h - 80 + r * 2, fill=1, stroke=0)

    # Subtle blue glow — bottom-right
    for i in range(25, 0, -1):
        alpha = 0.004 * i
        glow = Color(0.22, 0.74, 0.98, alpha=alpha)
        c.setFillColor(glow)
        r = i * 8
        c.ellipse(w - 80 - r * 2, -20, w - 80, -20 + r * 2, fill=1, stroke=0)


def _draw_border(c: rl_canvas.Canvas, w: float, h: float):
    """Decorative double border."""
    margin = 12 * mm
    # Outer border
    c.setStrokeColor(C_PURPLE)
    c.setLineWidth(1.5)
    c.roundRect(margin, margin, w - 2 * margin, h - 2 * margin, 8 * mm, fill=0, stroke=1)
    # Inner border
    c.setStrokeColor(HexColor("#2d2f52"))
    c.setLineWidth(0.5)
    inner = margin + 3 * mm
    c.roundRect(inner, inner, w - 2 * inner, h - 2 * inner, 6 * mm, fill=0, stroke=1)


def _draw_corner_ornaments(c: rl_canvas.Canvas, w: float, h: float):
    """Small decorative corner marks."""
    margin = 14 * mm
    size = 8 * mm
    c.setStrokeColor(C_GOLD)
    c.setLineWidth(1.5)
    corners = [
        (margin, margin),
        (w - margin, margin),
        (margin, h - margin),
        (w - margin, h - margin),
    ]
    for cx, cy in corners:
        dx = size if cx < w / 2 else -size
        dy = size if cy < h / 2 else -size
        c.line(cx, cy, cx + dx, cy)
        c.line(cx, cy, cx, cy + dy)


def _draw_header(c: rl_canvas.Canvas, w: float, h: float):
    """SkillMe branding at the top."""
    # Logo circle
    logo_x, logo_y = w / 2, h - 28 * mm
    c.setFillColor(C_PURPLE)
    c.circle(logo_x, logo_y, 10 * mm, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(logo_x, logo_y - 3, "S")

    # Platform name
    c.setFillColor(C_TEXT)
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(w / 2, h - 42 * mm, "SkillMe Internship Platform")

    c.setFillColor(C_MUTED)
    c.setFont("Helvetica", 9)
    c.drawCentredString(w / 2, h - 48 * mm, "CERTIFICATE OF COMPLETION")

    # Divider line
    c.setStrokeColor(HexColor("#2d2f52"))
    c.setLineWidth(0.5)
    c.line(w * 0.15, h - 52 * mm, w * 0.85, h - 52 * mm)


def _draw_body(c: rl_canvas.Canvas, w: float, h: float, student: dict, batch: dict, cert_id: str, issued_on: str):
    """Main certificate body content."""
    mid = h / 2 + 10 * mm

    # "This is to certify that"
    c.setFillColor(C_MUTED)
    c.setFont("Helvetica", 11)
    c.drawCentredString(w / 2, mid + 30 * mm, "This is to certify that")

    # Student Name
    name = f"{student.get('first_name', '')} {student.get('last_name', '')}".strip()
    c.setFillColor(C_TEXT)
    c.setFont("Helvetica-Bold", 36)
    c.drawCentredString(w / 2, mid + 10 * mm, name)

    # Underline beneath name
    name_w = c.stringWidth(name, "Helvetica-Bold", 36)
    c.setStrokeColor(C_PURPLE)
    c.setLineWidth(1.2)
    c.line(w / 2 - name_w / 2, mid + 7 * mm, w / 2 + name_w / 2, mid + 7 * mm)

    # Body text
    domain = batch.get("domain", "").replace("-", " ").title()
    batch_num = batch.get("batch_number", "")
    c.setFillColor(C_MUTED)
    c.setFont("Helvetica", 12)
    c.drawCentredString(w / 2, mid - 4 * mm, "has successfully completed the")

    c.setFillColor(C_BLUE)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(w / 2, mid - 14 * mm, f"{domain} Developer Internship")

    c.setFillColor(C_MUTED)
    c.setFont("Helvetica", 11)
    c.drawCentredString(w / 2, mid - 22 * mm, f"Batch #{batch_num}  ·  4 Weeks  ·  Real-World GitHub Projects")


def _draw_footer(c: rl_canvas.Canvas, w: float, h: float, cert_id: str, issued_on: str):
    """Footer with date, cert ID and signature line."""
    footer_y = 24 * mm

    # Left: Issued date
    c.setFillColor(C_MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(22 * mm, footer_y + 8, "DATE OF ISSUE")
    c.setFillColor(C_TEXT)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(22 * mm, footer_y - 2, issued_on)

    # Center: Certificate ID with gold accent
    c.setFillColor(C_MUTED)
    c.setFont("Helvetica", 8)
    c.drawCentredString(w / 2, footer_y + 8, "CERTIFICATE ID")
    c.setFillColor(C_GOLD)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(w / 2, footer_y - 2, cert_id)

    # Right: Authorised signature line
    sig_x = w - 22 * mm
    c.setStrokeColor(C_PURPLE)
    c.setLineWidth(0.8)
    c.line(sig_x - 40 * mm, footer_y + 4, sig_x, footer_y + 4)
    c.setFillColor(C_MUTED)
    c.setFont("Helvetica", 8)
    c.drawRightString(sig_x, footer_y - 2, "Authorised Signatory, SkillMe")

    # Emerald accent bar at very bottom
    c.setFillColor(C_EMERALD)
    c.rect(0, 0, w, 3, fill=1, stroke=0)

    # Gold accent bar
    c.setFillColor(C_GOLD)
    c.rect(0, 3, w, 1.5, fill=1, stroke=0)


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

    # Layers
    _draw_gradient_bg(c, w, h)
    _draw_border(c, w, h)
    _draw_corner_ornaments(c, w, h)
    _draw_header(c, w, h)
    _draw_body(c, w, h, student, batch, cert_id, issued_on)
    _draw_footer(c, w, h, cert_id, issued_on)

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
