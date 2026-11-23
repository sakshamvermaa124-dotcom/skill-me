"""
SkillMe Backend — Configuration
Loads environment variables with pydantic-settings for validation.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    model_config = SettingsConfigDict(extra="ignore", env_file=".env", env_file_encoding="utf-8")

    # Server
    port: int = 8000
    host: str = "0.0.0.0"
    # The public URL of this backend.
    backend_url: str = ""
    # Safety interlock: the engagement engine can only send real emails when this is true,
    # no matter what the admin setting says. Keep false in dev/test/staging.
    engagement_live_allowed: bool = False

    # Admin Auth
    admin_api_key: str = ""  # set ADMIN_API_KEY in the environment; empty = admin API locked

    # Database — Turso (LibSQL)
    # In production: set TURSO_DB_URL and TURSO_AUTH_TOKEN in Render env vars
    # For local dev: leave TURSO_AUTH_TOKEN blank and set TURSO_DB_URL to a local file path
    turso_db_url: str = "local.db"      # e.g. libsql://your-db-name.turso.io
    turso_auth_token: str = ""           # Turso auth token (blank = local SQLite)

    # ── Email (Brevo SMTP relay) ───────────────────
    email_enabled: bool = True
    smtp_host: str = "smtp-relay.brevo.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    # Extra Brevo accounts used when the primary hits its daily cap. JSON list, e.g.
    # [{"user": "b@example.com", "password": "xsmtpsib-..."}]
    smtp_extra_accounts: str = ""
    # Switch to the next account once an account has sent this many emails in the last 24h (Brevo free cap is 300)
    smtp_daily_limit: int = 295
    smtp_from_name: str = "SkillMe Team"
    smtp_from_email: str = ""
    frontend_url: str = "https://skill-me-intern.in"
    # Shared secret appended as ?key=... to the Brevo webhook URL to authenticate inbound event callbacks
    brevo_webhook_secret: str = ""
    # Brevo v3 REST API key (Settings → SMTP & API → API Keys — NOT the SMTP key) — used only
    # by the one-off engagement backfill script to pull historical open/click/bounce events.
    brevo_api_key: str = ""
    # Comma-separated list of allowed CORS origins.
    allowed_origins: str = "*"

    # ── Razorpay (Payment Gateway) ──────────────
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    # Webhook secret from Razorpay Dashboard > Webhooks (NOT the API key secret). Blank = webhook rejected.
    razorpay_webhook_secret: str = ""
    certificate_price_paise: int = 12900  # ₹129 in paise (students in India)
    # Students abroad pay in USD (Razorpay won't settle foreign cards on a ₹129 ticket).
    # See services/pricing.py for which countries get the reduced price.
    certificate_price_usd_cents: int = 400           # US$4
    certificate_price_usd_reduced_cents: int = 200   # US$2, lower-income countries
    # Only for analytics: USD orders are counted in revenue at this rate (Razorpay settles in INR).
    usd_inr_rate: float = 88.0

    # ── Student Auth (OTP + JWT) ─────────────────
    jwt_secret_key: str = "changeme-set-a-strong-secret-in-render"
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 30
    otp_expiry_minutes: int = 10
    otp_max_attempts: int = 5            # wrong guesses before a code is locked
    otp_max_requests: int = 3            # codes one email can request per window
    otp_request_window_minutes: int = 15

    @property
    def db_path(self) -> str:
        """Returns the database URL (Turso remote or local SQLite path)."""
        return self.turso_db_url


settings = Settings()
