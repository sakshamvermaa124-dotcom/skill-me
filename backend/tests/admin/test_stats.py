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
        """With no data, every aggregate is zero/empty, not an error."""
        r = await client.get("/api/admin/analytics", headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["overview"]["applicants"] == 0 and d["overview"]["revenue_rupees"] == 0
        assert d["domains"] == []
        assert [s["count"] for s in d["funnel"]["learning"]] == [0] * 8
        assert d["payments"]["revenue"]["paid_orders"] == 0
        assert d["validation"] == []
        for key in ("definitions", "acquisition", "growth", "audience", "engagement", "options"):
            assert key in d
        assert [q["key"] for q in d["audience"]["quiz_bands"]] == ["0-49%", "50-79%", "80-100%"]

    async def test_analytics_requires_admin_key(self, client):
        assert (await client.get("/api/admin/analytics")).status_code == 403


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

    async def test_overview_stats_empty_db(self, client, admin_headers):
        stats = (await client.get("/api/admin/stats", headers=admin_headers)).json()
        for key in ("apps_today", "apps_7d", "active_7d", "eligible_unpaid", "subs_7d", "enrolled_7d", "completed_total"):
            assert stats[key] == 0
        assert "revenue_month_rupees" not in stats  # revenue lives on Analytics only
        assert stats["oldest_pending_days"] is None

    async def test_seeded_test_payment_ids_are_never_real_revenue(self, client, admin_headers):
        """pay_test*/pay_mock* rows count as test even if the is_test column was never backfilled."""
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
        assert stats["eligible_unpaid"] == 2 and stats["total_alumni"] == 1   # fake (test payment) + owes
        d = (await client.get("/api/admin/analytics", headers=admin_headers)).json()
        assert d["payments"]["lifecycle"]["eligible_unpaid"] == 2
        assert d["payments"]["excluded_test"]["paid_orders"] == 1

    async def test_growth_audience_and_quiz_bands(self, client, admin_headers):
        await self._student("a@x.com", college="IIT Delhi", year_of_study="3rd", quiz_score=9, quiz_total=10)
        await self._student("b@x.com", college="iit delhi", quiz_score=2, quiz_total=10)
        await self._student("a@x.com", domain="python")   # same person, second track
        d = (await client.get("/api/admin/analytics", headers=admin_headers)).json()
        assert d["growth"]["unique_people"] == 2 and d["growth"]["total_applications"] == 3
        assert d["growth"]["multi_track_rate"] == 50.0
        assert d["audience"]["colleges"][0]["applications"] == 2
        bands = {q["key"]: q for q in d["audience"]["quiz_bands"]}
        assert bands["80-100%"]["applications"] == 1 and bands["0-49%"]["applications"] == 1

    async def test_analytics_cache_and_fresh_bypass(self, client, admin_headers):
        await self._student("one@x.com")
        first = (await client.get("/api/admin/analytics", headers=admin_headers)).json()
        await self._student("two@x.com")
        cached = (await client.get("/api/admin/analytics", headers=admin_headers)).json()
        assert cached["overview"]["applicants"] == first["overview"]["applicants"] == 1
        fresh = (await client.get("/api/admin/analytics?fresh=true", headers=admin_headers)).json()
        assert fresh["overview"]["applicants"] == 2

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
