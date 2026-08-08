"""
SkillMe — Referral System Routes
Manage referral codes, track conversions, and apply discounts.
"""

import random
import string
import logging
from fastapi import APIRouter, HTTPException, Depends
from middleware.student_auth import require_student
from db.database import db
from config import settings

logger = logging.getLogger("skillme.referrals")
router = APIRouter(prefix="/api/referrals", tags=["referrals"])

FRONTEND_URL = settings.frontend_url


def _generate_code() -> str:
    """Generate a short referral code like SKM-A1B2C3."""
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(random.choices(chars, k=6))
    return f"SKM-{suffix}"


async def _get_or_create_code(student_id: int) -> str:
    """Return existing referral code or create a new one."""
    row = await db.fetch_one(
        "SELECT code FROM referral_codes WHERE student_id = ?",
        (student_id,)
    )
    if row:
        return row["code"]

    # Generate unique code (retry on collision)
    for _ in range(10):
        code = _generate_code()
        existing = await db.fetch_one(
            "SELECT id FROM referral_codes WHERE code = ?", (code,)
        )
        if not existing:
            await db.insert(
                "INSERT INTO referral_codes (student_id, code) VALUES (?, ?)",
                (student_id, code)
            )
            return code

    raise RuntimeError("Could not generate unique referral code")


@router.get("/code", summary="Get my referral code and link")
async def get_referral_code(student: dict = Depends(require_student)):
    """Return the student's unique referral code and shareable link."""
    code = await _get_or_create_code(student["id"])
    referral_link = f"{FRONTEND_URL}/apply?ref={code}"
    return {
        "code": code,
        "referral_link": referral_link,
        "discount_per_referral_inr": settings.referral_discount_paise // 100,
        "ambassador_threshold": settings.referral_ambassador_threshold,
    }


@router.get("/stats", summary="Get my referral stats")
async def get_referral_stats(student: dict = Depends(require_student)):
    """
    Return referral conversion counts and total discount earned.
    Also returns ambassador status if threshold is met.
    """
    conversions = await db.fetch_all(
        """SELECT rc.status, rc.discount_applied, rc.referred_email,
                  s.first_name, s.last_name
           FROM referral_conversions rc
           LEFT JOIN students s ON s.id = rc.referred_student_id
           WHERE rc.referrer_student_id = ?
           ORDER BY rc.created_at DESC""",
        (student["id"],)
    )

    total_clicked = len(conversions)
    total_applied = sum(1 for c in conversions if c["status"] in ("applied", "enrolled"))
    total_enrolled = sum(1 for c in conversions if c["status"] == "enrolled")
    total_discount_paise = sum(c["discount_applied"] or 0 for c in conversions)
    is_ambassador = total_enrolled >= settings.referral_ambassador_threshold

    return {
        "total_clicked": total_clicked,
        "total_applied": total_applied,
        "total_enrolled": total_enrolled,
        "total_discount_earned_inr": total_discount_paise // 100,
        "is_ambassador": is_ambassador,
        "ambassador_threshold": settings.referral_ambassador_threshold,
        "conversions": [dict(c) for c in conversions],
    }


@router.get("/discount/{student_id}", summary="Get available referral discount for student")
async def get_discount(student_id: int):
    """
    Returns how much referral discount a student is entitled to on their certificate.
    Called by the payments route before creating a Razorpay order.
    """
    # Count enrolled referrals not yet discounted
    conversions = await db.fetch_all(
        """SELECT id FROM referral_conversions
           WHERE referrer_student_id = ? AND status = 'enrolled' AND discount_applied = 0""",
        (student_id,)
    )
    discount_paise = len(conversions) * settings.referral_discount_paise
    # Cap at full certificate price
    discount_paise = min(discount_paise, settings.certificate_price_paise)
    final_price_paise = settings.certificate_price_paise - discount_paise

    return {
        "referrals_unused": len(conversions),
        "discount_paise": discount_paise,
        "discount_inr": discount_paise // 100,
        "original_price_paise": settings.certificate_price_paise,
        "final_price_paise": final_price_paise,
        "final_price_inr": final_price_paise // 100,
    }


async def record_referral_application(referred_email: str, referred_student_id: int, ref_code: str):
    """
    Called when a new student applies using a referral code.
    Updates the conversion to 'applied'.
    """
    code_row = await db.fetch_one(
        "SELECT student_id FROM referral_codes WHERE code = ?", (ref_code.upper(),)
    )
    if not code_row:
        return  # Invalid code — silently skip

    referrer_id = code_row["student_id"]
    if referrer_id == referred_student_id:
        return  # Can't refer yourself

    # Upsert conversion record
    existing = await db.fetch_one(
        "SELECT id FROM referral_conversions WHERE referrer_student_id = ? AND referred_email = ?",
        (referrer_id, referred_email)
    )
    if existing:
        await db.execute(
            """UPDATE referral_conversions
               SET referred_student_id = ?, status = 'applied', updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (referred_student_id, existing["id"])
        )
    else:
        await db.insert(
            """INSERT INTO referral_conversions
               (referrer_student_id, referred_student_id, referred_email, status)
               VALUES (?, ?, ?, 'applied')""",
            (referrer_id, referred_student_id, referred_email)
        )
    logger.info(f"Referral applied: referrer={referrer_id}, referred={referred_student_id}")


async def record_referral_enrollment(referred_student_id: int):
    """
    Called when a referred student is enrolled in a batch.
    Updates status to 'enrolled' so the referrer earns their discount.
    """
    await db.execute(
        """UPDATE referral_conversions
           SET status = 'enrolled', updated_at = CURRENT_TIMESTAMP
           WHERE referred_student_id = ? AND status = 'applied'""",
        (referred_student_id,)
    )
    logger.info(f"Referral enrolled: referred_student_id={referred_student_id}")
