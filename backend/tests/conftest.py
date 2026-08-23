"""
SkillMe Test Suite — conftest.py
====================================
Shared fixtures for all tests.

KEY DESIGN DECISIONS:
- All tests run against an IN-MEMORY SQLite database.
  The production Turso DB is NEVER touched.
- GitHub API, Razorpay, and SMTP are all mocked.
- The FastAPI app is tested via httpx.AsyncClient with ASGITransport —
  no live server needed.
- Each test function gets a fresh DB state via the `client` fixture.
"""

import hashlib
import sqlite3
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
import httpx

# ── Make the backend package importable ──────────────────────────────────────
BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Set env overrides BEFORE importing any app modules so Settings picks them up
os.environ.setdefault("TURSO_DB_URL", ":memory:")
os.environ.setdefault("TURSO_AUTH_TOKEN", "")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-tests")
os.environ.setdefault("SKILLME_GITHUB_TOKEN", "")
os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test_key")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "test_secret")
os.environ.setdefault("EMAIL_ENABLED", "False")
os.environ.setdefault("SMTP_FROM_EMAIL", "test@skillme.test")
os.environ.setdefault("FRONTEND_URL", "http://localhost")
os.environ.setdefault("CERTIFICATE_PRICE_PAISE", "9900")

# ── Now import app components (env is already set) ───────────────────────────
from config import settings
from db.database import Database
from main import app

# Patch the settings object directly so tests use test values
settings.admin_api_key = "test-admin-key"
settings.jwt_secret_key = "test-jwt-secret-key-for-tests"
settings.email_enabled = False
settings.razorpay_key_id = "rzp_test_key"
settings.razorpay_key_secret = "test_secret"
settings.certificate_price_paise = 9900
settings.backend_url = "http://test.local"


# ── Test Database Helpers ─────────────────────────────────────────────────────

SCHEMA_PATH = BACKEND_DIR / "db" / "schema.sql"


def _create_test_db() -> sqlite3.Connection:
    """Create a fresh in-memory SQLite DB with the full schema applied."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    statements = [s.strip() for s in schema_sql.split(";") if s.strip()]
    for stmt in statements:
        conn.execute(stmt)
    conn.commit()
    return conn


class TestDatabase:
    """
    Drop-in replacement for db.database.Database that uses an in-memory
    SQLite connection. All methods are async-compatible but synchronous
    internally (SQLite is sync).
    """

    def __init__(self):
        self._conn: sqlite3.Connection | None = None

    def reset(self):
        """Drop all data and re-apply schema for a fresh test state."""
        if self._conn:
            self._conn.close()
        self._conn = _create_test_db()

    async def connect(self):
        self.reset()

    async def disconnect(self):
        pass

    def _execute_sql(self, query: str, params: tuple = ()):
        cursor = self._conn.execute(query, params)
        self._conn.commit()
        return cursor

    async def execute(self, query: str, params: tuple = ()):
        self._execute_sql(query, params)

    async def fetch_one(self, query: str, params: tuple = ()) -> dict | None:
        cursor = self._conn.execute(query, params)
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    async def fetch_all(self, query: str, params: tuple = ()) -> list[dict]:
        cursor = self._conn.execute(query, params)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

    async def insert(self, query: str, params: tuple = ()) -> int:
        cursor = self._execute_sql(query, params)
        return cursor.lastrowid


# ── Global test DB instance ───────────────────────────────────────────────────

test_db = TestDatabase()


# ── Seed Data Helpers ─────────────────────────────────────────────────────────

async def seed_student(
    db: TestDatabase,
    email: str = "test@example.com",
    first_name: str = "Test",
    last_name: str = "Student",
    github_username: str = "testuser",
    domain: str = "web-dev",
    status: str = "applied",
) -> int:
    """Insert and return the ID of a test student."""
    return await db.insert(
        """INSERT INTO students
           (first_name, last_name, email, github_username, domain, status)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (first_name, last_name, email, github_username, domain, status),
    )


async def seed_batch(
    db: TestDatabase,
    domain: str = "web-dev",
    batch_number: int = 1,
    status: str = "active",
) -> int:
    """Insert and return the ID of a test batch."""
    return await db.insert(
        """INSERT INTO batches (domain, batch_number, status)
           VALUES (?, ?, ?)""",
        (domain, batch_number, status),
    )


async def seed_enrollment(db: TestDatabase, student_id: int, batch_id: int) -> int:
    return await db.insert(
        "INSERT INTO enrollments (student_id, batch_id, status) VALUES (?, ?, 'enrolled')",
        (student_id, batch_id),
    )


async def seed_payment(
    db: TestDatabase,
    student_id: int,
    batch_id: int,
    status: str = "paid",
    amount: int = 9900,
) -> int:
    return await db.insert(
        """INSERT INTO payments (student_id, batch_id, razorpay_order_id, amount, status)
           VALUES (?, ?, ?, ?, ?)""",
        (student_id, batch_id, f"order_test_{student_id}_{batch_id}", amount, status),
    )


async def seed_certificate(
    db: TestDatabase,
    student_id: int,
    batch_id: int,
    cert_id: str = "SM-TEST-CERT-0001",
) -> int:
    return await db.insert(
        "INSERT INTO certificates (student_id, batch_id, cert_id) VALUES (?, ?, ?)",
        (student_id, batch_id, cert_id),
    )


