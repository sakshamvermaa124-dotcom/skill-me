import asyncio, sys
sys.path.insert(0, ".")
from db.database import db

async def run_migration():
    await db.connect()
    res = await db.fetch_all("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r["name"] for r in res]
    print(f"Tables in DB: {tables}")
    if "email_logs" in tables:
        print("email_logs table exists.")
    else:
        print("email_logs table DOES NOT exist.")
    await db.disconnect()

asyncio.run(run_migration())
