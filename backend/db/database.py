"""
SkillMe — Database Layer
Async LibSQL (Turso) database client.
Replaces aiosqlite with cloud-persistent storage so data survives redeployments.
"""

import logging
from pathlib import Path
from config import settings

import libsql_experimental as libsql

logger = logging.getLogger("skillme.database")

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class Database:
    """Async LibSQL (Turso) database wrapper — API-compatible with the old aiosqlite wrapper.
    
    Includes automatic reconnect logic to handle Turso stream expiry errors
    (error: 'stream not found') that occur after periods of inactivity.
    """

    def __init__(self, url: str, auth_token: str):
        self._url = url
        self._auth_token = auth_token
        self._conn: libsql.Connection | None = None

    def _make_connection(self) -> libsql.Connection:
        """Create a fresh libsql connection."""
        if self._auth_token:
            return libsql.connect(self._url, auth_token=self._auth_token)
        else:
            return libsql.connect(self._url)

    def _reconnect(self):
        """Drop the stale connection and open a fresh one (no schema re-run needed)."""
        try:
            if self._conn:
                self._conn.close()
        except Exception:
            pass
        self._conn = self._make_connection()
        logger.info("Database: reconnected to Turso after stream expiry.")

    def _execute_with_retry(self, fn, *args, **kwargs):
        """Call fn(*args) and retry once on Turso stream-expiry errors."""
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            err = str(e)
            if "stream not found" in err or "Hrana" in err or "stream" in err.lower():
                logger.warning(f"Turso stream error, reconnecting: {err}")
                self._reconnect()
                return fn(*args, **kwargs)
            raise

    async def connect(self):
        """Initialize the LibSQL connection and create tables from schema."""
        # Use a temporary connection to apply the schema
        conn = self._make_connection()
        try:
            # Apply schema (CREATE IF NOT EXISTS — safe to run every start)
            schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
            statements = [s.strip() for s in schema_sql.split(";") if s.strip()]
            for stmt in statements:
                conn.execute(stmt)
            conn.commit()

            # Run migrations — safe to run on every startup (no-op if already done)
            migrations = [
                "ALTER TABLE students ADD COLUMN domain TEXT",
                # email_logs table — added in v2; safe no-op if schema already ran
                """CREATE TABLE IF NOT EXISTS email_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recipient_email TEXT NOT NULL,
                    recipient_name  TEXT,
                    email_type      TEXT NOT NULL,
                    subject         TEXT NOT NULL,
                    student_id      INTEGER,
                    batch_id        INTEGER,
                    status          TEXT NOT NULL DEFAULT 'sent',
                    error_message   TEXT,
                    sent_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""",
                "CREATE INDEX IF NOT EXISTS idx_email_logs_recipient ON email_logs(recipient_email)",
                "CREATE INDEX IF NOT EXISTS idx_email_logs_type ON email_logs(email_type)",
                "CREATE INDEX IF NOT EXISTS idx_email_logs_sent_at ON email_logs(sent_at)",
            ]
            for migration in migrations:
                try:
                    conn.execute(migration)
                    conn.commit()
                except Exception:
                    pass  # Column already exists — safe to ignore
            logger.info(f"Database schema verified: {self._url}")
        finally:
            conn.close()

    async def disconnect(self):
        """No-op since connections are created per-query."""
        pass

    # ── Query helpers ──────────────────────────────────────────────

    def _run_query(self, fn):
        """Helper to run a function with a fresh connection, retrying once on network errors."""
        try:
            conn = self._make_connection()
            try:
                return fn(conn)
            finally:
                conn.close()
        except Exception as e:
            err = str(e)
            if "stream not found" in err or "Hrana" in err or "stream" in err.lower():
                logger.warning(f"Turso stream error on fresh connection, retrying: {err}")
                conn = self._make_connection()
                try:
                    return fn(conn)
                finally:
                    conn.close()
            raise

    async def execute(self, query: str, params: tuple = ()):
        """Execute a single write query."""
        def _run(conn):
            conn.execute(query, params)
            conn.commit()
        return self._run_query(_run)

    async def fetch_one(self, query: str, params: tuple = ()) -> dict | None:
        """Fetch a single row as a dict."""
        def _run(conn):
            cursor = conn.execute(query, params)
            row = cursor.fetchone()
            if row is None:
                return None
            columns = [description[0] for description in cursor.description]
            return dict(zip(columns, row))
        return self._run_query(_run)

    async def fetch_all(self, query: str, params: tuple = ()) -> list[dict]:
        """Fetch all rows as a list of dicts."""
        def _run(conn):
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
        return self._run_query(_run)

    async def insert(self, query: str, params: tuple = ()) -> int:
        """Insert a row and return the last inserted ID."""
        def _run(conn):
            cursor = conn.execute(query, params)
            conn.commit()
            return cursor.lastrowid
        return self._run_query(_run)


# Global database instance — reads TURSO_DB_URL and TURSO_AUTH_TOKEN from env
db = Database(
    url=settings.turso_db_url,
    auth_token=settings.turso_auth_token,
)
