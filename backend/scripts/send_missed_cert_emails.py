"""
One-time script: retroactively send certificate-ready emails to the 3 students
whose certificates were issued without a notification email.

Run once from the backend/ directory:
    python scripts/send_missed_cert_emails.py
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import db
from services.email_service import email_service

MISSING = [
    {"cert_id": "SM-5E50-AC46-2A60", "email": "ttg336451@gmail.com",   "first_name": "JONNY",   "last_name": "Ttg",   "issued_at": "02 August 2026"},
    {"cert_id": "SM-429B-5148-DDFA", "email": "n8n.saksham@gmail.com", "first_name": "SAKSHAM", "last_name": "bisht", "issued_at": "08 August 2026"},
    {"cert_id": "SM-7636-ED2A-F101", "email": "h4930480@gmail.com",    "first_name": "SAKSHAM", "last_name": "doe",   "issued_at": "13 August 2026"},
]


async def main():
    await db.connect()
    for c in MISSING:
        row = await db.fetch_one(
            """SELECT b.domain, b.batch_number
               FROM certificates cert
               JOIN batches b ON cert.batch_id = b.id
               WHERE cert.cert_id = ?""",
            (c["cert_id"],),
        )
        if not row:
            print(f"SKIP {c['cert_id']} — batch not found")
            continue

        print(f"Sending to {c['email']} ({c['cert_id']}, {row['domain']})...")
        ok = await email_service.send_certificate_ready(
            first_name=c["first_name"],
            last_name=c["last_name"],
            email=c["email"],
            domain=row["domain"],
            batch_number=row["batch_number"],
            cert_id=c["cert_id"],
            issued_date=c["issued_at"],
        )
        print(f"  -> {'OK' if ok else 'FAILED'}")

    await db.disconnect()


asyncio.run(main())
