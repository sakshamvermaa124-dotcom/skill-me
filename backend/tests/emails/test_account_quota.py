"""
Brevo multi-account selection: mail must never go to an account that is out of quota,
because Brevo accepts it over SMTP and then silently drops it.
"""

from datetime import datetime, timedelta, timezone

import pytest

from services import email_service as es

PRIMARY = ("primary@smtp-brevo.com", "key-a")
EXTRA = ("extra@smtp-brevo.com", "key-b")


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    es._credits.clear()
    es._key_fetched_at.clear()
    es._refused_today.clear()
    monkeypatch.setattr(es, "_accounts", lambda: [PRIMARY, EXTRA])
    monkeypatch.setattr(es.settings, "email_enabled", True)
    monkeypatch.setattr(es.settings, "smtp_daily_limit", 295)
    yield
    es._credits.clear()
    es._key_fetched_at.clear()
    es._refused_today.clear()


def _db_usage(monkeypatch, used: dict[str, int]):
    """Fake our own email_logs count per account; no Brevo API keys configured."""
    async def fake_fetch_one(query, params):
        return {"n": used.get(params[0], 0)}

    from db.database import db
    monkeypatch.setattr(db, "fetch_one", fake_fetch_one)


def _set_credits(login: str, n: int):
    es._credits[login] = (n, datetime.now(timezone.utc))


async def _no_refresh():
    return None


@pytest.mark.asyncio
async def test_brevo_credits_override_low_local_count(monkeypatch):
    """Our log says 285 (under the 295 cap) but Brevo says 0 left: the account must be skipped."""
    _db_usage(monkeypatch, {PRIMARY[0]: 285, EXTRA[0]: 174})
    monkeypatch.setattr(es, "_refresh_credits", _no_refresh)
    _set_credits(PRIMARY[0], 0)
    _set_credits(EXTRA[0], 120)

    assert await es._ordered_accounts() == [EXTRA]


@pytest.mark.asyncio
async def test_exhausted_accounts_are_never_used_even_as_last_resort(monkeypatch):
    _db_usage(monkeypatch, {})
    monkeypatch.setattr(es, "_refresh_credits", _no_refresh)
    _set_credits(PRIMARY[0], 0)
    _set_credits(EXTRA[0], 0)
    sent = []
    monkeypatch.setattr(es, "_send_sync", lambda *a, **k: sent.append(a))

    ok, account = await es._send_ex("s@example.com", "S", "subj", "<p>x</p>")

    assert (ok, account) == (False, None)
    assert sent == []


@pytest.mark.asyncio
async def test_fallback_to_local_count_when_no_api_key(monkeypatch):
    monkeypatch.setattr(es.settings, "brevo_api_key", "")
    monkeypatch.setattr(es.settings, "brevo_extra_api_keys", "")
    _db_usage(monkeypatch, {PRIMARY[0]: 295, EXTRA[0]: 10})

    assert await es._ordered_accounts() == [EXTRA]


@pytest.mark.asyncio
async def test_local_count_window_starts_at_utc_midnight():
    start = es._quota_day_start_utc()
    now = datetime.now(timezone.utc)
    assert start == now.strftime("%Y-%m-%d") + " 00:00:00"


@pytest.mark.asyncio
async def test_last_credit_cannot_be_spent_twice(monkeypatch):
    """Two concurrent sends seeing 1 credit left: only one may use that account."""
    import asyncio

    _db_usage(monkeypatch, {})
    monkeypatch.setattr(es, "_refresh_credits", _no_refresh)
    _set_credits(PRIMARY[0], 1)
    _set_credits(EXTRA[0], 50)
    used = []
    monkeypatch.setattr(es, "_send_sync", lambda *a: used.append(a[5][0]))

    results = await asyncio.gather(
        es._send_ex("a@example.com", "A", "s", "b"),
        es._send_ex("b@example.com", "B", "s", "b"),
    )

    assert all(ok for ok, _ in results)
    assert sorted(used) == sorted([PRIMARY[0], EXTRA[0]])
    assert es._credits[PRIMARY[0]][0] == 0


