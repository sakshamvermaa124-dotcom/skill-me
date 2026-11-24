"""
SkillMe — Student Auth Service
Handles OTP generation, verification, and JWT token management.
"""

import hashlib
import hmac
import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt

from config import settings
from db.database import db

logger = logging.getLogger("skillme.auth")


class OTPRateLimited(Exception):
    """Too many codes requested for one email inside the request window."""


class OTPLocked(Exception):
    """Too many wrong guesses: the current code no longer works."""


def _hash_otp(email: str, otp: str) -> str:
    """HMAC the OTP with the server secret, bound to the email.

    A bare SHA-256 of a 6-digit code is reversed by hashing all 1M values, so a
    leaked otp_tokens table would expose every live code. The key prevents that.
    """
    msg = f"otp:{email.lower().strip()}:{otp.strip()}".encode()
    return hmac.new(settings.jwt_secret_key.encode(), msg, hashlib.sha256).hexdigest()


def _generate_otp() -> str:
    """Generate a 6-digit numeric OTP from a cryptographically secure source."""
    return f"{secrets.randbelow(1_000_000):06d}"


def _utc_str(dt: datetime) -> str:
    """Same format SQLite's CURRENT_TIMESTAMP uses, so string comparison works."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def offer_ref(student_id: int) -> str:
    """Unguessable reference printed on a student's offer letter / HOD pack (QR + links).
    Lets a college verify the letter without exposing a lookup by sequential student id."""
    digest = hmac.new(settings.jwt_secret_key.encode(), f"offer:{int(student_id)}".encode(), hashlib.sha256)
    return digest.hexdigest()[:16]


# How much of the signed reference the printed Offer ID carries. 48 bits per student is
# far beyond guessing, and short enough to type off a printed letter.
OFFER_CODE_HEX = 12


def offer_code(student_id: int) -> str:
    """The typeable Offer ID printed on the letter, e.g. OF-0812-A1B2-C3D4-E5F6.
    Anyone can enter it at /verify; it carries part of the signed reference, so ids
    still can't be enumerated."""
    r = offer_ref(student_id)[:OFFER_CODE_HEX].upper()
    return f"OF-{int(student_id):04d}-{r[0:4]}-{r[4:8]}-{r[8:12]}"


def offer_ref_valid(student_id: int, ref: str) -> bool:
    """Accepts the full signed reference (QR links) or the short one in the Offer ID."""
    given = (ref or "").strip().lower().replace("-", "")
    full = offer_ref(student_id)
    if len(given) == len(full):
        return hmac.compare_digest(full, given)
    if len(given) == OFFER_CODE_HEX:
        return hmac.compare_digest(full[:OFFER_CODE_HEX], given)
    return False


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
        "SELECT id, first_name, last_name, status FROM students WHERE lower(email) = ? ORDER BY id DESC",
        (email.lower().strip(),)
    )
    if not student:
        raise ValueError("No student account found with this email address.")

    # Per-email cap. The per-IP limit on the route can't stop someone rotating IPs
    # to flood one inbox (and burn email quota), so count codes issued to this email.
    email_key = email.lower().strip()
    window_start = _utc_str(datetime.utcnow() - timedelta(minutes=settings.otp_request_window_minutes))
    recent = await db.fetch_one(
        "SELECT COUNT(*) AS n FROM otp_tokens WHERE email = ? AND created_at >= ?",
        (email_key, window_start),
    )
    if recent and int(recent["n"] or 0) >= settings.otp_max_requests:
        logger.warning("OTP request limit hit for %s", email_key)
        raise OTPRateLimited(
            f"Too many codes requested. Please wait {settings.otp_request_window_minutes} minutes "
            "and try again, or use the latest code we sent you."
        )

    otp = _generate_otp()
    otp_hash = _hash_otp(email_key, otp)
    expires_at = _utc_str(datetime.utcnow() + timedelta(minutes=settings.otp_expiry_minutes))

    # Invalidate any existing unused OTPs for this email. 2 = superseded, distinct from
    # 1 = actually used to log in, so admin "active people" counts real logins only.
    await db.execute(
        "UPDATE otp_tokens SET used = 2 WHERE email = ? AND used = 0",
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
    Returns None if the code is wrong, expired or missing.
    Raises OTPLocked once the current code has taken settings.otp_max_attempts guesses.
    """
    email = email.lower().strip()

    # Only the newest unused code can be valid: requesting a new one supersedes the rest.
    row = await db.fetch_one(
        """SELECT o.id, o.otp_hash, o.expires_at, COALESCE(o.attempts, 0) AS attempts,
                  s.id AS student_id, s.email AS student_email
           FROM otp_tokens o
           JOIN students s ON lower(s.email) = o.email
           WHERE o.email = ? AND o.used = 0
           ORDER BY o.created_at DESC, o.id DESC, s.id DESC LIMIT 1""",
        (email,),
    )
    if not row:
        return None

    try:
        expires_at = datetime.strptime(row["expires_at"], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        expires_at = datetime.strptime(row["expires_at"], "%Y-%m-%dT%H:%M:%S")
    if datetime.utcnow() > expires_at:
        return None

    max_attempts = settings.otp_max_attempts
    if int(row["attempts"]) >= max_attempts:
        raise OTPLocked()

    # Count the attempt before comparing, then read the counter back. Writes are
    # serialised, so the k-th concurrent request always reads a value >= k: parallel
    # requests can't sneak extra guesses past the cap.
    await db.execute(
        "UPDATE otp_tokens SET attempts = COALESCE(attempts, 0) + 1 WHERE id = ?",
        (row["id"],),
    )
    counted = await db.fetch_one("SELECT attempts FROM otp_tokens WHERE id = ?", (row["id"],))
    attempts = int(counted["attempts"]) if counted else max_attempts + 1
    if attempts > max_attempts:
        raise OTPLocked()

    if not hmac.compare_digest(row["otp_hash"], _hash_otp(email, otp)):
        logger.info("Wrong OTP for %s (attempt %d/%d)", email, attempts, max_attempts)
        if attempts >= max_attempts:
            raise OTPLocked()
        return None

    await db.execute(
        "UPDATE otp_tokens SET used = 1, verified_at = CURRENT_TIMESTAMP WHERE id = ? AND used = 0",
        (row["id"],),
    )

    jwt_token = _create_jwt(row["student_id"], row["student_email"])
    logger.info(f"OTP verified for {email}, JWT issued")
    return jwt_token
