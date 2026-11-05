"""
Analytics definitions — one seeded world mirroring the production inconsistencies, with the
expected number for every metric worked out by hand.

World (all non-test applicants applied 2026-02-01 10:00 UTC; enrolled students joined 02-03,
signed in 02-04, submitted week 1 on 02-06 — so the timing medians are exact):

  A  web-dev  4/4 approved, paid ₹129 (real), certificate via payment, attribution linkedin / nov-push
  B  web-dev  3/4 approved, paid ₹129 (real), certificate via payment, attribution google
  C  python   2/4 approved, ₹5 TEST payment, certificate (legacy, issued_via NULL)
  D  python   4/4 approved, one legacy 'pending' order (no initiated_at), attribution captured but direct
  E  python   3/4 approved, never opened checkout
  K  python   3/4 approved, latest order FAILED ("card declined")
  G  ml       enrolled, never signed in, no task
  F  ml       applied only (applied 2026-01-10 20:00 UTC = 2026-01-11 IST)
  I  "Data Science", J "data-science": applied only (same track, two spellings)
  L  web-dev  enrolled, no task, certificate issued by an admin (no payment)
  H  ml       TEST account, 4/4 approved (excluded unless include_test)
"""
import pytest

URL = "/api/admin/analytics"


async def _world():
    from tests.conftest import test_db as db, seed_batch

    async def student(email, domain, created="2026-02-01 10:00:00", **cols):
        f = {"first_name": email[0].upper(), "last_name": "Test", "email": f"{email}@x.com",
             "domain": domain, "created_at": created, **cols}
        return await db.insert(
            f"INSERT INTO students ({', '.join(f)}) VALUES ({', '.join('?' for _ in f)})", tuple(f.values()))

    counter = iter(range(1, 100))

    async def enroll(sid, unlocked=None):
        b = await seed_batch(db, batch_number=next(counter))   # one private batch per enrollment
        await db.insert(
            "INSERT INTO enrollments (student_id, batch_id, joined_at, payment_unlocked_at) VALUES (?, ?, '2026-02-03 10:00:00', ?)",
            (sid, b, unlocked))
        return b

    async def login(sid_email):
        await db.insert(
            "INSERT INTO otp_tokens (email, otp_hash, expires_at, used, created_at) VALUES (?, 'h', '2099-01-01', 1, '2026-02-04 10:00:00')",
            (sid_email,))

    async def approve(sid, b, weeks):
        for w in range(1, weeks + 1):
            sub = f"2026-02-{6 + (w - 1) * 7:02d} 10:00:00"
            rev = f"2026-02-{7 + (w - 1) * 7:02d} 10:00:00"
            await db.insert(
                "INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status, submitted_at, reviewed_at)"
                " VALUES (?, ?, ?, 'u', 'approved', ?, ?)", (sid, b, w, sub, rev))

    async def pay(sid, b, order, status, amount=12900, payment_id=None, is_test=0, initiated=None, reason=None,
                  created="2026-02-20 10:00:00"):
        return await db.insert(
            "INSERT INTO payments (student_id, batch_id, razorpay_order_id, razorpay_payment_id, amount, status,"
            " is_test, initiated_at, completed_at, failure_reason, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (sid, b, order, payment_id, amount, status, is_test, initiated,
             created if status == "paid" and initiated else None, reason, created, created))

    async def cert(sid, b, cid, via):
        await db.insert("INSERT INTO certificates (student_id, batch_id, cert_id, issued_via) VALUES (?,?,?,?)", (sid, b, cid, via))

    w = {}
    attr = lambda src, camp=None: dict(attribution_captured=1, first_touch_source=src, last_touch_source=src,
                                       utm_campaign=camp, utm_source=src if camp else None)
    w["A"] = await student("a", "web-dev", **attr("linkedin", "nov-push"))
    w["B"] = await student("b", "web-dev", **attr("google"))
    w["C"] = await student("c", "python")
    w["D"] = await student("d", "python", **attr(None))
    w["E"] = await student("e", "python")
    w["K"] = await student("k", "python")
    w["G"] = await student("g", "ml")
    w["F"] = await student("f", "ml", created="2026-01-10 20:00:00")
    w["I"] = await student("i", "Data Science")
    w["J"] = await student("j", "data-science")
    w["L"] = await student("l", "web-dev")
    w["H"] = await student("h", "ml", is_test=1)

    plan = {"A": 4, "B": 3, "C": 2, "D": 4, "E": 3, "K": 3, "H": 4}
    b = {}
    for k in ("A", "B", "C", "D", "E", "K", "G", "L", "H"):
        b[k] = await enroll(w[k])
        if k not in ("G", "L"):
            await login(f"{k.lower()}@x.com")
    for k, n in plan.items():
        await approve(w[k], b[k], n)
    # L and G have no tasks; only the logins above give started
    await pay(w["A"], b["A"], "oA", "paid", payment_id="pay_RealA", initiated="2026-02-20 10:00:00")
    await pay(w["B"], b["B"], "oB", "paid", payment_id="pay_RealB", initiated="2026-02-21 10:00:00")
    await pay(w["C"], b["C"], "oC", "paid", amount=500, payment_id="pay_RealC", is_test=1, initiated="2026-02-22 10:00:00")
    await pay(w["D"], b["D"], "oD", "pending")  # legacy: no initiated_at
    await pay(w["K"], b["K"], "oK", "failed", initiated="2026-02-23 10:00:00", reason="card declined")
    await cert(w["A"], b["A"], "SM-AAAA", "payment")
    await cert(w["B"], b["B"], "SM-BBBB", "payment")
    await cert(w["C"], b["C"], "SM-CCCC", None)
    await cert(w["L"], b["L"], "SM-LLLL", "admin")
    return w, b


