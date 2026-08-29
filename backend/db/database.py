"""
SkillMe — Database Layer
Async LibSQL (Turso) database client.
Replaces aiosqlite with cloud-persistent storage so data survives redeployments.
"""

import logging
from pathlib import Path
from config import settings

try:
    import libsql_experimental as libsql
except ImportError:
    import sqlite3 as libsql

logger = logging.getLogger("skillme.database")

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class Database:
    """Async LibSQL (Turso) database wrapper with sqlite3 fallback — API-compatible.
    
    Includes automatic reconnect logic to handle Turso stream expiry errors
    (error: 'stream not found') that occur after periods of inactivity.
    """

    def __init__(self, url: str, auth_token: str):
        self._url = url
        self._auth_token = auth_token
        self._conn: libsql.Connection | None = None

    def _make_connection(self) -> libsql.Connection:
        """Create a fresh libsql / sqlite3 connection."""
        if self._auth_token and getattr(libsql, "__name__", "") == "libsql_experimental":
            return libsql.connect(self._url, auth_token=self._auth_token)
        else:
            url = self._url
            if url.startswith("libsql://") or url.startswith("https://"):
                url = "local.db"
            return libsql.connect(url)

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
                "ALTER TABLE email_logs ADD COLUMN body TEXT", # v3 update
                # otp_tokens — student OTP login (v3)
                """CREATE TABLE IF NOT EXISTS otp_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    otp_hash TEXT NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    used INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""",
                "CREATE INDEX IF NOT EXISTS idx_otp_email ON otp_tokens(email)",
                # referral_codes — one per student (v3)
                """CREATE TABLE IF NOT EXISTS referral_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL UNIQUE,
                    code TEXT NOT NULL UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""",
                "CREATE INDEX IF NOT EXISTS idx_referral_codes_code ON referral_codes(code)",
                # referral_conversions (v3)
                """CREATE TABLE IF NOT EXISTS referral_conversions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    referrer_student_id INTEGER NOT NULL,
                    referred_student_id INTEGER,
                    referred_email TEXT NOT NULL,
                    status TEXT DEFAULT 'clicked',
                    discount_applied INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""",
                "CREATE INDEX IF NOT EXISTS idx_referral_conv_referrer ON referral_conversions(referrer_student_id)",
                # ── Monitoring & QA tables (v4) ──
                """CREATE TABLE IF NOT EXISTS monitor_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    category TEXT NOT NULL,
                    workflow TEXT,
                    failed_step TEXT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    expected TEXT,
                    actual TEXT,
                    student_id INTEGER,
                    student_email TEXT,
                    api_response TEXT,
                    error_details TEXT,
                    component TEXT,
                    is_regression INTEGER DEFAULT 0,
                    is_resolved INTEGER DEFAULT 0,
                    resolved_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""",
                "CREATE INDEX IF NOT EXISTS idx_monitor_alerts_severity ON monitor_alerts(severity)",
                "CREATE INDEX IF NOT EXISTS idx_monitor_alerts_created ON monitor_alerts(created_at)",
                "CREATE INDEX IF NOT EXISTS idx_monitor_alerts_resolved ON monitor_alerts(is_resolved)",
                """CREATE TABLE IF NOT EXISTS monitor_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    check_name TEXT NOT NULL,
                    check_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    response_time_ms INTEGER,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""",
                "CREATE INDEX IF NOT EXISTS idx_monitor_checks_name ON monitor_checks(check_name)",
                "CREATE INDEX IF NOT EXISTS idx_monitor_checks_created ON monitor_checks(created_at)",
                """CREATE TABLE IF NOT EXISTS frontend_errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    page TEXT NOT NULL,
                    error_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    stack_trace TEXT,
                    url TEXT,
                    user_agent TEXT,
                    student_email TEXT,
                    session_id TEXT,
                    request_url TEXT,
                    request_status INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""",
                "CREATE INDEX IF NOT EXISTS idx_frontend_errors_page ON frontend_errors(page)",
                "CREATE INDEX IF NOT EXISTS idx_frontend_errors_created ON frontend_errors(created_at)",
                "CREATE INDEX IF NOT EXISTS idx_frontend_errors_email ON frontend_errors(student_email)",
                # payment_unlocked_at — set on enrollments when an admin fulfills a sub-50% urgent request (v5)
                "ALTER TABLE enrollments ADD COLUMN payment_unlocked_at TIMESTAMP",
                # Email delivery/engagement tracking via Brevo webhook events (v6)
                "ALTER TABLE email_logs ADD COLUMN message_tag TEXT",
                "ALTER TABLE email_logs ADD COLUMN delivered_at TIMESTAMP",
                "ALTER TABLE email_logs ADD COLUMN opened_at TIMESTAMP",
                "ALTER TABLE email_logs ADD COLUMN opened_count INTEGER DEFAULT 0",
                "ALTER TABLE email_logs ADD COLUMN clicked_at TIMESTAMP",
                "ALTER TABLE email_logs ADD COLUMN clicked_count INTEGER DEFAULT 0",
                "ALTER TABLE email_logs ADD COLUMN bounced_at TIMESTAMP",
                "ALTER TABLE email_logs ADD COLUMN bounce_type TEXT",
                "ALTER TABLE email_logs ADD COLUMN spam_reported_at TIMESTAMP",
                "ALTER TABLE email_logs ADD COLUMN unsubscribed_at TIMESTAMP",
                "ALTER TABLE email_logs ADD COLUMN last_event TEXT",
                "ALTER TABLE email_logs ADD COLUMN last_event_at TIMESTAMP",
                "CREATE INDEX IF NOT EXISTS idx_email_logs_tag ON email_logs(message_tag)",
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

    def _run_turso_http(self, query: str, params: tuple = ()):
        """Query Turso Cloud DB via HTTP Pipeline API when libsql_experimental native driver is unavailable."""
        import httpx
        http_url = self._url.replace("libsql://", "https://")
        if not http_url.startswith("http"):
            http_url = "https://" + http_url
        if not http_url.endswith("/v2/pipeline"):
            http_url = http_url.rstrip("/") + "/v2/pipeline"

        formatted_args = []
        for p in params:
            if isinstance(p, int):
                formatted_args.append({"type": "integer", "value": str(p)})
            elif isinstance(p, float):
                formatted_args.append({"type": "float", "value": p})
            elif p is None:
                formatted_args.append({"type": "null"})
            else:
                formatted_args.append({"type": "text", "value": str(p)})

        payload = {
            "requests": [
                {
                    "type": "execute",
                    "stmt": {
                        "sql": query,
                        "args": formatted_args
                    }
                },
                {"type": "close"}
            ]
        }
        headers = {"Authorization": f"Bearer {self._auth_token}", "Content-Type": "application/json"}
        with httpx.Client(timeout=10.0) as client:
            res = client.post(http_url, headers=headers, json=payload)
            res.raise_for_status()
            data = res.json()
            results = data.get("results", [])
            if not results or "response" not in results[0]:
                return [], None
            result = results[0]["response"].get("result", {})
            cols = [c["name"] for c in result.get("cols", [])]
            rows = []
            for r in result.get("rows", []):
                row_vals = [v.get("value") if isinstance(v, dict) else v for v in r]
                rows.append(dict(zip(cols, row_vals)))
            last_id = result.get("last_insert_rowid")
            if last_id is not None and str(last_id).isdigit():
                last_id = int(last_id)
            return rows, last_id

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
        if self._auth_token and getattr(libsql, "__name__", "") != "libsql_experimental":
            self._run_turso_http(query, params)
            return
        def _run(conn):
            conn.execute(query, params)
            conn.commit()
        return self._run_query(_run)

    async def fetch_one(self, query: str, params: tuple = ()) -> dict | None:
        """Fetch a single row as a dict."""
        if self._auth_token and getattr(libsql, "__name__", "") != "libsql_experimental":
            rows, _ = self._run_turso_http(query, params)
            return rows[0] if rows else None
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
        if self._auth_token and getattr(libsql, "__name__", "") != "libsql_experimental":
            rows, _ = self._run_turso_http(query, params)
            return rows
        def _run(conn):
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
        return self._run_query(_run)

    async def insert(self, query: str, params: tuple = ()) -> int:
        """Insert a row and return the last inserted ID."""
        if self._auth_token and getattr(libsql, "__name__", "") != "libsql_experimental":
            _, last_id = self._run_turso_http(query, params)
            return last_id or 0
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
