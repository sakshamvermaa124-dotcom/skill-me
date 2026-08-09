import sys
import os
import asyncio
from unittest.mock import patch
from fastapi.testclient import TestClient

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import app
from db.database import db
from services.auth_service import _generate_otp, _hash_otp

client = TestClient(app)

async def check_otp():
    print("Connecting to DB...")
    await db.connect()
    
    # 1. Create a dummy student
    email = "otp_test_user@example.com"
    await db.execute("DELETE FROM students WHERE email = ?", (email,))
    await db.execute("DELETE FROM otp_tokens WHERE email = ?", (email,))
    await db.execute(
        """
        INSERT INTO students (id, first_name, last_name, email, github_username, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        ("test_id_123", "Test", "User", email, "testuser", "ACTIVE")
    )
    print("Dummy student created.")

    # 2. Patch email service so we can capture the OTP from the HTML body
    sent_otp = None
    original_send = app.dependency_overrides.get("email_service._send_and_log") 
    
    # Actually, let's just patch _generate_otp to return a fixed OTP
    fixed_otp = "123456"
    
    with patch('routes.auth.request_otp') as mock_request:
        from services.auth_service import request_otp as original_request_otp
        
        async def patched_request_otp(email_str):
            result = await original_request_otp(email_str)
            # Patch the returned OTP in the result
            nonlocal sent_otp
            sent_otp = result['otp']
            return result
            
        # Instead of patching request_otp which might be hard due to imports, let's patch _generate_otp
    
    print("Requesting OTP...")
    
    with patch('services.auth_service._generate_otp', return_value="123456"):
        resp = client.post("/api/auth/request-otp", json={"email": email})
        print(f"Request OTP response: {resp.status_code}")
        print(resp.json())
        
        # Verify the OTP
        print("Verifying OTP...")
        verify_resp = client.post("/api/auth/verify-otp", json={"email": email, "otp": "123456"})
        print(f"Verify OTP response: {verify_resp.status_code}")
        print(verify_resp.json())
        
        # Try invalid OTP
        print("Verifying INVALID OTP...")
        invalid_resp = client.post("/api/auth/verify-otp", json={"email": email, "otp": "999999"})
        print(f"Invalid OTP response: {invalid_resp.status_code}")
        print(invalid_resp.json())

    # Cleanup
    await db.execute("DELETE FROM students WHERE email = ?", (email,))
    await db.execute("DELETE FROM otp_tokens WHERE email = ?", (email,))
    print("Cleanup done.")
    
if __name__ == "__main__":
    asyncio.run(check_otp())
