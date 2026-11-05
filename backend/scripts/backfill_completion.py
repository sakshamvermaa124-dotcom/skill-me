"""
Record completion that already happened. Analytics derives completion from approvals either way;
this only makes the stored enrollment status agree with records that already exist.

  python scripts/backfill_completion.py            # dry run
  python scripts/backfill_completion.py --apply

Rule (same as services/submission_service._sync_completion): an enrollment whose student has all 4
distinct weeks approved is set to status='completed', completed_at = the last approval's reviewed_at.
Only rows currently 'enrolled'/'active' are touched; dropped enrollments are never changed, and no
value is invented (completed_at always comes from an existing reviewed_at).
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.database import db   # noqa: E402


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    rows = await db.fetch_all(
        """SELECT e.id AS enrollment_id, e.student_id, e.batch_id, e.status,
                  datetime(MAX(x.reviewed_at)) AS last_review, COUNT(DISTINCT x.week) AS weeks
           FROM enrollments e JOIN submissions x
             ON x.student_id = e.student_id AND x.batch_id = e.batch_id AND x.status = 'approved'
           WHERE e.status IN ('enrolled', 'active')
           GROUP BY e.id HAVING COUNT(DISTINCT x.week) >= 4""")
    print(f"{'APPLYING' if args.apply else 'DRY RUN'}: {len(rows)} enrollment(s) -> completed")
    for r in rows:
        print(f"  enrollment #{r['enrollment_id']} student #{r['student_id']} {r['status']} -> completed at {r['last_review']}")
        if args.apply:
            await db.execute(
                "UPDATE enrollments SET status = 'completed', completed_at = ? WHERE id = ? AND status IN ('enrolled','active')",
                (r["last_review"], r["enrollment_id"]))
    if not args.apply and rows:
        print("\nRe-run with --apply to write.")


if __name__ == "__main__":
    asyncio.run(main())
