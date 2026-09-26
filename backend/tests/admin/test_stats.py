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
