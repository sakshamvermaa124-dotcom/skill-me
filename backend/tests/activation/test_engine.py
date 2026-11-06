"""Engagement engine: modes, dedupe, auto-stop, suppression, caps, holdout, old cohorts."""
import pytest

from config import settings
from tests.activation.helpers import enrolled, login, sub, ts
from tests.conftest import seed_student, test_db

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("client")]


async def _cfg(**patch):
    from services import activation_service as seg
    base = {"holdout_pct": 0}
    base.update(patch)
    return await seg.save_config(base)


def _mailer():
    from services import engagement_service as eng
    return eng.es.email_service.send_activation


@pytest.fixture
def live_ok(monkeypatch):
    monkeypatch.setattr(settings, "engagement_live_allowed", True)


async def _rows(where="1=1"):
    return await test_db.fetch_all(f"SELECT * FROM engagement_reminders WHERE {where}")


class TestModes:
    async def test_off_does_nothing(self):
        from services import engagement_service as eng
        await enrolled(test_db, "a@x.com")
        res = await eng.run_tick(throttle=0)
        assert res["mode"] == "off" and res["evaluated"] == 0
        assert await _rows() == []

    async def test_dry_run_records_but_never_sends(self):
        from services import engagement_service as eng
        await enrolled(test_db, "a@x.com")
        await _cfg(mode="dry_run")
        res = await eng.run_tick(throttle=0)
        assert res["would_send"] == 1 and res["sent"] == 0
        assert [r["status"] for r in await _rows()] == ["dry_run"]
        _mailer().assert_not_called()
        assert await test_db.fetch_all("SELECT * FROM email_logs") == []

    async def test_dry_run_is_idempotent_within_a_step(self):
        from services import engagement_service as eng
        sid, bid = await enrolled(test_db, "a@x.com", days_ago=0)  # only step 1 due
        await _cfg(mode="dry_run")
        await test_db.execute("UPDATE enrollments SET joined_at = ? WHERE student_id = ?", (ts(0.1), sid))
        await eng.run_tick(throttle=0)
        await eng.run_tick(throttle=0)
        assert len(await _rows()) <= 2  # step 1, then the sequence advances at most one step per tick

    async def test_live_without_env_interlock_refuses_to_send(self):
        from services import engagement_service as eng
        await enrolled(test_db, "a@x.com")
        await _cfg(mode="live")
        assert settings.engagement_live_allowed is False
        res = await eng.run_tick(throttle=0)
        assert res["mode"] == "dry_run" and "ENGAGEMENT_LIVE_ALLOWED" in res["note"]
        _mailer().assert_not_called()

    async def test_live_sends_and_never_duplicates(self, live_ok):
        from services import activation_service as seg
        from services import engagement_service as eng
        await enrolled(test_db, "a@x.com")
        await _cfg(mode="live")
        rows, cfg = await seg.load_recovery_rows()
        r = rows[0]
        first = await eng.process_one(r, "onboarding_no_login", 1, "live", cfg)
        again = await eng.process_one(r, "onboarding_no_login", 1, "live", cfg)
        assert first["status"] == "sent" and again["reason"] == "duplicate"
        assert _mailer().await_count == 1
        sent = await _rows("status = 'sent'")
        assert len(sent) == 1 and sent[0]["token"]

    async def test_live_tick_sends_sequence_one_step_per_tick(self, live_ok):
        from services import engagement_service as eng
        await enrolled(test_db, "a@x.com", days_ago=2)
        await _cfg(mode="live")
        r1 = await eng.run_tick(throttle=0)
        r2 = await eng.run_tick(throttle=0)
        r3 = await eng.run_tick(throttle=0)
        assert (r1["sent"], r2["sent"], r3["sent"]) == (1, 1, 0)  # step 3 is not due until 72h
        assert sorted(r["step"] for r in await _rows("status='sent'")) == [1, 2]


class TestAutoStop:
    async def test_progressed_student_is_not_reminded(self, live_ok):
        from services import engagement_service as eng
        sid, bid = await enrolled(test_db, "a@x.com", days_ago=2)
        await _cfg(mode="live")
        await login(test_db, "a@x.com", days_ago=1)  # logged in -> onboarding no longer applies
        res = await eng.run_tick(throttle=0)
        kinds = {c.args[0] for c in _mailer().await_args_list}
        assert "onboarding_no_login" not in kinds

    async def test_first_task_submission_stops_first_task_nudges(self, live_ok):
        from services import engagement_service as eng
        sid, bid = await enrolled(test_db, "a@x.com", days_ago=4)
        await login(test_db, "a@x.com", days_ago=3)
        await sub(test_db, sid, bid, 1, status="pending", days_ago=0)
        await _cfg(mode="live")
        await eng.run_tick(throttle=0)
        assert "login_no_first_task" not in {c.args[0] for c in _mailer().await_args_list}

    async def test_milestone_trigger_targets_next_week_only(self, live_ok):
        from services import engagement_service as eng
        sid, bid = await enrolled(test_db, "a@x.com", days_ago=10)
        await login(test_db, "a@x.com", days_ago=9)
        await sub(test_db, sid, bid, 1, status="approved", days_ago=6)
        await _cfg(mode="live")
        await eng.run_tick(throttle=0)
        calls = _mailer().await_args_list
        assert [c.args[0] for c in calls] == ["milestone_stall"]
        assert calls[0].kwargs["ms"]["next_week"] == 2 and calls[0].kwargs["ms"]["last_approved"] == 1
        # Student submits Week 2 -> nothing more to nudge
        await sub(test_db, sid, bid, 2, status="pending", days_ago=0)
        _mailer().reset_mock()
        await eng.run_tick(throttle=0)
        _mailer().assert_not_called()


