"""
test_offer_email.py -- Send a test offer letter email to the SMTP sender address.
No live student used.
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from config import settings
from services.email_service import email_service


async def main():
    target_email = settings.smtp_from_email
    print(f"\n[EMAIL]  Sending test offer letter to: {target_email}\n")

    ok = await email_service.send_offer_letter(
        first_name="Test",
        last_name="Student",
        email=target_email,
        domain="web-dev",
        batch_number=2,
        joining_date=None,   # will be set to today automatically
        repo_url="https://github.com/sakshamvermaa124-dotcom/web-dev-batch-2",
        github_username="test-student",
    )

    if ok:
        print("[OK]  Offer letter sent! Check inbox at:", target_email)
    else:
        print("[FAIL]  Offer letter email FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
