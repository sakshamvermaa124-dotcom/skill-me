import asyncio
import sys
sys.path.append('backend')
from db.database import db

async def main():
    await db.connect()
    student_res = await db.fetch_all("SELECT * FROM students WHERE lower(first_name) LIKE '%bunty%'")
    if not student_res:
        print("No bunty found")
        await db.disconnect()
        return
    student = student_res[0]
    print("Student:", dict(student))
    enrollments = await db.fetch_all("SELECT * FROM enrollments WHERE student_id = :id", {"id": student["id"]})
    print("Enrollments:", [dict(e) for e in enrollments])
    await db.disconnect()

asyncio.run(main())