async def seed_otp(
    db: TestDatabase,
    email: str,
    otp: str = "123456",
    expired: bool = False,
) -> None:
    otp_hash = hashlib.sha256(otp.encode()).hexdigest()
    if expired:
        expires_at = (datetime.utcnow() - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    else:
        expires_at = (datetime.utcnow() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    await db.insert(
        "INSERT INTO otp_tokens (email, otp_hash, expires_at) VALUES (?, ?, ?)",
        (email, otp_hash, expires_at),
    )


def make_jwt(student_id: int, email: str) -> str:
    """Generate a real JWT using the test secret key."""
    from services.auth_service import _create_jwt
    return _create_jwt(student_id, email)


# ── Mock External Services ────────────────────────────────────────────────────

def mock_email_service():
    """Return a mock that swallows all email sends."""
    mock = MagicMock()
    mock.send_application_confirmation = AsyncMock(return_value=True)
    mock.send_shortlist_notification = AsyncMock(return_value=True)
    mock.send_offer_letter = AsyncMock(return_value=True)
    mock.send_certificate_ready = AsyncMock(return_value=True)
    mock.send_test_email = AsyncMock(return_value=True)
    return mock


def mock_scheduler_service():
    """Return a mock scheduler that does nothing."""
    mock = MagicMock()
    mock.start = MagicMock()
    mock.shutdown = MagicMock()
    return mock


# ── Core Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_db():
    """Reset the test DB before every test."""
    test_db.reset()
    yield


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """
    Reset slowapi's in-memory rate limit storage before every test.
    Without this, OTP rate limits (3/minute) fire across tests sharing the same IP.

    The auth route uses its own `limiter` instance (routes.auth.limiter),
    separate from main.limiter.
    """
    def _clear_limiter(lim):
        try:
            storage = lim._storage
            # Different versions of slowapi use different internal structures
            for attr in ("_storage", "storage", "_mapping", "_cache"):
                if hasattr(storage, attr):
                    val = getattr(storage, attr)
                    if isinstance(val, dict):
                        val.clear()
                        return
        except Exception:
            pass

    try:
        from main import limiter as main_limiter
        _clear_limiter(main_limiter)
    except Exception:
        pass

    try:
        from routes.auth import limiter as auth_limiter
        _clear_limiter(auth_limiter)
    except Exception:
        pass

    yield


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    Return an httpx AsyncClient wired to the FastAPI app via ASGITransport.
    All external services are mocked, and the DB is the in-memory test DB.
    Uses contextlib.ExitStack to avoid Python's 'too many statically nested blocks' limit.
    """
    from contextlib import ExitStack

    mock_email = mock_email_service()
    mock_sched = mock_scheduler_service()

    patches = [
        patch("db.database.db", test_db),
        patch("routes.admin.db", test_db),
        patch("routes.students.db", test_db),
        patch("routes.auth.db", test_db),
        patch("routes.certificates.db", test_db),
        patch("routes.payments.db", test_db),
        patch("routes.referrals.db", test_db),
        patch("routes.portfolio.db", test_db),
        patch("services.auth_service.db", test_db),
        patch("services.batch_service.db", test_db),
        patch("services.submission_service.db", test_db),
        patch("services.certificate_service.db", test_db),
        patch("middleware.student_auth.db", test_db),
        patch("services.email_service.email_service", mock_email),
        patch("routes.admin.email_service", mock_email),
        patch("routes.students.email_service", mock_email),
        patch("routes.auth.email_service", mock_email),
        patch("routes.certificates.email_service", mock_email),
        patch("routes.payments.email_service", mock_email),
        patch("main.scheduler_service", mock_sched),
    ]

    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac


# ── Convenience Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def admin_headers() -> dict:
    """Headers to authenticate as admin."""
    return {"X-Admin-Key": "test-admin-key"}


@pytest_asyncio.fixture
async def test_student(client) -> dict:
    """Seed a test student and return its data."""
    student_id = await seed_student(test_db)
    return {
        "id": student_id,
        "email": "test@example.com",
        "first_name": "Test",
        "last_name": "Student",
        "github_username": "testuser",
        "domain": "web-dev",
    }


@pytest_asyncio.fixture
async def test_batch(client) -> dict:
    """Seed a test batch and return its data."""
    batch_id = await seed_batch(test_db)
    return {
        "id": batch_id,
        "domain": "web-dev",
        "batch_number": 1,
        "repo_name": "web-dev-batch-1",
    }


@pytest_asyncio.fixture
async def enrolled_student(client, test_student, test_batch) -> dict:
    """Seed an enrolled student and return combined data."""
    await seed_enrollment(test_db, test_student["id"], test_batch["id"])
    return {**test_student, "batch_id": test_batch["id"]}


@pytest_asyncio.fixture
async def paid_student(client, enrolled_student, test_batch) -> dict:
    """Seed an enrolled student with a completed payment."""
    await seed_payment(test_db, enrolled_student["id"], test_batch["id"])
    return enrolled_student


@pytest_asyncio.fixture
async def student_token(test_student) -> str:
    """Return a valid JWT for the test student."""
    return make_jwt(test_student["id"], test_student["email"])


@pytest_asyncio.fixture
async def student_headers(student_token) -> dict:
    """Authorization header for student auth."""
    return {"Authorization": f"Bearer {student_token}"}
