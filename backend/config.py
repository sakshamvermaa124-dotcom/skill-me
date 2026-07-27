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

    # Database
    database_path: str = "data/skillme.db"

    # GitHub API base URL
    github_api_url: str = "https://api.github.com"

    # ── Email (Brevo SMTP relay) ───────────────────
    email_enabled: bool = False          # Set True once SMTP creds are in .env
    smtp_host: str = "smtp-relay.brevo.com"
    smtp_port: int = 587
    smtp_user: str = ""                  # Your Brevo login email
    smtp_password: str = ""             # Brevo SMTP key (Settings → SMTP & API)
    smtp_from_name: str = "SkillMe Team"
    smtp_from_email: str = ""           # Must match / be verified in Brevo
    frontend_url: str = "https://skill-me.onrender.com"  # Base URL for email CTAs
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
    def db_path(self) -> Path:
        """Returns the absolute database path, creating parent dirs if needed."""
        path = Path(self.database_path)
        if not path.is_absolute():
            path = Path(__file__).parent / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
