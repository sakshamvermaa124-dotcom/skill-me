"""
Retroactively send certificate-ready emails for certificates that were issued
without a notification email going out.

Looks the recipients up from the DB by certificate ID (or by student email)
instead of hardcoding student PII in this file — pass the cert IDs (or emails)
as CLI args.

Run from the backend/ directory:
    python scripts/send_missed_cert_emails.py --cert-id SM-XXXX-XXXX-XXXX [--cert-id ...]
    python scripts/send_missed_cert_emails.py --email someone@example.com [--email ...]
"""
import argparse
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import db
from services.email_service import email_service


async def _send_for_row(row: dict) -> bool:
    print(f"Sending to {row['email']} ({row['cert_id']}, {row['domain']})...")
    ok = await email_service.send_certificate_ready(
        first_name=row["first_name"],
        last_name=row["last_name"],
        email=row["email"],
        domain=row["domain"],
        cert_id=row["cert_id"],
        issued_date=row["issued_at"],
    )
    print(f"  -> {'OK' if ok else 'FAILED'}")
    return ok


async def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cert-id", action="append", default=[], help="Certificate ID, e.g. SM-XXXX-XXXX-XXXX (repeatable)")
    parser.add_argument("--email", action="append", default=[], help="Student email — resends for their most recent certificate (repeatable)")
    args = parser.parse_args()

    if not args.cert_id and not args.email:
        parser.error("Provide at least one --cert-id or --email")

    await db.connect()

    for cert_id in args.cert_id:
        row = await db.fetch_one(
            """SELECT cert.cert_id, cert.issued_at, s.first_name, s.last_name, s.email,
                      COALESCE(b.domain, s.domain) AS domain
               FROM certificates cert
               JOIN students s ON s.id = cert.student_id
               LEFT JOIN batches b ON cert.batch_id = b.id
               WHERE cert.cert_id = ?""",
            (cert_id,),
        )
        if not row:
            print(f"SKIP {cert_id} — certificate not found")
            continue
        await _send_for_row(row)

    for email in args.email:
        row = await db.fetch_one(
            """SELECT cert.cert_id, cert.issued_at, s.first_name, s.last_name, s.email,
                      COALESCE(b.domain, s.domain) AS domain
               FROM certificates cert
               JOIN students s ON s.id = cert.student_id
               LEFT JOIN batches b ON cert.batch_id = b.id
               WHERE LOWER(s.email) = LOWER(?)
               ORDER BY cert.issued_at DESC LIMIT 1""",
            (email,),
        )
        if not row:
            print(f"SKIP {email} — no certificate found for this student")
            continue
        await _send_for_row(row)

    await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
