"""
Read-only reconciliation of the analytics definitions against the raw tables.

  python scripts/analytics_reconcile.py             # snapshot mode (default, never writes to the source DB)
  python scripts/analytics_reconcile.py --direct    # query the configured DB as-is (needs the migrated schema)

Snapshot mode copies every table from the configured database (TURSO_DB_URL / local file) into a
temporary SQLite file, applies db/schema.sql + Database._migrations() to THAT COPY, and runs the
analytics service on it. So you can see the corrected numbers before deploying and before running any
flag/backfill script. Pass --flag-confirmed-tests to also simulate scripts/flag_test_records.py on the copy.
"""
import argparse
import asyncio
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import Database, db as source_db   # noqa: E402
from services import analytics_service as A          # noqa: E402

CONFIRMED_TEST_AMOUNT = 500


async def snapshot() -> Database:
    tables = [r["name"] for r in await source_db.fetch_all(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
    path = os.path.join(tempfile.mkdtemp(prefix="skillme_snapshot_"), "snapshot.db")
    local = Database(path, "")
    await local.connect()                              # schema.sql + migrations on the COPY
    conn = sqlite3.connect(path)
    for t in tables:
        rows = await source_db.fetch_all(f"SELECT * FROM {t}")
        if not rows:
            continue
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({t})")}
        if not have:
            continue
        cols = [c for c in rows[0] if c in have]
        conn.executemany(
            f"INSERT OR IGNORE INTO {t} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
            [tuple(r[c] for c in cols) for r in rows])
    conn.commit()
    conn.close()
    print(f"[snapshot] {len(tables)} tables copied to {path}")
    return local


def line(label, value, raw=None):
    extra = f"   (raw: {raw})" if raw is not None else ""
    print(f"  {label:<46}{value}{extra}")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--direct", action="store_true")
    ap.add_argument("--flag-confirmed-tests", action="store_true",
                    help=f"on the snapshot only: flag paid Rs.{CONFIRMED_TEST_AMOUNT // 100} payments as test")
    args = ap.parse_args()

    db = source_db if args.direct else await snapshot()
    if args.flag_confirmed_tests and not args.direct:
        await db.execute("UPDATE payments SET is_test = 1 WHERE status = 'paid' AND amount = ?", (CONFIRMED_TEST_AMOUNT,))

    raw = await A.load_raw(db)
    students_all = A.build_students(raw)
    d = A.compute(raw, students_all, {"date_from": None, "date_to": None, "domain": None, "source": None,
                                      "campaign": None, "include_test": False})
    q = db.fetch_one

    print("\n== Counts: dashboard definition vs raw table ==")
    o = d["overview"]
    line("Applicants (non-test students)", o["applicants"], (await q("SELECT COUNT(*) n FROM students"))["n"])
    line("Unique people", o["unique_people"], (await q("SELECT COUNT(DISTINCT lower(email)) n FROM students"))["n"])
    line("Enrolled students", o["enrolled"], (await q("SELECT COUNT(DISTINCT student_id) n FROM enrollments"))["n"])
    line("Completed (4/4 approved weeks)", o["completed"], (await q(
        "SELECT COUNT(*) n FROM (SELECT student_id FROM submissions WHERE status='approved' GROUP BY student_id HAVING COUNT(DISTINCT week)>=4)"))["n"])
    line("Certificates issued", o["certificates"], (await q("SELECT COUNT(DISTINCT student_id) n FROM certificates"))["n"])
    line("Paying students (real payments)", o["paying_students"], (await q(
        "SELECT COUNT(DISTINCT student_id) n FROM payments WHERE status='paid'"))["n"])
    line("Revenue (Rs, real)", o["revenue_rupees"], (await q("SELECT SUM(amount)/100.0 n FROM payments WHERE status='paid'"))["n"])
    line("Eligible but unpaid", o["eligible_unpaid"])
    t = d["engagement"]["task_level"]
    line("Approved SUBMISSIONS (task-level, not students)", t["approved_submissions"],
         (await q("SELECT COUNT(*) n FROM submissions WHERE status='approved'"))["n"])

    print("\n== Learning funnel ==")
    for r in d["funnel"]["learning"]:
        line(r["label"], f"{r['count']:>4}  step {r['step_conversion']}%  drop {r['drop_off']} ({r['drop_off_pct']}%)")
    print("\n== Revenue funnel ==")
    for r in d["funnel"]["revenue"]:
        line(r["label"], f"{r['count']:>4}  step {r['step_conversion']}%")
    print("\n== Timings (median / p90 days) ==")
    for x in d["funnel"]["timings"]:
        line(f"{x['from']} -> {x['to']}", f"{x['median_days']} / {x['p90_days']}  (n={x['n']})")
    print("\n== Payments lifecycle ==")
    for k, v in d["payments"]["lifecycle"].items():
        line(k, v)
    line("excluded test payments", d["payments"]["excluded_test"])
    print("\n== Acquisition coverage ==")
    line("coverage", d["acquisition"]["coverage"])
    print("\n== Domains (applications / completed / certified / paid) ==")
    for x in d["domains"]:
        line(x["label"], f"{x['applications']} / {x['completed']} / {x['certified']} / {x['paid']}"
             f"   certified-not-completed={x['certified_not_completed']}")
    print("\n== Validation warnings ==")
    for w in d["validation"]:
        print(f"  [{w['level']}] {w['code']}: {w['message']}")
    dq = await A.data_quality(db, students_all)
    print("\n== Data quality ==")
    for c in dq["checks"]:
        line(c["label"], f"{c['severity']} ({c['count']})")


if __name__ == "__main__":
    asyncio.run(main())
