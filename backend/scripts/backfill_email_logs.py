"""
One-time backfill of email_logs from existing DB data.

Infers which emails were sent based on student statuses, enrollments,
and issue assignments — since logging wasn't in place before.
"""
import sqlite3, sys
sys.stdout.reconfigure(encoding="utf-8")

con = sqlite3.connect("data/skillme.db")
con.row_factory = sqlite3.Row

inserted = 0

def insert_log(recipient_email, recipient_name, email_type, subject,
               student_id=None, batch_id=None, sent_at=None):
    global inserted
    # Avoid duplicates
    existing = con.execute(
        "SELECT 1 FROM email_logs WHERE recipient_email=? AND email_type=? AND (batch_id=? OR (batch_id IS NULL AND ? IS NULL))",
        (recipient_email, email_type, batch_id, batch_id)
    ).fetchone()
    if existing:
        return  # skip duplicate
    con.execute(
        """INSERT INTO email_logs
           (recipient_email, recipient_name, email_type, subject, student_id, batch_id, status, sent_at)
           VALUES (?, ?, ?, ?, ?, ?, 'sent', COALESCE(?, CURRENT_TIMESTAMP))""",
        (recipient_email, recipient_name, email_type, subject, student_id, batch_id, sent_at)
    )
    inserted += 1

print()
print("=" * 65)
print("  Email Log Backfill — Reconstructing historical send history")
print("=" * 65)

# ── 1. Application Confirmation — every student that applied ──────────
students = con.execute("SELECT * FROM students ORDER BY created_at").fetchall()
print(f"\n  [1/4] Application Confirmations — {len(students)} students")
for s in students:
    name = f"{s['first_name']} {s['last_name']}"
    insert_log(
        s["email"], name,
        "application_confirmation",
        "✅ We received your SkillMe application!",
        student_id=s["id"],
        sent_at=s["created_at"],
    )
print(f"        → {inserted} records inserted so far")

# ── 2. Shortlisted — students whose status is shortlisted/enrolled/completed
shortlisted = [s for s in students
               if s["status"] in ("shortlisted", "enrolled", "completed")]
print(f"\n  [2/4] Shortlisted Notifications — {len(shortlisted)} students")
before = inserted
for s in shortlisted:
    name = f"{s['first_name']} {s['last_name']}"
    insert_log(
        s["email"], name,
        "shortlisted",
        "🎉 You've been shortlisted for SkillMe!",
        student_id=s["id"],
        sent_at=s["updated_at"] or s["created_at"],
    )
print(f"        → {inserted - before} records inserted")

# ── 3. Offer Letters — every active enrollment ────────────────────────
enrollments = con.execute(
    """SELECT e.*, s.first_name, s.last_name, s.email, s.id as sid,
              b.domain, b.batch_number, b.repo_name, b.id as bid
       FROM enrollments e
       JOIN students s ON s.id = e.student_id
       JOIN batches  b ON b.id = e.batch_id
       WHERE e.status != 'dropped'
       ORDER BY e.joined_at""",
).fetchall()
print(f"\n  [3/4] Offer Letters — {len(enrollments)} enrollments")
before = inserted
for e in enrollments:
    name = f"{e['first_name']} {e['last_name']}"
    domain_label = e["domain"].replace("-", " ").title()
    insert_log(
        e["email"], name,
        "offer_letter",
        f"🚀 Your SkillMe Offer Letter — {domain_label} Batch #{e['batch_number']}",
        student_id=e["sid"],
        batch_id=e["bid"],
        sent_at=e["joined_at"],
    )
print(f"        → {inserted - before} records inserted")

# ── 4. Weekly Task Notifications — infer from issues table ───────────
issues = con.execute(
    """SELECT DISTINCT i.week_number, i.batch_id, e.student_id,
              s.first_name, s.last_name, s.email, s.id as sid,
              b.domain, b.batch_number, i.created_at
       FROM issues i
       JOIN enrollments e ON e.batch_id = i.batch_id AND e.student_id = i.assigned_to
       JOIN students s ON s.id = e.student_id
       JOIN batches  b ON b.id = i.batch_id
       ORDER BY i.created_at""",
).fetchall()
print(f"\n  [4/4] Weekly Task Notifications — {len(issues)} student-week combinations")
before = inserted
for row in issues:
    name = f"{row['first_name']} {row['last_name']}"
    domain_label = row["domain"].replace("-", " ").title()
    insert_log(
        row["email"], name,
        "weekly_tasks",
        f"💻 Week {row['week_number']} Tasks Are Live — SkillMe {domain_label}",
        student_id=row["sid"],
        batch_id=row["batch_id"],
        sent_at=row["created_at"],
    )
print(f"        → {inserted - before} records inserted")

con.commit()

# ── Summary ───────────────────────────────────────────────────────────
total_in_db = con.execute("SELECT COUNT(*) as c FROM email_logs").fetchone()["c"]
by_type = con.execute(
    "SELECT email_type, COUNT(*) as c FROM email_logs GROUP BY email_type ORDER BY c DESC"
).fetchall()

print()
print("=" * 65)
print(f"  DONE — {inserted} new records backfilled")
print(f"  Total email_logs rows now: {total_in_db}")
print()
print(f"  {'Email Type':<30} {'Count':>6}")
print(f"  {'─'*30} {'─'*6}")
for row in by_type:
    print(f"  {row['email_type']:<30} {row['c']:>6}")
print("=" * 65)
print()
print("  Reload the Email Log panel in admin to see these.")
print()
con.close()
