"""
One-off migration: allow one application per (email, track) instead of one per email.

SQLite can't drop the column-level UNIQUE on students.email, so the table is rebuilt with
SQLite's documented procedure (create new table → copy rows → drop old → rename), then a
UNIQUE index on (lower(email), domain) is added. Student ids are preserved, so every
foreign key (enrollments, submissions, payments, certificates, ...) keeps pointing at the
same rows.

Dry run by default — nothing is written until you pass --apply.

    # local SQLite file (a copy is made next to it first)
    python backend/scripts/migrate_multi_domain.py --local backend/local.db
    python backend/scripts/migrate_multi_domain.py --local backend/local.db --apply

    # Turso (reads TURSO_DB_URL / TURSO_AUTH_TOKEN from the environment)
    python backend/scripts/migrate_multi_domain.py
    python backend/scripts/migrate_multi_domain.py --apply

Before --apply on Turso, take a backup too (e.g. `turso db shell <db> .dump > backup.sql`).
The script also writes students-backup-<time>.json with every students row.
"""
import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime

INDEX_SQL = "CREATE UNIQUE INDEX IF NOT EXISTS ux_students_email_domain ON students(lower(email), domain)"
EMAIL_UNIQUE = re.compile(r"(\bemail\s+TEXT\s+NOT\s+NULL)\s+UNIQUE\b", re.IGNORECASE)


# ── database access: local sqlite3 or Turso over HTTP ────────────────────────

class Local:
    def __init__(self, path):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row

    def query(self, sql, args=()):
        return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def run_atomic(self, statements):
        self.conn.execute("PRAGMA foreign_keys = OFF")
        try:
            self.conn.execute("BEGIN")
            for stmt in statements:
                self.conn.execute(stmt)
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        finally:
            self.conn.execute("PRAGMA foreign_keys = ON")


class Turso:
    def __init__(self, url, token):
        import httpx
        self.httpx = httpx
        url = url.replace("libsql://", "https://")
        self.endpoint = url.rstrip("/") + "/v2/pipeline"
        self.headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    @staticmethod
    def _val(v):
        if not isinstance(v, dict) or v.get("value") is None:
            return None if isinstance(v, dict) else v
        return int(v["value"]) if v.get("type") == "integer" else v["value"]

    def _post(self, requests):
        res = self.httpx.post(self.endpoint, headers=self.headers, json={"requests": requests + [{"type": "close"}]}, timeout=60)
        res.raise_for_status()
        return res.json()["results"]

    def query(self, sql, args=()):
        stmt = {"sql": sql, "args": [{"type": "text", "value": str(a)} for a in args]}
        result = self._post([{"type": "execute", "stmt": stmt}])[0]
        if result.get("type") == "error":
            raise RuntimeError(result["error"]["message"])
        r = result["response"]["result"]
        cols = [c["name"] for c in r["cols"]]
        return [dict(zip(cols, [self._val(v) for v in row])) for row in r["rows"]]

    def run_atomic(self, statements):
        # One Hrana batch: each step runs only if the previous one succeeded; if anything
        # fails, the last step rolls the transaction back.
        steps = [{"stmt": {"sql": "BEGIN"}}]
        for stmt in statements:
            steps.append({"stmt": {"sql": stmt}, "condition": {"type": "ok", "step": len(steps) - 1}})
        steps.append({"stmt": {"sql": "COMMIT"}, "condition": {"type": "ok", "step": len(steps) - 1}})
        commit_step = len(steps) - 1
        steps.append({"stmt": {"sql": "ROLLBACK"}, "condition": {"type": "not", "cond": {"type": "ok", "step": commit_step}}})
        results = self._post([
            {"type": "execute", "stmt": {"sql": "PRAGMA foreign_keys = OFF"}},
            {"type": "batch", "batch": {"steps": steps}},
            {"type": "execute", "stmt": {"sql": "PRAGMA foreign_keys = ON"}},
        ])
        batch = results[1]
        if batch.get("type") == "error":
            raise RuntimeError(batch["error"]["message"])
        errors = [e for e in batch["response"]["result"]["step_errors"] if e]
        committed = batch["response"]["result"]["step_results"][commit_step] is not None
        if errors or not committed:
            raise RuntimeError(f"Migration rolled back: {errors[0]['message'] if errors else 'commit did not run'}")


# ── migration ────────────────────────────────────────────────────────────────

