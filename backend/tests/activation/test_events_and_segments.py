"""Activation layer: event dedupe, hook safety, and mutually-exclusive segmentation."""
import hashlib
from datetime import datetime, timedelta

import pytest

from tests.conftest import seed_batch, seed_enrollment, seed_student, test_db

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("client")]


from tests.activation.helpers import enrolled as _enrolled, login as _login, sub as _sub


class TestEvents:
    async def test_record_event_is_deduplicated(self):
        from services.activation_events import record_event
        assert await record_event("first_task_viewed", 1, 1) is True
        assert await record_event("first_task_viewed", 1, 1) is False
        n = await test_db.fetch_one("SELECT COUNT(*) AS n FROM student_events")
        assert n["n"] == 1

    async def test_week_approved_is_keyed_per_week(self):
        from services.activation_events import record_event
        assert await record_event("week_approved", 1, 1, discriminator=1)
        assert await record_event("week_approved", 1, 1, discriminator=2)
        assert not await record_event("week_approved", 1, 1, discriminator=2)

    async def test_unknown_event_and_db_failure_never_raise(self, monkeypatch):
        from services import activation_events as ev
        assert await ev.record_event("bogus", 1, 1) is False

        async def boom(*a, **k):
            raise RuntimeError("db down")
        monkeypatch.setattr(ev.db, "fetch_one", boom)
        assert await ev.record_event("first_task_viewed", 1, 1) is False
        await ev.track_login("a@b.com")  # must not raise

    async def test_track_login_once_per_enrollment(self):
        from services.activation_events import track_login
        sid, bid = await _enrolled(test_db, "login@x.com")
        await track_login("LOGIN@x.com")
        await track_login("login@x.com")
        rows = await test_db.fetch_all("SELECT * FROM student_events WHERE event_type='first_verified_login'")
        assert len(rows) == 1 and rows[0]["batch_id"] == bid

    async def test_track_approval_completion(self):
        from services.activation_events import track_approval
        sid, bid = await _enrolled(test_db, "done@x.com")
        for w in (1, 2, 3, 4):
            await _sub(test_db, sid, bid, w)
        last = await test_db.fetch_one("SELECT id FROM submissions WHERE week = 4")
        await track_approval(last["id"])
        await track_approval(last["id"])
        kinds = {r["event_type"] for r in await test_db.fetch_all("SELECT event_type FROM student_events")}
        assert {"week_approved", "first_task_approved", "internship_completed"} <= kinds
        n = await test_db.fetch_one("SELECT COUNT(*) AS n FROM student_events")
        assert n["n"] == 3

    async def test_login_endpoint_still_works_when_tracker_raises(self, client, monkeypatch):
        from tests.conftest import seed_otp
        from services import activation_events as ev

        async def boom(*a, **k):
            raise RuntimeError("tracker exploded")
        monkeypatch.setattr(ev.db, "fetch_all", boom)
        await seed_student(test_db, email="ok@x.com", status="enrolled")
        await seed_otp(test_db, "ok@x.com", "123456")
        r = await client.post("/api/auth/verify-otp", json={"email": "ok@x.com", "otp": "123456"})
        assert r.status_code == 200 and r.json()["status"] == "authenticated"


class TestSegmentation:
    async def _world(self):
        ids = {}
        ids["never"], _ = await _enrolled(test_db, "never@x.com")
        ids["nofirst"], _ = await _enrolled(test_db, "nofirst@x.com")
        await _login(test_db, "nofirst@x.com")
        ids["sub"], b = await _enrolled(test_db, "sub@x.com")
        await _login(test_db, "sub@x.com")
        await _sub(test_db, ids["sub"], b, 1, status="pending")
        ids["w1"], b = await _enrolled(test_db, "w1@x.com", days_ago=10)
        await _login(test_db, "w1@x.com", days_ago=9)
        await _sub(test_db, ids["w1"], b, 1, days_ago=9)
        ids["done"], b = await _enrolled(test_db, "done@x.com", days_ago=20)
        await _login(test_db, "done@x.com", days_ago=19)
        for w in (1, 2, 3, 4):
            await _sub(test_db, ids["done"], b, w, days_ago=5)
        ids["old"], _ = await _enrolled(test_db, "old@x.com", days_ago=80)
        return ids

    async def test_stages_are_exclusive_and_sum_to_enrolled(self):
        from services import activation_service as svc
        ids = await self._world()
        rows, _ = await svc.load_recovery_rows()
        by = {r["id"]: r for r in rows}
        assert by[ids["never"]]["stage"] == "never_logged_in"
        assert by[ids["nofirst"]]["stage"] == "no_first_task"
        assert by[ids["sub"]]["stage"] == "first_task_submitted"
        assert by[ids["w1"]]["stage"] == "stuck_week_1"
        assert by[ids["done"]]["stage"] == "completed"
        summary = svc.summarize(rows)
        assert sum(s["count"] for s in summary["stages"]) == summary["total"] == len(ids)

    async def test_old_cohort_is_marked_ended_and_active_ones_are_not(self):
        from services import activation_service as svc
        ids = await self._world()
        rows, _ = await svc.load_recovery_rows()
        by = {r["id"]: r for r in rows}
        assert by[ids["old"]]["eligibility"] == "ended"
        assert by[ids["never"]]["eligibility"] == "active"

    async def test_inactive_overlay_and_filters(self):
        from services import activation_service as svc
        ids = await self._world()
        rows, _ = await svc.load_recovery_rows()
        inactive = {r["id"] for r in svc.filter_rows(rows, inactive=True)}
        assert ids["old"] in inactive and ids["sub"] not in inactive
        assert [r["id"] for r in svc.filter_rows(rows, stage="completed")] == [ids["done"]]
        assert [r["id"] for r in svc.filter_rows(rows, milestone=2, stage="stuck_week_1")] == [ids["w1"]]

    async def test_holdout_is_deterministic(self):
        from services.activation_service import is_holdout
        assert is_holdout(42, 10) == is_holdout(42, 10)
        assert sum(is_holdout(i, 10) for i in range(1000)) in range(60, 140)
        assert not any(is_holdout(i, 0) for i in range(100))

    async def test_segmentation_does_not_modify_core_tables(self):
        from services import activation_service as svc
        await self._world()

        async def digest():
            h = hashlib.sha256()
            for t in ("students", "enrollments", "submissions", "payments", "certificates"):
                for r in await test_db.fetch_all(f"SELECT * FROM {t} ORDER BY 1"):
                    h.update(repr(sorted(r.items())).encode())
            return h.hexdigest()
        before = await digest()
        await svc.load_recovery_rows()
        assert await digest() == before
