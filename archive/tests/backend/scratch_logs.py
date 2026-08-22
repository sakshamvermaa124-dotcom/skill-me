import asyncio
import os
import sys

sys.path.insert(0, r"c:\Users\saksh\Desktop\skill-me\backend")
from db.database import db

async def check_email_logs():
    await db.connect()
    
    rows = await db.fetch_all("""
        SELECT student_id, type, sent_at
        FROM email_logs
        WHERE type = 'github_invite_reminder'
        ORDER BY sent_at DESC
        LIMIT 20
    """)
    
    print(f"{'Student ID':<15} | {'Type':<30} | {'Sent At'}")
    print("-" * 70)
    for r in rows:
        print(f"{r['student_id']:<15} | {r['type']:<30} | {r['sent_at']}")
        
    await db.disconnect()

asyncio.run(check_email_logs())
