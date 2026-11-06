"""Admin recovery API, student activation API, public click/unsubscribe, and core-journey regression."""
import pytest

from config import settings
from tests.activation.helpers import enrolled, login, sub, ts
from tests.conftest import auth_headers, seed_otp, seed_student, test_db

pytestmark = [pytest.mark.asyncio]
A = "/api/admin/activation"


async def _cfg(**patch):
    from services import activation_service as seg
    return await seg.save_config(patch)


class TestAdminApi:
    @pytest.mark.parametrize("method,path", [("get", "/summary"), ("get", "/students"), ("get", "/settings"),
                                             ("get", "/report"), ("get", "/reminders"), ("post", "/backfill"),
                                             ("post", "/run")])
    async def test_requires_admin_key(self, client, method, path):
        r = await getattr(client, method)(A + path)
        assert r.status_code == 403

    async def test_summary_counts_match_analytics_funnel(self, client, admin_headers):
        await enrolled(test_db, "never@x.com")
        s2, b2 = await enrolled(test_db, "nofirst@x.com")
        await login(test_db, "nofirst@x.com")
        s3, b3 = await enrolled(test_db, "w1@x.com", days_ago=9)
        await login(test_db, "w1@x.com", days_ago=8)
        await sub(test_db, s3, b3, 1, days_ago=5)
        r = await client.get(f"{A}/summary", headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        counts = {x["key"]: x["count"] for x in d["stages"]}
        assert counts["never_logged_in"] == 1 and counts["no_first_task"] == 1 and counts["stuck_week_1"] == 1
        an = (await client.get("/api/admin/analytics?fresh=true", headers=admin_headers)).json()
        assert d["total"] == an["overview"]["enrolled"]
        assert counts["never_logged_in"] == an["engagement"]["never_logged_in"]
        assert d["mode"]["selected"] == "off"

    async def test_students_filters_and_paging(self, client, admin_headers):
        await enrolled(test_db, "a@x.com", domain="python")
        await enrolled(test_db, "b@x.com", domain="web-dev")
        r = await client.get(f"{A}/students?domain=python&stage=never_logged_in", headers=admin_headers)
        assert [x["email"] for x in r.json()["students"]] == ["a@x.com"]
        assert (await client.get(f"{A}/students?stage=bogus", headers=admin_headers)).status_code == 400
        assert (await client.get(f"{A}/students?limit=1", headers=admin_headers)).json()["total_pages"] == 2

    async def test_settings_validation_and_live_guard(self, client, admin_headers):
        assert (await client.put(f"{A}/settings", json={"mode": "bogus"}, headers=admin_headers)).status_code == 422
        r = await client.put(f"{A}/settings", json={"mode": "live", "confirm_live": True}, headers=admin_headers)
        assert r.status_code == 409  # server interlock off
        r = await client.put(f"{A}/settings", json={"mode": "dry_run"}, headers=admin_headers)
        assert r.status_code == 200 and r.json()["config"]["mode"] == "dry_run"
        r = await client.put(f"{A}/settings", json={"triggers": {"nope": {}}}, headers=admin_headers)
        assert r.status_code == 400

    async def test_live_requires_confirmation_even_when_allowed(self, client, admin_headers, monkeypatch):
        monkeypatch.setattr(settings, "engagement_live_allowed", True)
        r = await client.put(f"{A}/settings", json={"mode": "live"}, headers=admin_headers)
        assert r.status_code == 400
        r = await client.put(f"{A}/settings", json={"mode": "live", "confirm_live": True}, headers=admin_headers)
        assert r.status_code == 200

    async def test_preview_groups_exclusions_and_renders_email(self, client, admin_headers):
        ok, _ = await enrolled(test_db, "ok@x.com")
        old, _ = await enrolled(test_db, "old@x.com", days_ago=90)
        done, b = await enrolled(test_db, "done@x.com", days_ago=20)
        await login(test_db, "done@x.com", days_ago=19)
        for w in (1, 2, 3, 4):
            await sub(test_db, done, b, w, days_ago=3)
        r = await client.post(f"{A}/preview", json={"student_ids": [ok, old, 999]}, headers=admin_headers)
        d = r.json()
        assert [e["student_id"] for e in d["eligible"]] == [ok]
        assert d["excluded_by_reason"] == {"cohort_ended": 1, "not_enrolled": 1}
        assert "<html" in d["sample"]["html"].lower() and d["sample"]["trigger"] == "onboarding_no_login"

    async def test_send_requires_confirm_and_dry_run_sends_nothing(self, client, admin_headers):
        from services import engagement_service as eng
        sid, _ = await enrolled(test_db, "ok@x.com")
        assert (await client.post(f"{A}/send", json={"student_ids": [sid]}, headers=admin_headers)).status_code == 400
        await _cfg(mode="dry_run")
        r = await client.post(f"{A}/send", json={"student_ids": [sid], "confirm": True}, headers=admin_headers)
        assert r.json()["would_send"] == 1 and r.json()["sent"] == 0
        eng.es.email_service.send_activation.assert_not_called()

    async def test_backfill_is_idempotent_and_read_only_on_core(self, client, admin_headers):
        sid, bid = await enrolled(test_db, "bf@x.com", days_ago=12)
        await login(test_db, "bf@x.com", days_ago=11)
        for w in (1, 2):
            await sub(test_db, sid, bid, w, days_ago=6)
        core = lambda: test_db.fetch_all("SELECT * FROM submissions ORDER BY id")  # noqa: E731
        before = [dict(x) for x in await core()]
        first = (await client.post(f"{A}/backfill", headers=admin_headers)).json()
        second = (await client.post(f"{A}/backfill", headers=admin_headers)).json()
        assert first["created"] > 0 and second["created"] == 0
        assert [dict(x) for x in await core()] == before
        ev = {r["event_type"] for r in await test_db.fetch_all("SELECT event_type FROM student_events")}
        assert {"enrollment_created", "first_verified_login", "first_task_submitted", "week_approved"} <= ev

    async def test_report_matches_analytics_definitions(self, client, admin_headers):
        for i in range(3):
            await enrolled(test_db, f"n{i}@x.com", days_ago=3)
        sid, bid = await enrolled(test_db, "t@x.com", days_ago=6)
        await login(test_db, "t@x.com", days_ago=5)
        await sub(test_db, sid, bid, 1, status="pending", days_ago=3)
        d = (await client.get(f"{A}/report", headers=admin_headers)).json()
        t = d["total"]
        assert t["enrolled"] == 4 and t["logged_in"] == 1 and t["first_task"] == 1
        assert t["first_task_pct"] == 100.0 and t["first_login_pct"] == 25.0
        assert d["baseline"]["first_task_pct"] == 38.0 and d["targets"]["completion_pct"] == 55.0
        assert sum(c["enrolled"] for c in d["cohorts"]) == 4

    async def test_support_inbox_flow(self, client, admin_headers):
        sid, bid = await enrolled(test_db, "h@x.com")
        h = auth_headers(sid, "h@x.com")
        await _cfg(student_ui=True)
        r = await client.post("/api/activation/support", headers=h,
                              json={"student_id": sid, "category": "stuck_on_task", "message": "help"})
        assert r.status_code == 200
        lst = (await client.get(f"{A}/support?status=open", headers=admin_headers)).json()["requests"]
        assert len(lst) == 1 and lst[0]["category"] == "stuck_on_task"
        r = await client.patch(f"{A}/support/{lst[0]['id']}", json={"status": "resolved", "admin_note": "done"}, headers=admin_headers)
        assert r.status_code == 200
        assert (await client.get(f"{A}/support?status=open", headers=admin_headers)).json()["requests"] == []


class TestStudentApi:
    async def test_flag_off_returns_disabled(self, client):
        sid, _ = await enrolled(test_db, "s@x.com")
        r = await client.get(f"/api/activation/me?student_id={sid}", headers=auth_headers(sid, "s@x.com"))
        assert r.status_code == 200 and r.json() == {"enabled": False}

    async def test_requires_auth_and_ownership(self, client):
        sid, _ = await enrolled(test_db, "s@x.com")
        other = await seed_student(test_db, email="other@x.com")
        assert (await client.get(f"/api/activation/me?student_id={sid}")).status_code == 401
        r = await client.get(f"/api/activation/me?student_id={sid}", headers=auth_headers(other, "other@x.com"))
        assert r.status_code == 403

    @pytest.mark.parametrize("domain,family_word", [("web-dev", "GitHub"), ("python", "Python"),
                                                    ("ml", "Colab"), ("data-science", "Colab")])
    async def test_first_task_is_track_specific(self, client, domain, family_word):
        await _cfg(student_ui=True)
        sid, _ = await enrolled(test_db, f"{domain}@x.com", domain=domain)
        d = (await client.get(f"/api/activation/me?student_id={sid}", headers=auth_headers(sid, f"{domain}@x.com"))).json()
        assert d["enabled"] and d["stage"] == "no_first_task"  # authenticated => treated as logged in
        ft = d["first_task"]
        assert ft["project_name"] and ft["title"] and ft["deliverables"] and ft["time_label"].startswith("About")
        assert any(family_word in x for x in ft["setup"] + [ft["submit_what"]])
        assert [c["done"] for c in d["checklist"]] == [True, False, False, False]

    async def test_tracks_differ(self, client):
        await _cfg(student_ui=True)
        got = {}
        for dom in ("web-dev", "python", "ml", "data-science"):
            sid, _ = await enrolled(test_db, f"{dom}@x.com", domain=dom)
            d = (await client.get(f"/api/activation/me?student_id={sid}", headers=auth_headers(sid, f"{dom}@x.com"))).json()
            got[dom] = d["first_task"]["title"]
        assert len(set(got.values())) == 4

    async def test_viewed_event_flips_checklist_once(self, client):
        await _cfg(student_ui=True)
        sid, _ = await enrolled(test_db, "v@x.com")
        h = auth_headers(sid, "v@x.com")
        body = {"student_id": sid, "event": "first_task_viewed"}
        assert (await client.post("/api/activation/events", json=body, headers=h)).json()["recorded"] is True
        assert (await client.post("/api/activation/events", json=body, headers=h)).json()["recorded"] is False
        d = (await client.get(f"/api/activation/me?student_id={sid}", headers=h)).json()
        assert d["checklist"][1]["done"] is True
        bad = await client.post("/api/activation/events", json={**body, "event": "week_approved"}, headers=h)
        assert bad.status_code == 422

    async def test_milestone_card_after_approval(self, client):
        await _cfg(student_ui=True)
        sid, bid = await enrolled(test_db, "m@x.com", days_ago=10)
        await sub(test_db, sid, bid, 1, days_ago=4)
        d = (await client.get(f"/api/activation/me?student_id={sid}", headers=auth_headers(sid, "m@x.com"))).json()
        assert d["stage"] == "stuck_week_1" and d["milestone"]["next_week"] == 2 and d["milestone"]["remaining"] == 3

    async def test_support_is_rate_limited(self, client):
        sid, _ = await enrolled(test_db, "r@x.com")
        h = auth_headers(sid, "r@x.com")
        codes = [(await client.post("/api/activation/support", headers=h, json={"student_id": sid, "message": "x"})).status_code
                 for _ in range(4)]
        assert codes == [200, 200, 200, 429]


class TestPublicRoutes:
    async def test_click_redirects_and_records_once(self, client):
        from services import engagement_service as eng
        monkey = settings.engagement_live_allowed
        settings.engagement_live_allowed = True
        try:
            sid, _ = await enrolled(test_db, "c@x.com")
            await _cfg(mode="live", holdout_pct=0)
            await eng.send_manual([sid], throttle=0)
        finally:
            settings.engagement_live_allowed = monkey
        token = (await test_db.fetch_one("SELECT token FROM engagement_reminders WHERE status='sent'"))["token"]
        for _ in range(2):
            r = await client.get(f"/r/{token}", follow_redirects=False)
            assert r.status_code == 302 and "/dashboard" in r.headers["location"]
        assert (await client.get("/r/unknown", follow_redirects=False)).status_code == 302
        n = await test_db.fetch_one("SELECT COUNT(*) AS n FROM student_events WHERE event_type='reminder_clicked'")
        assert n["n"] == 1

    async def test_unsubscribe_needs_valid_signature_and_post(self, client):
        from services import engagement_service as eng
        sig = eng.unsubscribe_sig("u@x.com")
        assert (await client.get("/api/engagement/unsubscribe?e=u@x.com&s=bad")).status_code == 400
        assert (await client.post("/api/engagement/unsubscribe?e=u@x.com&s=bad")).status_code == 400
        # A GET (e.g. a mail scanner prefetch) must NOT unsubscribe anyone
        assert (await client.get(f"/api/engagement/unsubscribe?e=u@x.com&s={sig}")).status_code == 200
        assert await eng.suppression_reason("u@x.com") is None
        assert (await client.post(f"/api/engagement/unsubscribe?e=u@x.com&s={sig}")).status_code == 200
        assert await eng.suppression_reason("u@x.com") == "opted_out"


async def _journey(client, admin_headers, tag):
    """apply -> shortlist -> enroll -> OTP login -> submit W1-4 -> approve each. Returns a comparable fingerprint."""
    email = f"journey-{tag}@x.com"
    fp = []
    r = await client.post("/api/students/apply", json={"first_name": "J", "last_name": "R", "email": email, "domain": "python"})
    fp.append(("apply", r.status_code)); sid = r.json()["student_id"]
    r = await client.patch(f"/api/admin/students/{sid}/status", json={"status": "shortlisted"}, headers=admin_headers)
    fp.append(("shortlist", r.status_code))
    r = await client.post(f"/api/admin/students/{sid}/enroll", headers=admin_headers)
    fp.append(("enroll", r.status_code))
    await seed_otp(test_db, email, "123456")
    r = await client.post("/api/auth/verify-otp", json={"email": email, "otp": "123456"})
    fp.append(("login", r.status_code, r.json()["status"]))
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    for w in (1, 2, 3, 4):
        r = await client.post("/api/students/submit-task", headers=h, json={
            "student_id": sid, "week": w, "linkedin_url": f"https://www.linkedin.com/posts/j-r_activity-{w}"})
        fp.append((f"submit{w}", r.status_code, r.json().get("status")))
        sub_id = (await test_db.fetch_one("SELECT id FROM submissions WHERE student_id=? AND week=?", (sid, w)))["id"]
        r = await client.post(f"/api/admin/submissions/{sub_id}/approve", json={}, headers=admin_headers)
        fp.append((f"approve{w}", r.status_code))
    r = await client.get(f"/api/students/progress/id/{sid}", headers=h)
    summ = r.json()["summary"]
    fp.append(("progress", r.status_code, summ.get("completion_pct")))
    for t, cols in (("submissions", "week,status,attempts"), ("enrollments", "status"), ("progress", "week,issues_completed,score")):
        rows = await test_db.fetch_all(f"SELECT {cols} FROM {t} ORDER BY id")
        fp.append((t, [tuple(x.values()) for x in rows]))
    return fp


class TestCoreJourneyUnchanged:
    """The whole student/admin journey must behave identically with every activation feature off or on."""

    async def test_identical_with_activation_off_dry_run_and_student_ui(self, client, admin_headers):
        baseline = await _journey(client, admin_headers, "a")
        assert dict((k[0], k[1]) for k in baseline)["approve4"] == 200
        assert [x for x in baseline if x[0] == "progress"][0][2] == 100
        test_db.reset()
        await _cfg(mode="dry_run", student_ui=True)
        with_features = await _journey(client, admin_headers, "a")
        assert with_features == baseline
        ev = {r["event_type"] for r in await test_db.fetch_all("SELECT event_type FROM student_events")}
        assert {"enrollment_created", "first_verified_login", "first_task_submitted", "week_approved",
                "internship_completed"} <= ev

    async def test_core_journey_survives_a_broken_activation_layer(self, client, admin_headers, monkeypatch):
        from services import activation_events as ev

        class BrokenDb:
            def __getattr__(self, name):
                async def boom(*a, **k):
                    raise RuntimeError("activation tables unavailable")
                return boom
        monkeypatch.setattr(ev, "db", BrokenDb())  # only the activation recorder is broken, core DB is fine
        fp = await _journey(client, admin_headers, "b")
        assert all(x[1] == 200 for x in fp if isinstance(x[1], int))