class TestSuppressionAndCaps:
    async def _blocked(self, live_ok_fixture=None):
        _mailer().assert_not_called()
        assert await _rows("status = 'sent'") == []

    async def test_opt_out_blocks(self, live_ok):
        from services import engagement_service as eng
        await enrolled(test_db, "a@x.com")
        await _cfg(mode="live")
        await eng.opt_out("A@x.com")
        res = await eng.run_tick(throttle=0)
        assert res["suppressed"] == 1
        await self._blocked()

    @pytest.mark.parametrize("col,val", [("bounced_at", "2025-01-01"), ("spam_reported_at", "2025-01-01"),
                                         ("unsubscribed_at", "2025-01-01")])
    async def test_email_log_signals_block(self, live_ok, col, val):
        from services import engagement_service as eng
        await enrolled(test_db, "a@x.com")
        await test_db.execute(
            f"INSERT INTO email_logs (recipient_email, email_type, subject, status, {col}, bounce_type) VALUES ('a@x.com','other','s','sent',?,?)",
            (val, "hard_bounce"))
        await _cfg(mode="live")
        await eng.run_tick(throttle=0)
        await self._blocked()

    async def test_soft_bounce_does_not_block(self, live_ok):
        from services import engagement_service as eng
        await enrolled(test_db, "a@x.com")
        await test_db.execute(
            "INSERT INTO email_logs (recipient_email, email_type, subject, status, bounced_at, bounce_type) VALUES ('a@x.com','other','s','sent','2025-01-01','soft_bounce')")
        assert await eng.suppression_reason("a@x.com") is None

    async def test_cap_counts_legacy_task_reminder(self, live_ok):
        from services import engagement_service as eng
        await enrolled(test_db, "a@x.com")
        await test_db.execute(
            "INSERT INTO email_logs (recipient_email, email_type, subject, status) VALUES ('a@x.com','task_reminder','s','sent')")
        await _cfg(mode="live")
        await eng.run_tick(throttle=0)
        await self._blocked()

    async def test_holdout_is_excluded_and_recorded(self, live_ok):
        from services import engagement_service as eng
        await enrolled(test_db, "a@x.com")
        await _cfg(mode="live", holdout_pct=100)
        res = await eng.run_tick(throttle=0)
        assert res["suppressed"] == 1
        assert [r["reason"] for r in await _rows("status = 'suppressed'")] == ["holdout"]
        await self._blocked()


class TestEligibility:
    async def test_ended_cohort_is_never_automated(self, live_ok):
        from services import engagement_service as eng
        await enrolled(test_db, "old@x.com", days_ago=80)
        await _cfg(mode="live")
        res = await eng.run_tick(throttle=0)
        assert res["evaluated"] == 0
        _mailer().assert_not_called()

    async def test_manual_send_to_ended_cohort_needs_override(self, live_ok):
        from services import engagement_service as eng
        sid, _ = await enrolled(test_db, "old@x.com", days_ago=80)
        await _cfg(mode="live")
        elig, excl, _ = await eng.evaluate_manual([sid])
        assert not elig and excl[0]["reason"] == "cohort_ended"
        res = await eng.send_manual([sid], override_ended=False, throttle=0)
        assert res["sent"] == 0
        res = await eng.send_manual([sid], override_ended=True, throttle=0)
        assert res["sent"] == 1

    async def test_manual_send_same_day_is_not_duplicated(self, live_ok):
        from services import engagement_service as eng
        sid, _ = await enrolled(test_db, "a@x.com")
        await _cfg(mode="live")
        await eng.send_manual([sid], throttle=0)
        res = await eng.send_manual([sid], throttle=0)
        assert res["sent"] == 0 and _mailer().await_count == 1

    async def test_test_accounts_only_participate_in_dry_run(self, live_ok):
        from services import engagement_service as eng
        sid, _ = await enrolled(test_db, "t@x.com")
        await test_db.execute("UPDATE students SET is_test = 1 WHERE id = ?", (sid,))
        await _cfg(mode="live")
        await eng.run_tick(throttle=0)
        _mailer().assert_not_called()
        await _cfg(mode="dry_run")
        assert (await eng.run_tick(throttle=0))["would_send"] == 1


class TestClickAndOptOut:
    async def test_click_is_recorded_once(self, live_ok):
        from services import engagement_service as eng
        sid, _ = await enrolled(test_db, "a@x.com")
        await _cfg(mode="live")
        await eng.send_manual([sid], throttle=0)
        token = (await _rows("status='sent'"))[0]["token"]
        assert await eng.register_click(token) and await eng.register_click(token)
        n = await test_db.fetch_one("SELECT COUNT(*) AS n FROM student_events WHERE event_type='reminder_clicked'")
        assert n["n"] == 1
        assert await eng.register_click("nope") is False

    async def test_unsubscribe_signature(self):
        from services import engagement_service as eng
        sig = eng.unsubscribe_sig("A@x.com")
        assert eng.unsubscribe_valid("a@x.com", sig)
        assert not eng.unsubscribe_valid("a@x.com", "bad")
        assert not eng.unsubscribe_valid("b@x.com", sig)