def plan(db):
    table = db.query("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'students'")
    if not table:
        sys.exit("No students table found.")
    create_sql = table[0]["sql"]
    if not EMAIL_UNIQUE.search(create_sql):
        return None, create_sql
    new_sql = EMAIL_UNIQUE.sub(r"\1", create_sql)
    new_sql = re.sub(r"^CREATE TABLE\s+(IF NOT EXISTS\s+)?\"?students\"?", "CREATE TABLE students_new", new_sql, count=1, flags=re.IGNORECASE)
    indexes = [r["sql"] for r in db.query(
        "SELECT sql FROM sqlite_master WHERE type = 'index' AND tbl_name = 'students' AND sql IS NOT NULL")]
    dependents = db.query(
        "SELECT type, name FROM sqlite_master WHERE type IN ('trigger', 'view') AND sql LIKE '%students%'")
    if dependents:
        sys.exit(f"Triggers/views reference students, migrate them by hand first: {dependents}")
    statements = [
        new_sql,
        "INSERT INTO students_new SELECT * FROM students",
        "DROP TABLE students",
        "ALTER TABLE students_new RENAME TO students",
        *[re.sub(r"CREATE (UNIQUE )?INDEX (?!IF NOT EXISTS)", r"CREATE \1INDEX IF NOT EXISTS ", s) for s in indexes],
        INDEX_SQL,
    ]
    return statements, create_sql


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--local", help="path to a local SQLite database instead of Turso")
    ap.add_argument("--apply", action="store_true", help="actually run the migration (default: dry run)")
    args = ap.parse_args()

    if args.local:
        if args.apply:
            backup = f"{args.local}.before-multi-domain-{datetime.now():%Y%m%d%H%M%S}"
            shutil.copy2(args.local, backup)
            print(f"Copied database to {backup}")
        db = Local(args.local)
        where = args.local
    else:
        url, token = os.environ.get("TURSO_DB_URL"), os.environ.get("TURSO_AUTH_TOKEN")
        if not url or not token or not url.startswith(("libsql://", "https://")):
            sys.exit("Set TURSO_DB_URL (libsql://...) and TURSO_AUTH_TOKEN, or pass --local PATH.")
        db = Turso(url, token)
        where = url

    print(f"Database: {where}")
    count_before = db.query("SELECT COUNT(*) AS n FROM students")[0]["n"]
    print(f"Students rows: {count_before}")

    statements, create_sql = plan(db)
    if statements is None:
        print("students.email is already free of UNIQUE: nothing to rebuild.")
        if args.apply:
            db.run_atomic([INDEX_SQL])
            print("Ensured index ux_students_email_domain exists.")
        return

    clashes = db.query(
        "SELECT lower(email) AS email, domain, COUNT(*) AS n FROM students "
        "GROUP BY lower(email), domain HAVING COUNT(*) > 1")
    if clashes:
        sys.exit(f"These (email, track) pairs appear more than once (emails that differ only by case). "
                 f"Merge or remove them before migrating:\n{json.dumps(clashes, indent=2)}")

    print("\nCurrent table:\n" + create_sql)
    print("\nWill run, in one transaction:")
    for s in statements:
        print("  " + " ".join(s.split())[:150])

    if not args.apply:
        print("\nDry run only. Re-run with --apply to migrate.")
        return

    rows = db.query("SELECT * FROM students")
    backup_json = f"students-backup-{datetime.now():%Y%m%d%H%M%S}.json"
    with open(backup_json, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1, default=str)
    print(f"\nWrote {len(rows)} rows to {backup_json}")

    db.run_atomic(statements)

    count_after = db.query("SELECT COUNT(*) AS n FROM students")[0]["n"]
    new_sql = db.query("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'students'")[0]["sql"]
    index = db.query("SELECT name FROM sqlite_master WHERE type = 'index' AND name = 'ux_students_email_domain'")
    fk_problems = db.query("PRAGMA foreign_key_check")
    ok = count_after == count_before and not EMAIL_UNIQUE.search(new_sql) and index and not fk_problems
    print(f"Rows after: {count_after} (before {count_before})")
    print(f"UNIQUE(email) removed: {not EMAIL_UNIQUE.search(new_sql)}; per-track index present: {bool(index)}")
    print(f"Foreign key problems: {fk_problems or 'none'}")
    print("Migration complete." if ok else "CHECK THE OUTPUT ABOVE: something does not look right.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
