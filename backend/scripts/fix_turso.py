import asyncio
import sys
from pathlib import Path

# Add backend to path so we can import modules
sys.path.append(str(Path(__file__).parent.parent))

from config import settings
from db.database import db

async def fix_turso():
    print(f"Connecting to {settings.turso_db_url}...")
    
    # 1. Update the email and github username and domain for n8nsaksham-web to n8n.saksham@gmail.com
    # Wait, the user applied previously with bsaksham191? No, they probably didn't.
    # First, let's just create a completely clean student for n8n.saksham@gmail.com
    
    # Check if student exists
    student = await db.fetch_one("SELECT id FROM students WHERE github_username = 'n8nsaksham-web'")
    if not student:
        print("Creating student...")
        student_id = await db.insert(
            """INSERT INTO students (first_name, last_name, email, github_username, domain, status)
               VALUES ('Saksham', 'Verma', 'n8n.saksham@gmail.com', 'n8nsaksham-web', 'python', 'enrolled')"""
        )
    else:
        print(f"Student exists with ID {student['id']}, updating email to n8n.saksham@gmail.com")
        student_id = student['id']
        await db.execute("UPDATE students SET email = 'n8n.saksham@gmail.com', status = 'enrolled', domain = 'python' WHERE id = ?", (student_id,))
        
    # 2. Check if python-batch-1 exists
    batch = await db.fetch_one("SELECT id FROM batches WHERE repo_name = 'python-batch-1'")
    if not batch:
        print("Creating python batch...")
        batch_id = await db.insert(
            """INSERT INTO batches (domain, batch_number, repo_name, status, max_students)
               VALUES ('python', 1, 'python-batch-1', 'active', 30)"""
        )
    else:
        print(f"Batch exists with ID {batch['id']}")
        batch_id = batch['id']
        
    # 3. Create Enrollment
    enrollment = await db.fetch_one("SELECT id FROM enrollments WHERE student_id = ? AND batch_id = ?", (student_id, batch_id))
    if not enrollment:
        print("Creating enrollment...")
        await db.insert(
            """INSERT INTO enrollments (student_id, batch_id, status)
               VALUES (?, ?, 'active')""",
            (student_id, batch_id)
        )
    else:
        print("Enrollment exists")
        
    # 4. Create Progress
    progress = await db.fetch_one("SELECT id FROM progress WHERE student_id = ? AND batch_id = ? AND week = 1", (student_id, batch_id))
    if not progress:
        print("Creating progress...")
        await db.insert(
            """INSERT INTO progress (student_id, batch_id, week, issues_assigned, issues_completed, prs_merged, score)
               VALUES (?, ?, 1, 4, 1, 1, 25)""",
            (student_id, batch_id)
        )
    else:
        print("Progress exists, updating...")
        await db.execute(
            """UPDATE progress SET issues_assigned = 4, issues_completed = 1, prs_merged = 1, score = 25 
               WHERE id = ?""",
            (progress['id'],)
        )
        
    # 5. Create Submission
    sub = await db.fetch_one("SELECT id FROM submissions WHERE student_id = ? AND batch_id = ? AND pr_number = 1", (student_id, batch_id))
    if not sub:
        print("Creating submission...")
        await db.insert(
            """INSERT INTO submissions (student_id, batch_id, issue_id, pr_number, pr_url, status)
               VALUES (?, ?, 1, 1, 'https://github.com/sakshamvermaa124-dotcom/python-batch-1/pull/1', 'merged')""",
            (student_id, batch_id)
        )
    else:
        print("Submission exists")
        
    print("Fix complete.")

asyncio.run(fix_turso())
