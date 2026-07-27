"""
SkillMe — Auth Middleware
Simple API key authentication for admin endpoints.
"""

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader
from config import settings

api_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)


async def require_admin(api_key: str = Security(api_key_header)) -> str:
    """Dependency that validates the admin API key."""
    if not api_key or api_key != settings.admin_api_key:
        raise HTTPException(
            status_code=403,
            detail="Invalid or missing admin API key. Provide X-Admin-Key header.",
        )
    return api_key