@pytest.mark.asyncio
async def test_failed_send_refunds_the_credit(monkeypatch):
    _db_usage(monkeypatch, {})
    monkeypatch.setattr(es, "_refresh_credits", _no_refresh)
    _set_credits(PRIMARY[0], 5)
    _set_credits(EXTRA[0], 5)

    def boom(*a):
        raise OSError("network down")

    monkeypatch.setattr(es, "_send_sync", boom)
    ok, _ = await es._send_ex("a@example.com", "A", "s", "b")

    assert not ok
    assert es._credits[PRIMARY[0]][0] == 5
    assert es._credits[EXTRA[0]][0] == 5


@pytest.mark.asyncio
async def test_stale_credits_fall_back_to_local_count(monkeypatch):
    _db_usage(monkeypatch, {PRIMARY[0]: 10, EXTRA[0]: 10})
    monkeypatch.setattr(es, "_refresh_credits", _no_refresh)
    es._credits[PRIMARY[0]] = (0, datetime.now(timezone.utc) - timedelta(minutes=30))

    assert es._credits_left(PRIMARY[0]) is None
    assert await es._ordered_accounts() == [PRIMARY, EXTRA]


def _capture_alerts(monkeypatch):
    sent = []

    async def fake_send_and_log(to, name, subject, html, email_type="other", **kw):
        sent.append((to, subject, email_type))
        return True

    monkeypatch.setattr(es, "_send_and_log", fake_send_and_log)
    monkeypatch.setattr(es.settings, "quota_alert_email", "owner@example.com")
    es._alerted.clear()
    return sent


@pytest.mark.asyncio
async def test_alert_sent_once_when_account_reaches_90_percent(monkeypatch):
    async def no_prior(query, params):
        return None if "quota_alert" in query else {"n": 0}

    from db.database import db
    monkeypatch.setattr(db, "fetch_one", no_prior)
    monkeypatch.setattr(es, "_refresh_credits", _no_refresh)
    sent = _capture_alerts(monkeypatch)
    _set_credits(PRIMARY[0], 30)   # 270/300 used = 90%
    _set_credits(EXTRA[0], 200)

    await es._maybe_send_quota_alerts()
    await es._maybe_send_quota_alerts()

    assert len(sent) == 1
    to, subject, email_type = sent[0]
    assert to == "owner@example.com" and email_type == "quota_alert"
    assert PRIMARY[0] in subject and "90%" in subject


@pytest.mark.asyncio
async def test_no_alert_below_90_percent(monkeypatch):
    async def no_prior(query, params):
        return None if "quota_alert" in query else {"n": 0}

    from db.database import db
    monkeypatch.setattr(db, "fetch_one", no_prior)
    monkeypatch.setattr(es, "_refresh_credits", _no_refresh)
    sent = _capture_alerts(monkeypatch)
    _set_credits(PRIMARY[0], 31)
    _set_credits(EXTRA[0], 300)

    await es._maybe_send_quota_alerts()

    assert sent == []


@pytest.mark.asyncio
async def test_alert_skipped_if_already_sent_today_before_restart(monkeypatch):
    async def prior_exists(query, params):
        return {"id": 1} if "quota_alert" in query else {"n": 0}

    from db.database import db
    monkeypatch.setattr(db, "fetch_one", prior_exists)
    monkeypatch.setattr(es, "_refresh_credits", _no_refresh)
    sent = _capture_alerts(monkeypatch)
    _set_credits(PRIMARY[0], 5)
    _set_credits(EXTRA[0], 300)

    await es._maybe_send_quota_alerts()

    assert sent == []


@pytest.mark.asyncio
async def test_alert_uses_local_estimate_without_api_key(monkeypatch):
    async def usage(query, params):
        if "quota_alert" in query:
            return None
        return {"n": 280 if params[0] == PRIMARY[0] else 0}

    from db.database import db
    monkeypatch.setattr(db, "fetch_one", usage)
    monkeypatch.setattr(es, "_refresh_credits", _no_refresh)
    sent = _capture_alerts(monkeypatch)

    await es._maybe_send_quota_alerts()

    assert len(sent) == 1 and PRIMARY[0] in sent[0][1]


@pytest.mark.asyncio
async def test_fetch_credits_maps_api_key_to_smtp_login():
    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "relay": {"enabled": True, "data": {"userName": "primary@smtp-brevo.com"}},
                "plan": [{"type": "free", "credits": 42, "creditsType": "sendLimit"}],
            }

    class Client:
        async def get(self, url, headers):
            return Resp()

    await es._fetch_credits(Client(), "key")
    assert es._credits_left("primary@smtp-brevo.com") == 42
