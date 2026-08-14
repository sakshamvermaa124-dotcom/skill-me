"""
test_weekly_email.py — Send a test weekly-tasks email to the SMTP sender address.

Usage:
    python test_weekly_email.py

Sends to SMTP_FROM_EMAIL (your own address) so no live student is touched.
"""
import asyncio
import sys
import os

# Allow imports from the backend package root
sys.path.insert(0, os.path.dirname(__file__))

from config import settings
from services.email_service import email_service


DUMMY_TASKS = [
    {
        "title": "Build a Responsive Navbar",
        "issue_url": "https://github.com/sakshamvermaa124-dotcom/web-dev-batch-2/issues/1",
    },
    {
        "title": "Create a Hero Section with CSS Animations",
        "issue_url": "https://github.com/sakshamvermaa124-dotcom/web-dev-batch-2/issues/2",
    },
    {
        "title": "Implement a Contact Form with Validation",
        "issue_url": "https://github.com/sakshamvermaa124-dotcom/web-dev-batch-2/issues/3",
    },
]


async def main():
    target_email = settings.smtp_from_email   # send to yourself — no live user
    print(f"\n[EMAIL]  Sending test weekly-tasks email to: {target_email}")
    print(f"    SMTP host : {settings.smtp_host}:{settings.smtp_port}")
    print(f"    EMAIL_ENABLED = {settings.email_enabled}\n")

    ok = await email_service.send_weekly_tasks_notification(
        first_name="Test",
        last_name="Student",
        email=target_email,
        domain="web-dev",
        batch_number=2,
        week_number=1,
        tasks=DUMMY_TASKS,
        repo_url="https://github.com/sakshamvermaa124-dotcom/web-dev-batch-2",
        github_username="test-student",
    )

    if ok:
        print("[OK]  Email sent successfully! Check your inbox at:", target_email)
    else:
        print("[FAIL]  Email FAILED -- check SMTP credentials / logs above.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
