"""
SkillMe Backend — Configuration
Loads environment variables with pydantic-settings for validation.
"""

from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # GitHub
    skillme_github_token: str = ""
    github_org: str = "skill-me-intern"

    # Server
    port: int = 8000
    host: str = "0.0.0.0"

    # Webhook
    webhook_secret: str = ""

    # Admin Auth
    admin_api_key: str = "sakshamm"

    # Database — Turso (LibSQL)
    # In production: set TURSO_DB_URL and TURSO_AUTH_TOKEN in Render env vars
    # For local dev: leave TURSO_AUTH_TOKEN blank and set TURSO_DB_URL to a local file path
    turso_db_url: str = "local.db"      # e.g. libsql://your-db-name.turso.io
    turso_auth_token: str = ""           # Turso auth token (blank = local SQLite)

    # GitHub API base URL
    github_api_url: str = "https://api.github.com"

    # ── Email (Brevo SMTP relay) ───────────────────
    email_enabled: bool = True
    smtp_host: str = "smtp-relay.brevo.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_name: str = "SkillMe Team"
    smtp_from_email: str = ""
    frontend_url: str = "https://skill-me-intern.in"
    # Comma-separated list of allowed CORS origins.
    allowed_origins: str = "*"

    # ── Razorpay (Payment Gateway) ──────────────
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    certificate_price_paise: int = 9900  # ₹99 in paise

    # ── Student Auth (OTP + JWT) ─────────────────
    jwt_secret_key: str = "changeme-set-a-strong-secret-in-render"
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 7
    otp_expiry_minutes: int = 10

    # ── Referral System ──────────────────────────
    referral_discount_paise: int = 2000   # ₹20 off certificate per referral
    referral_ambassador_threshold: int = 5  # referrals needed for Ambassador badge

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def db_path(self) -> str:
        """Returns the database URL (Turso remote or local SQLite path)."""
        return self.turso_db_url


settings = Settings()
