"""
One-time migration: remove the GitHub PR submission system and switch to
LinkedIn-URL + admin-approval submissions.

Run once against the existing production DB before deploying the new backend:
    python backend/scripts/migrate_remove_github.py

Safe to re-run — every step checks whether it already applied.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.database import db


async def _columns(table: str) -> set[str]:
    rows = await db.fetch_all(f"PRAGMA table_info({table})")
    return {r["name"] for r in rows}


async def migrate():
    await db.connect()

    # ── submissions: rebuild with the new shape ────────────────────────────
    sub_cols = await _columns("submissions")
    if "linkedin_url" not in sub_cols:
        print("Migrating submissions table...")
        await db.execute("ALTER TABLE submissions RENAME TO submissions_old")
        await db.execute(
            """CREATE TABLE submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                batch_id INTEGER NOT NULL,
                week INTEGER NOT NULL,
                linkedin_url TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                admin_note TEXT,
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reviewed_at TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students(id),
                FOREIGN KEY (batch_id) REFERENCES batches(id),
                UNIQUE(student_id, batch_id, week)
            )"""
        )
        # Old PR-based submissions have no LinkedIn URL equivalent — dropped, not carried over.
        await db.execute("DROP TABLE submissions_old")
        print("  done (old PR submissions were not migratable — table recreated empty).")
    else:
        print("submissions table already migrated, skipping.")

    # ── progress: drop prs_submitted / prs_merged ──────────────────────────
    prog_cols = await _columns("progress")
    if "prs_merged" in prog_cols:
        print("Migrating progress table...")
        await db.execute("ALTER TABLE progress RENAME TO progress_old")
        await db.execute(
            """CREATE TABLE progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                batch_id INTEGER NOT NULL,
                week INTEGER NOT NULL,
                issues_completed INTEGER DEFAULT 0,
                score INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students(id),
                FOREIGN KEY (batch_id) REFERENCES batches(id),
                UNIQUE(student_id, batch_id, week)
            )"""
        )
        await db.execute(
            """INSERT INTO progress (id, student_id, batch_id, week, issues_completed, score, updated_at)
               SELECT id, student_id, batch_id, week, issues_completed, score, updated_at FROM progress_old"""
        )
        await db.execute("DROP TABLE progress_old")
        print("  done.")
    else:
        print("progress table already migrated, skipping.")

    # ── enrollments: drop github_invite_status ─────────────────────────────
    enr_cols = await _columns("enrollments")
    if "github_invite_status" in enr_cols:
        print("Migrating enrollments table...")
        await db.execute("ALTER TABLE enrollments DROP COLUMN github_invite_status")
        print("  done.")
    else:
        print("enrollments table already migrated, skipping.")

    # ── batches: drop repo_name / auto_assign / weeks_assigned ─────────────
    batch_cols = await _columns("batches")
    if "repo_name" in batch_cols:
        print("Migrating batches table...")
        for col in ("repo_name", "auto_assign", "weeks_assigned"):
            if col in batch_cols:
                await db.execute(f"ALTER TABLE batches DROP COLUMN {col}")
        print("  done.")
    else:
        print("batches table already migrated, skipping.")

    # ── issues: no longer used, drop entirely ──────────────────────────────
    existing_tables = {r["name"] for r in await db.fetch_all(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    if "issues" in existing_tables:
        print("Dropping issues table...")
        await db.execute("DROP TABLE issues")
        print("  done.")
    else:
        print("issues table already dropped, skipping.")

    await db.disconnect()
    print("Migration complete.")


if __name__ == "__main__":
    asyncio.run(migrate())