@pytest.fixture
async def world(client):
    return await _world()


async def get(client, headers, qs=""):
    r = await client.get(f"{URL}?fresh=true{qs}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.admin
class TestDefinitions:
    async def test_overview_counts_students_not_tasks(self, client, admin_headers, world):
        d = await get(client, admin_headers)
        o = d["overview"]
        assert o["applicants"] == 11 and o["unique_people"] == 11     # test account H excluded
        assert o["enrolled"] == 8
        assert o["completed"] == 2                                     # A, D   (NOT 84-style task counts)
        assert o["certificates"] == 4                                  # A, B, C, L
        assert o["paying_students"] == 2                               # A, B  (C's payment is a test)
        assert o["revenue_rupees"] == 258.0
        assert o["eligible_unpaid"] == 3                               # D, E, K
        # task-level numbers live elsewhere and are labelled as submissions
        t = d["engagement"]["task_level"]
        assert t["approved_submissions"] == 4 + 3 + 2 + 4 + 3 + 3 == 19
        assert "submissions" in t["unit"]

    async def test_learning_funnel(self, client, admin_headers, world):
        f = {r["key"]: r for r in (await get(client, admin_headers))["funnel"]["learning"]}
        assert [f[k]["count"] for k in ("applied", "enrolled", "started", "first_task", "week1", "week2", "week3", "completed")] \
            == [11, 8, 6, 6, 6, 6, 5, 2]
        assert f["enrolled"]["step_conversion"] == round(8 * 100 / 11, 1)
        assert f["enrolled"]["drop_off"] == 3 and f["enrolled"]["drop_off_pct"] == round(3 * 100 / 11, 1)
        assert f["completed"]["step_conversion"] == round(2 * 100 / 5, 1)

    async def test_revenue_funnel_is_nested_and_reconciles_certified_vs_completed(self, client, admin_headers, world):
        d = await get(client, admin_headers)
        r = {x["key"]: x["count"] for x in d["funnel"]["revenue"]}
        # eligible: A, B, D, E, K   checkout among eligible: A, B, D, K   paid: A, B   certified after paying: A, B
        assert r == {"eligible": 5, "checkout": 4, "paid": 2, "certified": 2}
        # the three certificate-vs-completed gaps are explained, never hidden
        v = {w["code"]: w for w in d["validation"]}
        assert v["cert_before_completion"]["count"] == 3   # B (3/4), C (2/4), L (0/4)
        assert v["cert_without_payment"]["count"] == 2     # C (test payment), L (admin)
        dom = {x["key"]: x for x in d["domains"]}
        assert dom["web-dev"]["certified_not_completed"] == 2   # B, L

    async def test_payment_lifecycle_states(self, client, admin_headers, world):
        p = (await get(client, admin_headers))["payments"]
        life = p["lifecycle"]
        assert life["eligible"] == 5 and life["eligible_unpaid"] == 3
        assert life["eligible_never_started_checkout"] == 1            # E
        assert life["checkout_initiated"] == 4                          # A, B, D, K (C is test)
        assert life["paid"] == 2 and life["failed"] == 1
        assert life["abandoned"] == 1 and life["abandoned_legacy_unknown"] == 1   # D
        assert life["pending"] == 0
        assert p["excluded_test"] == {"paid_orders": 1, "rupees": 5.0}
        assert p["revenue"]["total_rupees"] == 258.0 and p["revenue"]["paid_orders"] == 2
        assert [x["name"][0] for x in p["recovery"]["failed"]] == ["K"]
        assert p["recovery"]["failed"][0]["failure_reason"] == "card declined"
        assert {x["name"][0] for x in p["recovery"]["eligible_unpaid"]} == {"D", "E", "K"}

    async def test_timings_name_their_start_point(self, client, admin_headers, world):
        t = {(x["from"], x["to"]): x for x in (await get(client, admin_headers))["funnel"]["timings"]}
        # two different "first task" durations, now explicit instead of two conflicting medians
        assert t[("Application", "First task")]["median_days"] == 5.0
        assert t[("Enrollment", "First task")]["median_days"] == 3.0
        assert t[("Application", "Enrollment")]["median_days"] == 2.0
        assert t[("Enrollment", "First login")]["median_days"] == 1.0

    async def test_domains_merge_spellings_and_add_up(self, client, admin_headers, world):
        d = await get(client, admin_headers)
        dom = {x["key"]: x for x in d["domains"]}
        assert dom["datascience"]["applications"] == 2
        assert sum(x["applications"] for x in d["domains"]) == d["overview"]["applicants"]
        py = dom["python"]
        assert (py["applications"], py["completed"], py["paid"], py["certified"]) == (4, 1, 0, 1)
        assert [r["reached"] for r in py["retention"]] == [4, 4, 3, 1]  # wk1: C,D,E,K  wk3: D,E,K  wk4: D
        assert not [w for w in d["validation"] if w["code"] == "domain_sum_mismatch"]

    async def test_acquisition_separates_pre_tracking_from_direct(self, client, admin_headers, world):
        a = (await get(client, admin_headers))["acquisition"]
        src = {s["key"]: s for s in a["sources"]}
        assert src["linkedin"]["applications"] == 1 and src["linkedin"]["paid"] == 1
        assert src["google"]["paid"] == 1
        assert src["direct"]["applications"] == 1                       # D: tracked, no campaign
        assert src["unknown (pre-tracking)"]["applications"] == 8
        assert a["coverage"]["tracked"] == 3 and a["coverage"]["pre_tracking_unknown"] == 8
        camp = {c["key"]: c for c in a["campaigns"]}
        assert camp["linkedin / nov-push"]["applications"] == 1 and camp["linkedin / nov-push"]["completed"] == 1

    async def test_engagement_and_inactive(self, client, admin_headers, world):
        e = (await get(client, admin_headers))["engagement"]
        assert e["never_logged_in"] == 2                                # G, L
        assert e["enrolled_no_task"] == 2
        wk = {x["week"]: x for x in e["weekly"]}
        assert wk[1]["students_approved"] == 6 and wk[1]["approved_submissions"] == 6
        assert wk[4]["students_approved"] == 2
        # everyone enrolled but not completed has been silent since February -> all inactive
        ids = {x["name"][0] for x in e["inactive"]}
        assert ids == {"B", "C", "E", "K", "G", "L"} and e["inactive_count"] == 6


@pytest.mark.admin
class TestFiltersAndDrilldown:
    async def test_test_data_excluded_by_default_and_included_on_request(self, client, admin_headers, world):
        assert (await get(client, admin_headers))["overview"]["applicants"] == 11
        inc = await get(client, admin_headers, "&include_test=true")
        assert inc["overview"]["applicants"] == 12 and inc["overview"]["completed"] == 3

    async def test_date_range_is_ist_cohort_filter(self, client, admin_headers, world):
        # F applied 2026-01-10 20:00 UTC == 2026-01-11 01:30 IST
        only_f = await get(client, admin_headers, "&from=2026-01-11&to=2026-01-11")
        assert only_f["overview"]["applicants"] == 1
        before = await get(client, admin_headers, "&to=2026-01-10")
        assert before["overview"]["applicants"] == 0
        feb = await get(client, admin_headers, "&from=2026-02-01&to=2026-02-28")
        assert feb["overview"]["applicants"] == 10

    async def test_domain_and_source_and_campaign_filters(self, client, admin_headers, world):
        py = await get(client, admin_headers, "&domain=python")
        assert py["overview"]["applicants"] == 4 and py["overview"]["paying_students"] == 0
        li = await get(client, admin_headers, "&source=linkedin")
        assert li["overview"]["applicants"] == 1 and li["overview"]["completed"] == 1
        camp = await get(client, admin_headers, "&campaign=nov-push")
        assert camp["overview"]["applicants"] == 1

    async def test_drilldown_matches_every_funnel_count(self, client, admin_headers, world):
        d = await get(client, admin_headers)
        for row in d["funnel"]["learning"] + d["funnel"]["revenue"]:
            r = await client.get(f"{URL}/students?stage={row['key']}", headers=admin_headers)
            assert r.status_code == 200
            assert r.json()["total"] == row["count"], row["key"]
        for stage, expected in (("eligible_unpaid", 3), ("pay_failed", 1), ("pay_abandoned", 1),
                                ("cert_not_paid", 2), ("never_logged_in", 2), ("certified_any", 4)):
            r = (await client.get(f"{URL}/students?stage={stage}", headers=admin_headers)).json()
            assert r["total"] == expected, stage

    async def test_drilldown_respects_filters_and_search_and_paging(self, client, admin_headers, world):
        r = (await client.get(f"{URL}/students?stage=applied&domain=python&limit=2&page=2", headers=admin_headers)).json()
        assert r["total"] == 4 and len(r["students"]) == 2 and r["total_pages"] == 2
        r = (await client.get(f"{URL}/students?stage=applied&q=a@x.com", headers=admin_headers)).json()
        assert [s["email"] for s in r["students"]] == ["a@x.com"]

    async def test_no_student_is_double_counted_with_many_orders_and_logins(self, client, admin_headers, world):
        from tests.conftest import test_db as db
        w, b = world
        for i in range(3):   # extra orders/logins/certificates must not change student counts
            await db.insert("INSERT INTO payments (student_id, batch_id, razorpay_order_id, amount, status, initiated_at) "
                            "VALUES (?, ?, ?, 12900, 'failed', '2026-02-24 10:00:00')", (w["K"], b["K"], f"oKx{i}"))
            await db.insert("INSERT INTO otp_tokens (email, otp_hash, expires_at, used, created_at) VALUES ('k@x.com','h','2099-01-01',1,'2026-02-05 10:00:00')")
        d = await get(client, admin_headers)
        assert d["overview"]["applicants"] == 11 and d["payments"]["lifecycle"]["checkout_initiated"] == 4
        assert d["payments"]["lifecycle"]["failed"] == 1
        assert d["funnel"]["learning"][2]["count"] == 6

    async def test_unknown_stage_and_auth(self, client, admin_headers):
        assert (await client.get(f"{URL}/students?stage=nope", headers=admin_headers)).status_code == 400
        assert (await client.get(f"{URL}/students?stage=applied")).status_code == 403
        assert (await client.get(f"{URL}/data-quality")).status_code == 403


@pytest.mark.admin
class TestQualityJourneyPayments:
    async def test_data_quality_flags_but_changes_nothing(self, client, admin_headers, world):
        from tests.conftest import test_db as db
        before = await db.fetch_one("SELECT COUNT(*) n FROM certificates")
        dq = (await client.get(f"{URL}/data-quality", headers=admin_headers)).json()
        c = {x["key"]: x for x in dq["checks"]}
        assert c["cert_no_real_payment"]["count"] == 2
        assert {i["name"][0] for i in c["cert_no_real_payment"]["items"]} == {"C", "L"}
        assert c["test_payment_accounts"]["count"] == 1
        assert c["duplicate_people"]["count"] == 0
        assert c["missing_attribution"]["count"] == 8
        assert c["legacy_pending_orders"]["count"] == 1
        assert c["cert_invalid_enrollment"]["count"] == 0
        assert dq["problem_count"] >= 2
        assert (await db.fetch_one("SELECT COUNT(*) n FROM certificates")) == before

    async def test_marking_account_test_removes_it_everywhere_without_deleting(self, client, admin_headers, world):
        from tests.conftest import test_db as db
        w, _ = world
        r = await client.patch(f"/api/admin/students/{w['C']}/test-flag", json={"is_test": True}, headers=admin_headers)
        assert r.status_code == 200
        d = await get(client, admin_headers)
        assert d["overview"]["applicants"] == 10 and d["overview"]["certificates"] == 3
        assert (await db.fetch_one("SELECT COUNT(*) n FROM students WHERE id = ?", (w["C"],)))["n"] == 1
        back = await client.patch(f"/api/admin/students/{w['C']}/test-flag", json={"is_test": False}, headers=admin_headers)
        assert back.status_code == 200
        assert (await get(client, admin_headers))["overview"]["applicants"] == 11
        assert (await client.patch("/api/admin/students/9999/test-flag", json={"is_test": True}, headers=admin_headers)).status_code == 404

    async def test_journey_timeline(self, client, admin_headers, world):
        w, _ = world
        j = (await client.get(f"/api/admin/students/{w['A']}/journey", headers=admin_headers)).json()
        types = [e["type"] for e in j["timeline"]]
        assert types[0] == "applied" and "enrolled" in types and "login" in types
        assert types.count("submission") == 4 and types.count("review") == 4
        assert "checkout" in types and "paid" in types and types[-1] == "certificate"
        assert j["student"]["first_touch_source"] == "linkedin"
        assert (await client.get("/api/admin/students/9999/journey", headers=admin_headers)).status_code == 404

    async def test_payments_list_lifecycle_and_test_filter(self, client, admin_headers, world):
        def names(r): return sorted(p["razorpay_order_id"] for p in r["payments"])
        allp = (await client.get("/api/admin/payments", headers=admin_headers)).json()
        assert allp["total"] == 5
        paid = (await client.get("/api/admin/payments?status=paid", headers=admin_headers)).json()
        assert names(paid) == ["oA", "oB"]                              # test order oC excluded
        assert names((await client.get("/api/admin/payments?status=test", headers=admin_headers)).json()) == ["oC"]
        assert names((await client.get("/api/admin/payments?status=abandoned", headers=admin_headers)).json()) == ["oD"]
        failed = (await client.get("/api/admin/payments?status=failed", headers=admin_headers)).json()
        assert failed["payments"][0]["failure_reason"] == "card declined"
        legacy = (await client.get("/api/admin/payments?status=abandoned", headers=admin_headers)).json()["payments"][0]
        assert legacy["legacy"] is True

    async def test_fresh_order_is_pending_not_abandoned_until_it_ages(self, client, admin_headers, world):
        from tests.conftest import test_db as db
        w, b = world
        await db.insert("INSERT INTO payments (student_id, batch_id, razorpay_order_id, amount, status, initiated_at, created_at) "
                        "VALUES (?, ?, 'oFresh', 12900, 'created', datetime('now'), datetime('now'))", (w["E"], b["E"]))
        life = (await get(client, admin_headers))["payments"]["lifecycle"]
        assert life["pending"] == 1 and life["abandoned"] == 1 and life["checkout_initiated"] == 5
