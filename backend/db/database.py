"""
SkillMe — Database Layer
Async SQLite database with connection pooling.
"""

import aiosqlite
from pathlib import Path
from config import settings


SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class Database:
    """Async SQLite database wrapper."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._connection: aiosqlite.Connection | None = None

    async def connect(self):
        """Initialize database connection and create tables."""
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row
        # Enable WAL mode for better concurrent reads
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA foreign_keys=ON")
        # Run schema
        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        await self._connection.executescript(schema_sql)
        await self._connection.commit()

    async def disconnect(self):
        """Close database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    @property
    def conn(self) -> aiosqlite.Connection:
        """Get the active connection."""
        if not self._connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._connection

    async def execute(self, query: str, params: tuple = ()) -> aiosqlite.Cursor:
        """Execute a single query."""
        cursor = await self.conn.execute(query, params)
        await self.conn.commit()
        return cursor

    async def fetch_one(self, query: str, params: tuple = ()) -> dict | None:
        """Fetch a single row as a dict."""
        cursor = await self.conn.execute(query, params)
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    async def fetch_all(self, query: str, params: tuple = ()) -> list[dict]:
        """Fetch all rows as a list of dicts."""
        cursor = await self.conn.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def insert(self, query: str, params: tuple = ()) -> int:
        """Insert a row and return the last inserted ID."""
        cursor = await self.conn.execute(query, params)
        await self.conn.commit()
        return cursor.lastrowid


# Global database instance
db = Database(settings.db_path)
