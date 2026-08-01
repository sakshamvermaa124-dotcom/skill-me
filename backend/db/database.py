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
        self._conn = self._make_connection()

        # Apply schema (CREATE IF NOT EXISTS — safe to run every start)
        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        statements = [s.strip() for s in schema_sql.split(";") if s.strip()]
        for stmt in statements:
            self._conn.execute(stmt)
        self._conn.commit()

        # Run migrations — safe to run on every startup (no-op if already done)
        migrations = [
            "ALTER TABLE students ADD COLUMN domain TEXT",
        ]
        for migration in migrations:
            try:
                self._conn.execute(migration)
                self._conn.commit()
            except Exception:
                pass  # Column already exists — safe to ignore

        logger.info(f"Database connected: {self._url}")

    async def disconnect(self):
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Query helpers ──────────────────────────────────────────────

    async def execute(self, query: str, params: tuple = ()):
        """Execute a single write query (with auto-reconnect on stream expiry)."""
        def _run():
            cursor = self._conn.execute(query, params)
            self._conn.commit()
            return cursor
        return self._execute_with_retry(_run)

    async def fetch_one(self, query: str, params: tuple = ()) -> dict | None:
        """Fetch a single row as a dict (with auto-reconnect on stream expiry)."""
        def _run():
            cursor = self._conn.execute(query, params)
            row = cursor.fetchone()
            if row is None:
                return None
            columns = [description[0] for description in cursor.description]
            return dict(zip(columns, row))
        return self._execute_with_retry(_run)

    async def fetch_all(self, query: str, params: tuple = ()) -> list[dict]:
        """Fetch all rows as a list of dicts (with auto-reconnect on stream expiry)."""
        def _run():
            cursor = self._conn.execute(query, params)
            rows = cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
        return self._execute_with_retry(_run)

    async def insert(self, query: str, params: tuple = ()) -> int:
        """Insert a row and return the last inserted ID (with auto-reconnect on stream expiry)."""
        def _run():
            cursor = self._conn.execute(query, params)
            self._conn.commit()
            return cursor.lastrowid
        return self._execute_with_retry(_run)


# Global database instance — reads TURSO_DB_URL and TURSO_AUTH_TOKEN from env
db = Database(
    url=settings.turso_db_url,
    auth_token=settings.turso_auth_token,
)
