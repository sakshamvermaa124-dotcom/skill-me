import sqlite3
import hashlib
import random
import string
from datetime import datetime, timedelta

def _hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()

def _generate_otp() -> str:
    return "".join(random.choices(string.digits, k=6))

def test_otp_flow():
    # Setup test db
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute('''
    CREATE TABLE students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE,
        first_name TEXT,
        last_name TEXT
    )
    ''')
    cursor.execute('''
    CREATE TABLE otp_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        otp_hash TEXT NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        used INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Insert student
    test_email = "test@example.com"
    cursor.execute("INSERT INTO students (email, first_name, last_name) VALUES (?, ?, ?)", (test_email, "Test", "User"))
    student_id = cursor.lastrowid
    conn.commit()

    # --- SIMULATE request_otp ---
    otp = _generate_otp()
    otp_hash = _hash_otp(otp)
    expires_at = (datetime.utcnow() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("UPDATE otp_tokens SET used = 1 WHERE email = ? AND used = 0", (test_email,))
    cursor.execute(
        "INSERT INTO otp_tokens (email, otp_hash, expires_at) VALUES (?, ?, ?)",
        (test_email, otp_hash, expires_at)
    )
    conn.commit()
    print(f"Requested OTP: {otp}")

    # --- SIMULATE verify_otp ---
    cursor.execute(
        """SELECT id, expires_at FROM otp_tokens
           WHERE email = ? AND otp_hash = ? AND used = 0
           ORDER BY created_at DESC LIMIT 1""",
        (test_email, otp_hash)
    )
    token_row = cursor.fetchone()
    
    if not token_row:
        print("OTP token not found or already used.")
        return False
        
    try:
        expires_at_dt = datetime.strptime(token_row["expires_at"], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        expires_at_dt = datetime.strptime(token_row["expires_at"], "%Y-%m-%dT%H:%M:%S")

    if datetime.utcnow() > expires_at_dt:
        print("OTP token expired.")
        return False

    cursor.execute("UPDATE otp_tokens SET used = 1 WHERE id = ?", (token_row["id"],))
    conn.commit()

    cursor.execute("SELECT id, email FROM students WHERE email = ?", (test_email,))
    student = cursor.fetchone()
    if not student:
        print("Student not found.")
        return False

    print("OTP verified successfully!")
    
    # Check if it was marked as used
    cursor.execute("SELECT used FROM otp_tokens WHERE id = ?", (token_row["id"],))
    used = cursor.fetchone()[0]
    print(f"Token used status in DB: {used}")
    
    return True

if __name__ == "__main__":
    success = test_otp_flow()
    print(f"Test {'passed' if success else 'failed'}")
