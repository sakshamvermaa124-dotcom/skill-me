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
    """Async LibSQL (Turso) database wrapper — API-compatible with the old aiosqlite wrapper."""

    def __init__(self, url: str, auth_token: str):
        self._url = url
        self._auth_token = auth_token
        self._conn: libsql.Connection | None = None

    async def connect(self):
        """Initialize the LibSQL connection and create tables from schema."""
        # libsql_experimental.connect() supports both:
        #   - Local file:    connect("local.db")
        #   - Turso remote:  connect("libsql://...", auth_token="...")
        #   - Embedded sync: connect("local.db", sync_url="libsql://...", auth_token="...")
        if self._auth_token:
            # Production — remote Turso DB
            self._conn = libsql.connect(self._url, auth_token=self._auth_token)
        else:
            # Local dev fallback — plain SQLite file
            self._conn = libsql.connect(self._url)

        # Apply schema (CREATE IF NOT EXISTS — safe to run every start)
        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        # Split on semicolons so we can execute each statement individually
        # (libsql_experimental.Connection.executescript is not async-compatible)
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
        """Execute a single write query."""
        cursor = self._conn.execute(query, params)
        self._conn.commit()
        return cursor

    async def fetch_one(self, query: str, params: tuple = ()) -> dict | None:
        """Fetch a single row as a dict."""
        cursor = self._conn.execute(query, params)
        row = cursor.fetchone()
        if row is None:
            return None
        columns = [description[0] for description in cursor.description]
        return dict(zip(columns, row))

    async def fetch_all(self, query: str, params: tuple = ()) -> list[dict]:
        """Fetch all rows as a list of dicts."""
        cursor = self._conn.execute(query, params)
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    async def insert(self, query: str, params: tuple = ()) -> int:
        """Insert a row and return the last inserted ID."""
        cursor = self._conn.execute(query, params)
        self._conn.commit()
        return cursor.lastrowid


# Global database instance — reads TURSO_DB_URL and TURSO_AUTH_TOKEN from env
db = Database(
    url=settings.turso_db_url,
    auth_token=settings.turso_auth_token,
)
