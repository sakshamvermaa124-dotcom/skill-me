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
    admin_api_key: str = "dev-admin-key"

    # Database — Turso (LibSQL)
    # In production: set TURSO_DB_URL and TURSO_AUTH_TOKEN in Render env vars
    # For local dev: leave TURSO_AUTH_TOKEN blank and set TURSO_DB_URL to a local file path
    turso_db_url: str = "local.db"      # e.g. libsql://your-db-name.turso.io
    turso_auth_token: str = ""           # Turso auth token (blank = local SQLite)

    # GitHub API base URL
    github_api_url: str = "https://api.github.com"

    # ── Email (Brevo SMTP relay) ───────────────────
    email_enabled: bool = True          # Will attempt to send emails if SMTP creds are in .env
    smtp_host: str = "smtp-relay.brevo.com"
    smtp_port: int = 587
    smtp_user: str = ""                  # Your Brevo login email
    smtp_password: str = ""             # Brevo SMTP key (Settings → SMTP & API)
    smtp_from_name: str = "SkillMe Team"
    smtp_from_email: str = ""           # Must match / be verified in Brevo
    frontend_url: str = "https://skill-me-intern.in"  # Base URL for email CTAs
    # Comma-separated list of allowed CORS origins. Use "*" for dev.
    # In production set to: https://your-app.vercel.app,https://yourcustom.domain
    allowed_origins: str = "*"

    # ── Razorpay (Payment Gateway) ──────────────
    razorpay_key_id: str = ""           # rzp_test_... or rzp_live_...
    razorpay_key_secret: str = ""       # Found in Razorpay Dashboard → Settings → API Keys
    certificate_price_paise: int = 24900  # ₹249 in paise (1 ₹ = 100 paise)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def db_path(self) -> str:
        """Returns the database URL (Turso remote or local SQLite path)."""
        return self.turso_db_url


settings = Settings()
