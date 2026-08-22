import asyncio, sys
sys.path.append('backend')
from db.database import db
from services.batch_service import batch_service
from services.github_service import github_service

# Mock the github_service to avoid hitting live GitHub and avoid auth issues
async def mock_create_issue(repo_name, title, body, assignee, labels):
    print(f"[MOCK GITHUB API] Creating issue '{title}' in {repo_name} for {assignee}...")
    return {"number": 999} # Dummy issue number

github_service.create_issue = mock_create_issue

async def main():
    await db.connect()
    
    # Create a fresh TEST batch and student so we don't mess with live data
    batch_id = await db.insert(
        "INSERT INTO batches (batch_number, domain, repo_name, status) VALUES (999, 'python', 'mock-test-repo', 'active')"
    )

    student_id = await db.insert(
        "INSERT INTO students (first_name, last_name, email, domain, status) VALUES ('Test', 'User', 'test_user_safe@skillme.com', 'python', 'enrolled')"
    )
    
    await db.insert(
        "INSERT INTO enrollments (student_id, batch_id, status) VALUES (?, ?, 'enrolled')", (student_id, batch_id)
    )

    print("Assigning week 1 tasks from repo for TEST user...")
    created = await batch_service.assign_week_from_task_repo(batch_id, 1)
    
    print(f"\n--- RESULTS ---")
    print(f"Created {len(created)} issues in database:")
    for iss in created:
        print(f" - Issue ID: {iss['id']}, Title: '{iss['title']}', Github ID: {iss['github_issue_number']}")

    # Clean up test data safely
    await db.execute("DELETE FROM progress WHERE batch_id = ?", (batch_id,))
    await db.execute("DELETE FROM issues WHERE batch_id = ?", (batch_id,))
    await db.execute("DELETE FROM enrollments WHERE batch_id = ?", (batch_id,))
    await db.execute("DELETE FROM batches WHERE id = ?", (batch_id,))
    await db.execute("DELETE FROM students WHERE id = ?", (student_id,))
    print("Test data cleaned up successfully. No live users affected.")
    
    await db.disconnect()

asyncio.run(main())
