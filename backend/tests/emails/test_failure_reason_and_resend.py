"""
Failed sends record why they failed (email_logs.error_message), and a failed row can be resent
from the admin email log, updating the same row.
"""

import smtplib
from datetime import datetime, timezone

import pytest

from services import email_service as es

PRIMARY = ("primary@smtp-brevo.com", "key-a")
EXTRA = ("extra@smtp-brevo.com", "key-b")


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    es._credits.clear()
    es._refused_today.clear()
    es._resending.clear()
    monkeypatch.setattr(es, "_accounts", lambda: [PRIMARY, EXTRA])
    monkeypatch.setattr(es.settings, "email_enabled", True)
    monkeypatch.setattr(es.settings, "quota_alert_email", "")

    async def _no_refresh():
        return None

    monkeypatch.setattr(es, "_refresh_credits", _no_refresh)

    async def _no_usage():
        return [{"account": a[0], "exhausted": False, "credits_left": 100} for a in [PRIMARY, EXTRA]]

    monkeypatch.setattr(es, "get_quota_usage", _no_usage)
    yield
    es._credits.clear()
    es._refused_today.clear()
    es._resending.clear()


def _set_credits(login: str, n: int):
    es._credits[login] = (n, datetime.now(timezone.utc))


@pytest.mark.asyncio
async def test_quota_exhausted_reason(monkeypatch):
    _set_credits(PRIMARY[0], 0)
    _set_credits(EXTRA[0], 0)
    ok, account, err = await es._send_detailed("a@example.com", "A", "s", "b")
    assert (ok, account) == (False, None)
    assert err.startswith("quota_exhausted:")


@pytest.mark.asyncio
async def test_recipient_refused_reason(monkeypatch):
    def refuse(*a):
        raise smtplib.SMTPRecipientsRefused({"a@example.com": (550, b"mailbox unavailable")})

    monkeypatch.setattr(es, "_send_sync", refuse)
    ok, _, err = await es._send_detailed("a@example.com", "A", "s", "b")
    assert not ok
    assert err == "recipient_refused: 550 mailbox unavailable"


@pytest.mark.asyncio
async def test_smtp_error_lists_every_account(monkeypatch):
    def boom(*a):
        raise OSError("network down")

    monkeypatch.setattr(es, "_send_sync", boom)
    ok, _, err = await es._send_detailed("a@example.com", "A", "s", "b")
    assert not ok
    assert err.startswith("smtp_error:")
    assert PRIMARY[0] in err and EXTRA[0] in err and "network down" in err


@pytest.mark.asyncio
async def test_success_has_no_reason(monkeypatch):
    monkeypatch.setattr(es, "_send_sync", lambda *a: None)
    assert await es._send_detailed("a@example.com", "A", "s", "b") == (True, PRIMARY[0], None)


class FakeDB:
    def __init__(self, row):
        self.row = row
        self.writes = []

    async def fetch_one(self, query, params):
        return dict(self.row) if self.row else None

    async def execute(self, query, params):
        self.writes.append((query, params))


@pytest.fixture
def fake_db(monkeypatch):
    from db.database import db

    def make(row):
        f = FakeDB(row)
        monkeypatch.setattr(db, "fetch_one", f.fetch_one)
        monkeypatch.setattr(db, "execute", f.execute)
        return f

    return make


ROW = {"id": 7, "recipient_email": "a@example.com", "recipient_name": "A",
       "subject": "We received your SkillMe application!", "body": "<p>hi</p>", "status": "failed"}


@pytest.mark.asyncio
async def test_resend_success_marks_same_row_sent(monkeypatch, fake_db):
    f = fake_db(ROW)
    sent = []
    monkeypatch.setattr(es, "_send_sync", lambda *a: sent.append(a))

    res = await es.resend_failed_email(7)

    assert res == {"status": "sent", "error": None}
    assert sent[0][0] == "a@example.com" and sent[0][4] == "log7"
    query, params = f.writes[-1]
    assert "status = 'sent'" in query and "error_message = NULL" in query
    assert params == (PRIMARY[0], "log7", 7)


@pytest.mark.asyncio
async def test_resend_failure_updates_reason_only(monkeypatch, fake_db):
    f = fake_db(ROW)
    _set_credits(PRIMARY[0], 0)
    _set_credits(EXTRA[0], 0)

    res = await es.resend_failed_email(7)

    assert res["status"] == "failed" and res["error"].startswith("quota_exhausted:")
    query, params = f.writes[-1]
    assert "status" not in query.split("SET")[1].split("WHERE")[0]
    assert params[1] == 7


@pytest.mark.asyncio
@pytest.mark.parametrize("row,msg", [
    (None, "not found"),
    ({**ROW, "status": "sent"}, "Only failed"),
    ({**ROW, "body": None}, "no stored body"),
])
async def test_resend_rejects_bad_rows(monkeypatch, fake_db, row, msg):
    fake_db(row)
    monkeypatch.setattr(es, "_send_sync", lambda *a: pytest.fail("must not send"))
    with pytest.raises(ValueError, match=msg):
        await es.resend_failed_email(7)


@pytest.mark.asyncio
async def test_resend_in_flight_is_blocked(fake_db):
    fake_db(ROW)
    es._resending.add(7)
    with pytest.raises(RuntimeError):
        await es.resend_failed_email(7)
