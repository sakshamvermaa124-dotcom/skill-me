"""
Email certificate holders whose documents showed an internship period that wasn't ~4 weeks
(joining date -> day the certificate was claimed), telling them the certificate and LOR now
cover exactly one month from their joining date, and that they can move the joining date
earlier from the dashboard (services/doc_dates_service.py).

Who: every non-test certificate whose old period (start_date -> issued_at) was not 28-31 days,
or had no start date. One email per person; anyone already sent a `dates_update` email is skipped.

Run from the backend/ directory:
    python scripts/send_dates_update_emails.py            # dry run: list who would get it
    python scripts/send_dates_update_emails.py --send     # actually send
    python scripts/send_dates_update_emails.py --send --only someone@example.com
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import db
from services.doc_dates_service import doc_dates_status
from services.email_service import email_service

FOUR_WEEKS_OK = range(28, 32)  # 28-31 days already read as "one month"


async def candidates() -> list[dict]:
    rows = await db.fetch_all(
        """SELECT c.student_id, c.batch_id, c.cert_id, c.issued_at, b.start_date,
                  s.first_name, s.last_name, s.email, COALESCE(b.domain, s.domain) AS domain,
                  CAST(julianday(date(c.issued_at)) - julianday(b.start_date) AS INTEGER) AS old_days
           FROM certificates c
           JOIN students s ON s.id = c.student_id
           LEFT JOIN batches b ON b.id = c.batch_id
           WHERE COALESCE(s.is_test, 0) = 0
           ORDER BY c.issued_at"""
    )
    sent = {r["e"] for r in await db.fetch_all(
        "SELECT DISTINCT lower(recipient_email) AS e FROM email_logs WHERE email_type = 'dates_update' AND status = 'sent'")}
    out, seen = [], set()
    for r in rows:
        em = (r["email"] or "").strip().lower()
        if not em or em in seen:
            continue
        if r["old_days"] is not None and r["old_days"] in FOUR_WEEKS_OK:
            continue
        seen.add(em)
        dates = await doc_dates_status(r["student_id"], r["batch_id"])
        if not dates:
            continue
        out.append({**dict(r), "dates": dates, "already_sent": em in sent})
    return out


async def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--send", action="store_true", help="Actually send (default is a dry run)")
    ap.add_argument("--only", action="append", default=[], help="Limit to these emails (repeatable)")
    args = ap.parse_args()

    await db.connect()
    rows = await candidates()
    if args.only:
        only = {e.strip().lower() for e in args.only}
        rows = [r for r in rows if r["email"].lower() in only]

    todo = [r for r in rows if not r["already_sent"]]
    print(f"{len(rows)} affected, {len(rows) - len(todo)} already emailed, {len(todo)} to send"
          f"{'' if args.send else ' (dry run)'}\n")
    ok = failed = 0
    for r in todo:
        d = r["dates"]
        print(f"  {r['cert_id']}  old {r['old_days']}d  ->  {d['start_date']} .. {d['end_date']}"
              f"  window {d['min_start']}..{d['max_start']}  edit={d['can_edit']}")
        if not args.send:
            continue
        sent = await email_service.send_dates_update(
            first_name=r["first_name"], last_name=r["last_name"], email=r["email"],
            domain=r["domain"] or "web-dev", cert_id=r["cert_id"], dates=d,
            student_id=r["student_id"], batch_id=r["batch_id"],
        )
        ok, failed = ok + bool(sent), failed + (not sent)
        print(f"      -> {'sent' if sent else 'FAILED'}")
        await asyncio.sleep(0.5)  # stay well under the provider's rate limit

    if args.send:
        print(f"\nDone: {ok} sent, {failed} failed")
    await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
