"""
Flag confirmed internal test payments as is_test=1. NOTHING IS DELETED OR EDITED except that flag.

  python scripts/flag_test_records.py                 # dry run: prints what would change
  python scripts/flag_test_records.py --apply         # writes the flag

Confirmed by the business: the Rs.5 payments (amount 500 paise, the hard-coded BLACKYY code) were internal
tests. A payment is only flagged if it matches ALL of: status 'paid', amount == 500, not already flagged.
Pass explicit --ids to restrict the set. The linked STUDENT accounts are listed but never flagged here;
review them in Admin > Analytics > Data Quality ("mark as test") or via PATCH /api/admin/students/{id}/test-flag.
Run it after the app has been deployed once (the migration adds the is_test column).
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.database import db   # noqa: E402

TEST_AMOUNT_PAISE = 500


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ids", type=int, nargs="*", help="restrict to these payments.id values")
    args = ap.parse_args()

    rows = await db.fetch_all(
        """SELECT p.id, p.student_id, p.razorpay_payment_id, p.amount, p.created_at,
                  s.first_name || ' ' || s.last_name AS name, s.email,
                  (SELECT COUNT(DISTINCT week) FROM submissions x WHERE x.student_id = p.student_id AND x.status = 'approved') AS weeks
           FROM payments p JOIN students s ON s.id = p.student_id
           WHERE p.status = 'paid' AND p.amount = ? AND COALESCE(p.is_test, 0) = 0 ORDER BY p.id""",
        (TEST_AMOUNT_PAISE,))
    if args.ids:
        rows = [r for r in rows if r["id"] in set(args.ids)]
    if not rows:
        print("Nothing to flag.")
        return
    print(f"{'APPLYING' if args.apply else 'DRY RUN'}: {len(rows)} payment(s) -> is_test = 1")
    for r in rows:
        print(f"  payment #{r['id']:<4} {r['razorpay_payment_id']:<24} Rs.{r['amount'] / 100:<6g} "
              f"student #{r['student_id']:<4} {r['name']} <{r['email']}>  approved weeks: {r['weeks']}  {r['created_at']}")
    if not args.apply:
        print("\nRe-run with --apply to write. Student accounts are NOT flagged by this script.")
        return
    for r in rows:
        await db.execute("UPDATE payments SET is_test = 1 WHERE id = ? AND status = 'paid' AND amount = ?",
                         (r["id"], TEST_AMOUNT_PAISE))
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
