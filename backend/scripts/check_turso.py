import asyncio
import sys
from pathlib import Path

# Add backend to path so we can import modules
sys.path.append(str(Path(__file__).parent.parent))

from db.database import db

async def main():
    print("--- Checking Turso DB ---")
    
    # 1. Batches
    batches = await db.fetch_all("SELECT * FROM batches")
    print("Batches:")
    for b in batches:
        print(" -", dict(b))
        
    # 2. Students
    students = await db.fetch_all("SELECT id, email, github_username FROM students")
    print("\nStudents:")
    for s in students:
        print(" -", dict(s))
        
    # 3. Enrollments
    enrollments = await db.fetch_all("SELECT * FROM enrollments")
    print("\nEnrollments:")
    for e in enrollments:
        print(" -", dict(e))

asyncio.run(main())
