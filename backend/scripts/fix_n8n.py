import sqlite3
import json

conn = sqlite3.connect('backend/data/skillme.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# 1. Add the python batch if it doesn't exist
cursor.execute("SELECT id FROM batches WHERE repo_name = 'python-batch-1'")
batch = cursor.fetchone()
if not batch:
    cursor.execute("""
        INSERT INTO batches (domain, batch_number, repo_name, status, max_students, start_date, end_date)
        VALUES ('python', 1, 'python-batch-1', 'active', 50, '2026-08-01', '2026-08-30')
    """)
    batch_id = cursor.lastrowid
    print(f"Created python batch with id {batch_id}")
else:
    batch_id = batch['id']
    print(f"Found python batch with id {batch_id}")

# 2. Add the student if it doesn't exist
cursor.execute("SELECT id FROM students WHERE github_username = 'n8nsaksham-web'")
student = cursor.fetchone()
if not student:
    cursor.execute("""
        INSERT INTO students (first_name, last_name, email, github_username, domain, status)
        VALUES ('Saksham', 'Verma', 'n8nsaksham-web@example.com', 'n8nsaksham-web', 'python', 'enrolled')
    """)
    student_id = cursor.lastrowid
    print(f"Created student with id {student_id}")
else:
    student_id = student['id']
    print(f"Found student with id {student_id}")

# 3. Add progress
cursor.execute("SELECT id FROM progress WHERE student_id = ? AND batch_id = ? AND week = 1", (student_id, batch_id))
progress = cursor.fetchone()
if not progress:
    cursor.execute("""
        INSERT INTO progress (student_id, batch_id, week, issues_assigned, issues_completed, prs_merged, score)
        VALUES (?, ?, 1, 4, 1, 1, 25)
    """, (student_id, batch_id))
    print("Created progress")
else:
    cursor.execute("""
        UPDATE progress 
        SET issues_completed = 1, prs_merged = 1, score = 25 
        WHERE id = ?
    """, (progress['id'],))
    print("Updated progress")

# 4. Add submission
cursor.execute("SELECT id FROM submissions WHERE student_id = ? AND batch_id = ? AND pr_number = 1", (student_id, batch_id))
submission = cursor.fetchone()
if not submission:
    cursor.execute("""
        INSERT INTO submissions (student_id, batch_id, issue_id, pr_number, pr_url, status)
        VALUES (?, ?, 1, 1, 'https://github.com/sakshamvermaa124-dotcom/python-batch-1/pull/1', 'merged')
    """, (student_id, batch_id))
    print("Created submission")
else:
    cursor.execute("""
        UPDATE submissions SET status = 'merged' WHERE id = ?
    """, (submission['id'],))
    print("Updated submission")

conn.commit()
conn.close()
print("Done.")
