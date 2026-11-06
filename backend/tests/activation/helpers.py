from datetime import datetime, timedelta

from tests.conftest import seed_batch, seed_enrollment, seed_student, test_db


def ts(days_ago=0):
    return (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")


async def enrolled(test_db, email, domain="web-dev", days_ago=2):
    sid = await seed_student(test_db, email=email, domain=domain, status="enrolled")
    bid = await seed_batch(test_db, domain=domain, batch_number=sid)
    await test_db.execute("UPDATE batches SET start_date = ? WHERE id = ?", (ts(days_ago), bid))
    await seed_enrollment(test_db, sid, bid)
    await test_db.execute("UPDATE enrollments SET joined_at = ? WHERE student_id = ?", (ts(days_ago), sid))
    return sid, bid


async def login(test_db, email, days_ago=1):
    await test_db.insert(
        "INSERT INTO otp_tokens (email, otp_hash, expires_at, used, verified_at) VALUES (?, 'x', ?, 1, ?)",
        (email, ts(0), ts(days_ago)),
    )


async def sub(test_db, sid, bid, week, status="approved", days_ago=1):
    await test_db.insert(
        "INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status, submitted_at, reviewed_at) "
        "VALUES (?, ?, ?, 'https://linkedin.com/posts/x', ?, ?, ?)",
        (sid, bid, week, status, ts(days_ago + 1), ts(days_ago)),
    )
