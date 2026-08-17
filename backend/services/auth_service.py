"""
SkillMe — Student Auth Service
Handles OTP generation, verification, and JWT token management.
"""

import hashlib
import random
import string
import logging
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt

from config import settings
from db.database import db

logger = logging.getLogger("skillme.auth")


def _hash_otp(otp: str) -> str:
    """SHA-256 hash the OTP for safe storage."""
    return hashlib.sha256(otp.encode()).hexdigest()


def _generate_otp() -> str:
    """Generate a random 6-digit numeric OTP."""
    return "".join(random.choices(string.digits, k=6))


def _create_jwt(student_id: int, email: str) -> str:
    """Create a signed JWT for a student session."""
    expire = datetime.utcnow() + timedelta(days=settings.jwt_expire_days)
    payload = {
        "sub": str(student_id),
        "email": email,
        "exp": expire,
        "type": "student",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_jwt(token: str) -> Optional[dict]:
    """Decode and validate a student JWT. Returns payload or None."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "student":
            return None
        return payload
    except JWTError:
        return None


async def request_otp(email: str) -> dict:
    """
    Generate and store an OTP for the given email.
    Returns the OTP (caller is responsible for emailing it).
    Raises ValueError if the email is not a registered student.
    """
    # Check student exists
    student = await db.fetch_one(
        "SELECT id, first_name, last_name, status FROM students WHERE email = ?",
        (email.lower().strip(),)
    )
    if not student:
        raise ValueError("No student account found with this email address.")

    otp = _generate_otp()
    otp_hash = _hash_otp(otp)
    expires_at = (datetime.utcnow() + timedelta(minutes=settings.otp_expiry_minutes)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # Invalidate any existing unused OTPs for this email
    await db.execute(
        "UPDATE otp_tokens SET used = 1 WHERE email = ? AND used = 0",
        (email.lower().strip(),)
    )

    # Store new OTP
    await db.insert(
        "INSERT INTO otp_tokens (email, otp_hash, expires_at) VALUES (?, ?, ?)",
        (email.lower().strip(), otp_hash, expires_at),
    )

    logger.info(f"OTP generated for {email}")
    return {
        "otp": otp,
        "student": dict(student),
        "expires_in_minutes": settings.otp_expiry_minutes,
    }


async def verify_otp(email: str, otp: str) -> Optional[str]:
    """
    Verify the OTP and return a JWT if valid.
    Returns None if OTP is invalid or expired.
    """
    email = email.lower().strip()
    otp_hash = _hash_otp(otp)

    # Fetch both OTP token and Student info in a single network roundtrip
    row = await db.fetch_one(
        """SELECT o.id, o.expires_at, s.id as student_id, s.email as student_email 
           FROM otp_tokens o
           JOIN students s ON s.email = o.email
           WHERE o.email = ? AND o.otp_hash = ? AND o.used = 0
           ORDER BY o.created_at DESC LIMIT 1""",
        (email, otp_hash),
    )

    if not row:
        return None

    # Check expiry
    try:
        expires_at = datetime.strptime(row["expires_at"], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        expires_at = datetime.strptime(row["expires_at"], "%Y-%m-%dT%H:%M:%S")

    if datetime.utcnow() > expires_at:
        return None

    # Mark OTP as used
    # We still await this to prevent race conditions on double OTP usage,
    # but we've eliminated one full sequential DB roundtrip.
    await db.execute(
        "UPDATE otp_tokens SET used = 1 WHERE id = ?",
        (row["id"],)
    )

    jwt_token = _create_jwt(row["student_id"], row["student_email"])
    logger.info(f"OTP verified for {email}, JWT issued")
    return jwt_token
