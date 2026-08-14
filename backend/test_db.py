import asyncio
from db.database import db
async def check():
    await db.connect()
    s = await db.fetch_all('SELECT id, github_username, email FROM students;')
    print('Students:', s)
    subs = await db.fetch_all('SELECT * FROM submissions;')
    print('Submissions:', subs)
asyncio.run(check())
