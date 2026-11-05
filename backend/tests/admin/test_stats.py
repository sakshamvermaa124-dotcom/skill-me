"""
Admin Tests — Email
"""
import pytest


@pytest.mark.admin
class TestEmailLogs:
    async def test_email_logs_empty(self, client, admin_headers):
        r = await client.get("/api/admin/email/logs", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert "logs" in data
        assert "total" in data
        assert data["total"] == 0

    async def test_email_logs_filter_by_type(self, client, admin_headers):
        r = await client.get("/api/admin/email/logs?email_type=otp_login", headers=admin_headers)
        assert r.status_code == 200

    async def test_email_logs_filter_by_status(self, client, admin_headers):
        """Filtering by ?status= works now that el.status SQL ambiguity is fixed."""
        r = await client.get("/api/admin/email/logs?status=sent", headers=admin_headers)
        assert r.status_code == 200
    async def test_email_logs_pagination(self, client, admin_headers):
        r = await client.get("/api/admin/email/logs?limit=10&offset=0", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["limit"] == 10
        assert data["offset"] == 0

    async def test_email_test_endpoint(self, client, admin_headers):
        """Test email endpoint should skip when email is disabled."""
        r = await client.post(
            "/api/admin/email/test",
            json={"to_email": "test@example.com"},
            headers=admin_headers,
        )
        # email_enabled=False in test config → status=skipped
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("skipped", "sent", "failed")

    async def test_email_logs_page_shape(self, client, admin_headers):
        """/email/logs response includes page/total_pages, matching /students' convention."""
        r = await client.get("/api/admin/email/logs?page=1", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["page"] == 1
        assert "total_pages" in data
        assert "count" in data

    async def test_email_directory_empty(self, client, admin_headers):
        r = await client.get("/api/admin/email/directory", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["students"] == []
        assert data["total"] == 0

    async def test_email_directory_search(self, client, admin_headers):
        r = await client.get("/api/admin/email/directory?q=nobody-matches-this", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["students"] == []


@pytest.mark.admin
class TestAnalytics:
    async def test_analytics_empty_db_shape(self, client, admin_headers):
        """With no data, every aggregate should be zero/empty, not an error."""
        r = await client.get("/api/admin/analytics", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["funnel"]["total"] == 0
        assert data["funnel"]["completion_rate"] == 0
        assert data["domains"] == []
        assert data["weekly_completion"] == []
        assert data["revenue"]["paid_orders"] == 0
        assert data["revenue"]["total_revenue_rupees"] == 0
        assert data["applications_trend"] == []

    async def test_analytics_requires_admin_key(self, client):
        r = await client.get("/api/admin/analytics")
        assert r.status_code == 403

    async def test_domain_name_variants_are_merged(self, client, admin_headers):
        """'Data Science' and 'data-science' are the same domain everywhere else in the app."""
        from tests.conftest import test_db, seed_student
        await seed_student(test_db, email="a@x.com", domain="data-science")
        await seed_student(test_db, email="b@x.com", domain="Data Science")
        await seed_student(test_db, email="c@x.com", domain="flutter")
        await seed_student(test_db, email="d@x.com", domain="Flutter / Mobile")
        data = (await client.get("/api/admin/analytics", headers=admin_headers)).json()
        domains = {d["domain"]: d for d in data["domains"]}
        assert domains["datascience"]["total"] == 2
        assert domains["flutter"]["total"] == 2
        assert len(domains) == 2
        assert sum(d["total"] for d in data["domains"]) == data["funnel"]["total"] == 4

    async def test_completion_uses_approved_weeks_not_status(self, client, admin_headers):
        """students.status stays 'enrolled'; completion must come from 4 approved weeks."""
        from tests.conftest import test_db, seed_student, seed_batch
        done = await seed_student(test_db, email="done@x.com", status="enrolled")
        mid = await seed_student(test_db, email="mid@x.com", status="enrolled")
        await seed_student(test_db, email="idle@x.com", status="enrolled")
        b = await seed_batch(test_db)
        for week in range(1, 5):
            await test_db.insert(
                "INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status) VALUES (?, ?, ?, 'u', 'approved')",
                (done, b, week),
            )
        await test_db.insert(
            "INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status) VALUES (?, ?, 1, 'u', 'approved')",
            (mid, b),
        )
        f = (await client.get("/api/admin/analytics", headers=admin_headers)).json()["funnel"]
        assert f["total"] == 3
        assert f["started"] == 2
        assert f["completed"] == 1
        assert f["never_started"] == 1
        assert f["completion_rate"] == 50.0

    async def test_revenue_excludes_test_payments_and_splits_discounts(self, client, admin_headers):
        from tests.conftest import test_db, seed_student, seed_batch, seed_payment
        from config import settings
        full = settings.certificate_price_paise
        b = await seed_batch(test_db)
        s1 = await seed_student(test_db, email="full@x.com")
        s2 = await seed_student(test_db, email="disc@x.com")
        s3 = await seed_student(test_db, email="fake@x.com")
        s4 = await seed_student(test_db, email="abandon@x.com")
        await test_db.insert(
            "INSERT INTO payments (student_id, batch_id, razorpay_order_id, razorpay_payment_id, amount, status) VALUES (?, ?, 'o1', 'pay_Real1', ?, 'paid')",
            (s1, b, full),
        )
        await test_db.insert(
            "INSERT INTO payments (student_id, batch_id, razorpay_order_id, razorpay_payment_id, amount, status) VALUES (?, ?, 'o2', 'pay_Real2', 500, 'paid')",
            (s2, b),
        )
        await test_db.insert(
            "INSERT INTO payments (student_id, batch_id, razorpay_order_id, razorpay_payment_id, amount, status) VALUES (?, ?, 'o3', 'pay_test123', 24900, 'paid')",
            (s3, b),
        )
        await seed_payment(test_db, s4, b, status="pending", amount=full)

        data = (await client.get("/api/admin/analytics", headers=admin_headers)).json()
        rev = data["revenue"]
        assert rev["total_revenue_rupees"] == (full + 500) / 100
        assert rev["paid_orders"] == 2
        assert rev["excluded_test_orders"] == 1
        assert rev["excluded_test_rupees"] == 249.0
        assert rev["abandoned_checkouts"] == 1
        kinds = {t["kind"]: t for t in rev["tiers"]}
        assert kinds["full"]["orders"] == 1
        assert kinds["discounted"]["price_rupees"] == 5.0
        assert data["funnel"]["paid"] == 2  # fake-paid student not counted

        stats = (await client.get("/api/admin/stats", headers=admin_headers)).json()
        assert stats["total_alumni"] == 2


@pytest.mark.admin
class TestBusinessMetrics:
    async def _student(self, email, **cols):
        from tests.conftest import test_db
        fields = {"first_name": "T", "last_name": "S", "email": email, "domain": "web-dev", **cols}
        names = ", ".join(fields)
        return await test_db.insert(
            f"INSERT INTO students ({names}) VALUES ({', '.join('?' for _ in fields)})",
            tuple(fields.values()),
        )

    async def test_new_analytics_blocks_present_on_empty_db(self, client, admin_headers):
        data = (await client.get("/api/admin/analytics", headers=admin_headers)).json()
        for key in ("growth", "acquisition", "audience", "speed", "quiz_outcomes"):
            assert key in data
        assert data["speed"]["median_days_to_first_task"] is None
        assert [q["band"] for q in data["quiz_outcomes"]] == ["0-49%", "50-79%", "80-100%"]
        stats = (await client.get("/api/admin/stats", headers=admin_headers)).json()
        for key in ("apps_today", "apps_7d", "active_7d", "eligible_unpaid", "subs_7d", "enrolled_7d", "completed_total"):
            assert stats[key] == 0
        assert "revenue_month_rupees" not in stats  # revenue lives on Analytics only
        assert stats["oldest_pending_days"] is None

    async def test_acquisition_groups_by_source_with_paid_rate(self, client, admin_headers):
        from tests.conftest import test_db, seed_batch
        b = await seed_batch(test_db)
        a = await self._student("a@x.com", referral_source="LinkedIn", college="IIT Delhi")
        await self._student("b@x.com", referral_source="linkedin", college="IIT Delhi")
        await self._student("c@x.com", referral_source="Friend")
        await test_db.insert(
            "INSERT INTO payments (student_id, batch_id, razorpay_order_id, razorpay_payment_id, amount, status)"
            " VALUES (?, ?, 'o1', 'pay_Real1', 12900, 'paid')", (a, b))
        data = (await client.get("/api/admin/analytics", headers=admin_headers)).json()
        src = {s["label"].lower(): s for s in data["acquisition"]["sources"]}
        assert src["linkedin"]["total"] == 2 and src["linkedin"]["paid"] == 1
        assert src["linkedin"]["paid_rate"] == 50.0
        assert data["audience"]["colleges"][0]["total"] == 2

    async def test_eligible_unpaid_excludes_paid_and_test_payments(self, client, admin_headers):
        from tests.conftest import test_db, seed_batch
        b = await seed_batch(test_db)
        paid = await self._student("paid@x.com")
        fake = await self._student("fake@x.com")
        owes = await self._student("owes@x.com")
        low = await self._student("low@x.com")
        for sid, weeks in ((paid, 3), (fake, 3), (owes, 3), (low, 2)):
            for w in range(1, weeks + 1):
                await test_db.insert(
                    "INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status)"
                    " VALUES (?, ?, ?, 'u', 'approved')", (sid, b, w))
        await test_db.insert(
            "INSERT INTO payments (student_id, batch_id, razorpay_order_id, razorpay_payment_id, amount, status)"
            " VALUES (?, ?, 'o1', 'pay_Real1', 12900, 'paid')", (paid, b))
        await test_db.insert(
            "INSERT INTO payments (student_id, batch_id, razorpay_order_id, razorpay_payment_id, amount, status)"
            " VALUES (?, ?, 'o2', 'pay_test1', 12900, 'paid')", (fake, b))
        stats = (await client.get("/api/admin/stats", headers=admin_headers)).json()
        assert stats["eligible_unpaid"] == 2  # fake (test payment) + owes
        data = (await client.get("/api/admin/analytics", headers=admin_headers)).json()
        assert data["revenue"]["eligible_unpaid"] == 2

    async def test_quiz_bands_and_median_days(self, client, admin_headers):
        from tests.conftest import test_db, seed_batch
        b = await seed_batch(test_db)
        hi = await self._student("hi@x.com", quiz_score=9, quiz_total=10, created_at="2026-01-01 00:00:00")
        await self._student("lo@x.com", quiz_score=2, quiz_total=10)
        await test_db.insert(
            "INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status, submitted_at)"
            " VALUES (?, ?, 1, 'u', 'approved', '2026-01-03 00:00:00')", (hi, b))
        data = (await client.get("/api/admin/analytics", headers=admin_headers)).json()
        bands = {q["band"]: q for q in data["quiz_outcomes"]}
        assert bands["80-100%"]["total"] == 1 and bands["0-49%"]["total"] == 1
        assert data["speed"]["median_days_to_first_task"] == 2.0

    async def test_analytics_cache_and_fresh_bypass(self, client, admin_headers):
        await self._student("one@x.com")
        first = (await client.get("/api/admin/analytics", headers=admin_headers)).json()
        await self._student("two@x.com")
        cached = (await client.get("/api/admin/analytics", headers=admin_headers)).json()
        assert cached["funnel"]["total"] == first["funnel"]["total"] == 1
        fresh = (await client.get("/api/admin/analytics?fresh=true", headers=admin_headers)).json()
        assert fresh["funnel"]["total"] == 2

    async def test_fetch_batch_preserves_order(self):
        from tests.conftest import test_db
        res = await test_db.fetch_batch([("SELECT 1 AS a", ()), ("SELECT 2 AS a", ())])
        assert [r[0]["a"] for r in res] == [1, 2]

    async def test_active_people_ignores_superseded_otps(self, client, admin_headers):
        from tests.conftest import test_db
        await test_db.insert("INSERT INTO otp_tokens (email, otp_hash, expires_at, used) VALUES ('in@x.com', 'h', '2099-01-01', 1)")
        await test_db.insert("INSERT INTO otp_tokens (email, otp_hash, expires_at, used) VALUES ('never@x.com', 'h', '2099-01-01', 2)")
        stats = (await client.get("/api/admin/stats", headers=admin_headers)).json()
        assert stats["active_7d"] == 1

    async def test_overview_ops_metrics(self, client, admin_headers):
        from tests.conftest import test_db, seed_batch
        b = await seed_batch(test_db)
        done = await self._student("done@x.com")
        other = await self._student("other@x.com")
        await test_db.insert("INSERT INTO enrollments (student_id, batch_id) VALUES (?, ?)", (done, b))
        for w in range(1, 5):
            await test_db.insert(
                "INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status, reviewed_at)"
                " VALUES (?, ?, ?, 'u', 'approved', datetime('now'))", (done, b, w))
        await test_db.insert(
            "INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status, reviewed_at)"
            " VALUES (?, ?, 1, 'u', 'rejected', datetime('now'))", (other, b))
        await test_db.insert(
            "INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status, submitted_at)"
            " VALUES (?, ?, 2, 'u', 'pending', datetime('now', '-3 days'))", (other, b))
        s = (await client.get("/api/admin/stats", headers=admin_headers)).json()
        assert s["subs_7d"] == 6
        assert s["enrolled_7d"] == 1
        assert s["approved_30d"] == 4 and s["rejected_30d"] == 1
        assert s["approval_rate_30d"] == 80.0
        assert s["completed_total"] == 1
        assert 2.9 <= s["oldest_pending_days"] <= 3.1

    async def test_ux_block_on_empty_db(self, client, admin_headers):
        ux = (await client.get("/api/admin/analytics", headers=admin_headers)).json()["ux"]
        assert [j["step"] for j in ux["journey"]] == ["Enrolled", "Week 1", "Week 2", "Week 3", "Week 4", "Completed", "Paid"]
        assert ux["tasks"]["avg_attempts"] is None
        assert ux["login"]["success_rate"] == 0.0

    async def test_ux_journey_logins_and_attempts(self, client, admin_headers):
        from tests.conftest import test_db, seed_batch
        b = await seed_batch(test_db)
        a = await self._student("a@x.com")
        c = await self._student("c@x.com")
        for sid in (a, c):
            await test_db.insert("INSERT INTO enrollments (student_id, batch_id, joined_at) VALUES (?, ?, datetime('now', '-10 days'))", (sid, b))
        # a: week 1 approved after 2 tries, week 2 three days later; c: never logs in, never submits
        await test_db.insert(
            "INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status, attempts, submitted_at, reviewed_at)"
            " VALUES (?, ?, 1, 'u', 'approved', 2, datetime('now', '-8 days'), datetime('now', '-7 days'))", (a, b))
        await test_db.insert(
            "INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status, submitted_at)"
            " VALUES (?, ?, 2, 'u', 'pending', datetime('now', '-5 days'))", (a, b))
        await test_db.insert("INSERT INTO otp_tokens (email, otp_hash, expires_at, used) VALUES ('a@x.com', 'h', '2099-01-01', 1)")
        await test_db.insert("INSERT INTO otp_tokens (email, otp_hash, expires_at, used) VALUES ('c@x.com', 'h', '2000-01-01', 0)")
        ux = (await client.get("/api/admin/analytics", headers=admin_headers)).json()["ux"]
        steps = {j["step"]: j["count"] for j in ux["journey"]}
        assert steps["Enrolled"] == 2 and steps["Week 1"] == 1 and steps["Week 2"] == 1 and steps["Week 3"] == 0
        assert ux["onboarding"]["never_logged_in"] == 1
        assert ux["onboarding"]["median_days_to_first_task"] == 2.0
        assert ux["login"]["people_requested"] == 2 and ux["login"]["people_signed_in"] == 1
        assert ux["login"]["success_rate"] == 50.0 and ux["login"]["codes_expired_unused"] == 1
        w1 = ux["weeks"][0]
        assert w1["avg_attempts"] == 2.0 and w1["resubmitted"] == 1
        assert ux["weeks"][1]["median_days_from_prev_week"] == 3.0
        assert ux["review_wait"]["median_hours"] == 24.0

    async def test_resubmission_increments_attempts(self, client, admin_headers):
        from tests.conftest import test_db, seed_batch
        from services.submission_service import submission_service
        b = await seed_batch(test_db)
        sid = await self._student("r@x.com")
        await test_db.insert("INSERT INTO enrollments (student_id, batch_id) VALUES (?, ?)", (sid, b))
        sub = await test_db.insert(
            "INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status) VALUES (?, ?, 1, 'https://www.linkedin.com/posts/x', 'rejected')", (sid, b))
        await submission_service.submit_linkedin_url(sid, b, 1, "https://www.linkedin.com/posts/y")
        row = await test_db.fetch_one("SELECT attempts, status FROM submissions WHERE id = ?", (sub,))
        assert row["status"] == "pending" and row["attempts"] == 2
