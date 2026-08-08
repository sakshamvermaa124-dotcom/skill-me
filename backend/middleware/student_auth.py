"""
SkillMe — Student Auth Middleware
FastAPI dependency for protecting student-facing endpoints.
"""

from fastapi import HTTPException, Cookie, Header
from typing import Optional
from services.auth_service import decode_jwt
from db.database import db


async def require_student(
    authorization: Optional[str] = Header(None),
    skillme_token: Optional[str] = Cookie(None),
) -> dict:
    """
    FastAPI dependency: validates the student JWT from either:
    - Authorization: Bearer <token> header
    - skillme_token httpOnly cookie

    Returns the student row from DB on success.
    Raises 401 if not authenticated.
    """
    token = None

    # Try Authorization header first
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    elif skillme_token:
        token = skillme_token

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_jwt(token)
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Session expired or invalid. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    student_id = int(payload["sub"])
    student = await db.fetch_one(
        "SELECT id, first_name, last_name, email, github_username, status FROM students WHERE id = ?",
        (student_id,)
    )
    if not student:
        raise HTTPException(status_code=401, detail="Student account not found.")

    return dict(student)
