"""
SkillMe — Student Auth Routes
OTP-based login for students (no passwords).
"""

import logging
from fastapi import APIRouter, HTTPException, Response, Cookie
from pydantic import BaseModel, EmailStr
from typing import Optional

from services.auth_service import request_otp, verify_otp, decode_jwt
from services.email_service import email_service, _send_and_log
from middleware.student_auth import require_student
from db.database import db
from config import settings
from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request

limiter = Limiter(key_func=get_remote_address)

logger = logging.getLogger("skillme.auth_routes")
router = APIRouter(prefix="/api/auth", tags=["auth"])


class OTPRequest(BaseModel):
    email: str


class OTPVerify(BaseModel):
    email: str
    otp: str


@router.post("/request-otp", summary="Request a login OTP")
@limiter.limit("3/minute")
async def request_login_otp(request: Request, req: OTPRequest):
    """
    Send a 6-digit OTP to the student's registered email.
    The OTP expires in 10 minutes.
    """
    try:
        result = await request_otp(req.email)
    except ValueError as e:
        # Don't reveal if email exists or not (security)
        raise HTTPException(status_code=404, detail=str(e))

    # Send OTP via email
    student = result["student"]
    otp = result["otp"]
    html_body = f"""
    <div style="font-family:Inter,sans-serif;max-width:480px;margin:0 auto;padding:32px;background:#ffffff;color:#1e293b;border-radius:16px;border:1px solid #e2e8f0;">
      <div style="font-size:2rem;text-align:center;margin-bottom:8px;">🔐</div>
      <h2 style="text-align:center;color:#4f46e5;margin-bottom:4px;">Your SkillMe Login Code</h2>
      <p style="text-align:center;color:#64748b;margin-bottom:24px;">Hi {student['first_name']}, use this OTP to sign in to your dashboard.</p>
      <div style="background:#f8fafc;border:2px solid #e0e7ff;border-radius:12px;padding:24px;text-align:center;margin-bottom:24px;">
        <div style="font-size:2.5rem;font-weight:700;letter-spacing:0.4em;color:#4f46e5;font-family:monospace;">{otp}</div>
        <div style="color:#64748b;font-size:0.8rem;margin-top:8px;">Expires in {settings.otp_expiry_minutes} minutes</div>
      </div>
      <p style="color:#94a3b8;font-size:0.8rem;text-align:center;">If you didn't request this, you can safely ignore this email.</p>
    </div>
    """
    await _send_and_log(
        req.email.lower().strip(),
        f"{student['first_name']} {student['last_name']}",
        "🔐 Your SkillMe Login Code",
        html_body,
        email_type="otp_login",
        student_id=student["id"],
    )

    return {"status": "sent", "message": f"OTP sent to {req.email}"}


@router.post("/verify-otp", summary="Verify OTP and get session token")
async def verify_login_otp(req: OTPVerify, response: Response):
    """
    Verify the OTP and issue a 30-day JWT session.
    Sets an httpOnly cookie AND returns the token in the response body.
    """
    token = await verify_otp(req.email, req.otp)
    if not token:
        raise HTTPException(status_code=401, detail="Invalid or expired OTP. Please try again.")

    # Set httpOnly cookie (7-day expiry)
    response.set_cookie(
        key="skillme_token",
        value=token,
        max_age=settings.jwt_expire_days * 86400,
        httponly=True,
        samesite="lax",
        secure=True,  # HTTPS only in production
    )

    return {"status": "authenticated", "token": token}


@router.get("/me", summary="Get current student from session")
async def get_me(skillme_token: Optional[str] = Cookie(None)):
    """
    Return the currently authenticated student's profile.
    """
    if not skillme_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_jwt(skillme_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")

    student_id = int(payload["sub"])
    student = await db.fetch_one(
        """SELECT s.*, e.batch_id, b.domain, b.batch_number, b.repo_name,
                  b.start_date, e.status as enrollment_status
           FROM students s
           LEFT JOIN enrollments e ON e.student_id = s.id AND e.status != 'dropped'
           LEFT JOIN batches b ON b.id = e.batch_id
           WHERE s.id = ?
           LIMIT 1""",
        (student_id,)
    )
    if not student:
        raise HTTPException(status_code=401, detail="Student not found.")

    return dict(student)


@router.post("/logout", summary="Log out student")
async def logout(response: Response):
    """Clear the session cookie."""
    response.delete_cookie("skillme_token")
    return {"status": "logged_out"}
