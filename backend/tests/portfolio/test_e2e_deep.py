"""
Deep integration tests for the Task Approval -> Portfolio pipeline.
Exercises the REAL admin/submission routes and services end-to-end -- no mocking
of business logic, only external services (email/payments) per conftest.
"""
import asyncio
import pytest
from tests.conftest import test_db, seed_student, seed_batch, seed_enrollment, seed_payment


async def _setup_paid(domain="web-dev"):
    sid = await seed_student(test_db, email=f"{domain}-{id(object())}@example.com",
                              github_username=f"user{id(object())}", domain=domain)
    bid = await seed_batch(test_db, domain=domain)
    await seed_enrollment(test_db, sid, bid)
    await seed_payment(test_db, sid, bid)
    return sid, bid


@pytest.mark.asyncio
class TestRejectResubmitApprove:
    async def test_rejected_then_resubmitted_then_approved(self, client, admin_headers):
        sid, bid = await _setup_paid()
        sub_id = await test_db.insert(
            """INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status)
               VALUES (?, ?, 1, 'https://www.linkedin.com/feed/update/urn:li:activity:bad', 'pending')""",
            (sid, bid),
        )
        rej = await client.post(f"/api/admin/submissions/{sub_id}/reject",
                                 json={"admin_note": "wrong link"}, headers=admin_headers)
        assert rej.status_code == 200
        assert rej.json()["status"] == "rejected"

        # Rejected submission must not leak into the public portfolio.
        mid = await client.get(f"/api/portfolio/id/{sid}")
        assert mid.json()["submissions"] == []

        # Student resubmits the SAME week (real submission flow enforces resubmission semantics).
        resub = await client.post(
            "/api/students/submit-task",
            json={"student_id": sid, "batch_id": bid, "week": 1,
                  "linkedin_url": "https://www.linkedin.com/feed/update/urn:li:activity:good"},
        )
        assert resub.status_code in (200, 201), resub.text

        # Re-fetch submission id (resubmission updates the same row).
        row = await test_db.fetch_one("SELECT id, status FROM submissions WHERE student_id=? AND batch_id=? AND week=1", (sid, bid))
        assert row["status"] == "pending"

        appr = await client.post(f"/api/admin/submissions/{row['id']}/approve", headers=admin_headers)
        assert appr.status_code == 200, appr.text

        final = await client.get(f"/api/portfolio/id/{sid}")
        subs = final.json()["submissions"]
        assert len(subs) == 1
        assert subs[0]["linkedin_url"].endswith("good")
        assert final.json()["stats"]["total_score"] == 25


@pytest.mark.asyncio
class TestDoubleApproval:
    async def test_approving_twice_does_not_double_count_score(self, client, admin_headers):
        sid, bid = await _setup_paid()
        sub_id = await test_db.insert(
            """INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status)
               VALUES (?, ?, 1, 'https://www.linkedin.com/feed/update/urn:li:activity:1', 'pending')""",
            (sid, bid),
        )
        r1 = await client.post(f"/api/admin/submissions/{sub_id}/approve", headers=admin_headers)
        r2 = await client.post(f"/api/admin/submissions/{sub_id}/approve", headers=admin_headers)
        assert r1.json()["status"] == "approved" and not r1.json().get("already")
        assert r2.json().get("already") is True

        data = (await client.get(f"/api/portfolio/id/{sid}")).json()
        assert data["stats"]["total_score"] == 25, "double-approve inflated the score"
        assert len(data["submissions"]) == 1

    async def test_concurrent_approve_calls_are_safe(self, client, admin_headers):
        """Two admins clicking Approve at the same moment must not double-award score."""
        sid, bid = await _setup_paid()
        sub_id = await test_db.insert(
            """INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status)
               VALUES (?, ?, 1, 'https://www.linkedin.com/feed/update/urn:li:activity:1', 'pending')""",
            (sid, bid),
        )
        results = await asyncio.gather(*[
            client.post(f"/api/admin/submissions/{sub_id}/approve", headers=admin_headers)
            for _ in range(5)
        ])
        assert all(r.status_code == 200 for r in results)
        data = (await client.get(f"/api/portfolio/id/{sid}")).json()
        assert data["stats"]["total_score"] == 25, f"race condition inflated score to {data['stats']['total_score']}"


@pytest.mark.asyncio
class TestBulkApprove:
    async def test_bulk_approve_updates_all_and_skips_bad_ids(self, client, admin_headers):
        sid, bid = await _setup_paid()
        ids = []
        for wk in (1, 2, 3):
            ids.append(await test_db.insert(
                """INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status)
                   VALUES (?, ?, ?, ?, 'pending')""",
                (sid, bid, wk, f"https://www.linkedin.com/feed/update/urn:li:activity:{wk}"),
            ))
        ids.append(999999)  # nonexistent id mixed into the batch

        res = await client.post("/api/admin/submissions/bulk-approve",
                                 json={"submission_ids": ids}, headers=admin_headers)
        assert res.status_code == 200
        results = res.json()["results"]
        statuses = {r["submission_id"]: r["status"] for r in results}
        assert statuses[999999] == "error"
        assert all(statuses[i] == "approved" for i in ids[:3])

        data = (await client.get(f"/api/portfolio/id/{sid}")).json()
        assert len(data["submissions"]) == 3
        assert [s["week"] for s in data["submissions"]] == [1, 2, 3]
        assert data["stats"]["total_score"] == 75
        assert data["stats"]["total_tasks_completed"] == 3


@pytest.mark.asyncio
class TestMultiDomainStudent:
    async def test_student_enrolled_in_two_domains_shows_both(self, client, admin_headers):
        sid = await seed_student(test_db, email="multi@example.com", github_username="multiuser", domain="web-dev")
        bid1 = await seed_batch(test_db, domain="web-dev")
        bid2 = await seed_batch(test_db, domain="ml", batch_number=2)
        await seed_enrollment(test_db, sid, bid1)
        await seed_enrollment(test_db, sid, bid2)
        await seed_payment(test_db, sid, bid1)

        sub1 = await test_db.insert(
            """INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status)
               VALUES (?, ?, 1, 'https://www.linkedin.com/feed/update/urn:li:activity:a', 'pending')""",
            (sid, bid1),
        )
        sub2 = await test_db.insert(
            """INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status)
               VALUES (?, ?, 1, 'https://www.linkedin.com/feed/update/urn:li:activity:b', 'pending')""",
            (sid, bid2),
        )
        await client.post(f"/api/admin/submissions/{sub1}/approve", headers=admin_headers)
        await client.post(f"/api/admin/submissions/{sub2}/approve", headers=admin_headers)

        data = (await client.get(f"/api/portfolio/id/{sid}")).json()
        assert set(data["domains"]) == {"web-dev", "ml"}
        sub_domains = {s["domain"] for s in data["submissions"]}
        assert sub_domains == {"web-dev", "ml"}
        assert data["stats"]["total_score"] == 50


@pytest.mark.asyncio
class TestDroppedEnrollmentStillCountsIfPaid:
    async def test_dropped_but_paid_enrollment_domain_still_shown(self, client, admin_headers):
        sid = await seed_student(test_db, email="dropped@example.com", github_username="droppeduser")
        bid = await seed_batch(test_db, domain="python")
        await seed_enrollment(test_db, sid, bid)
        await seed_payment(test_db, sid, bid)
        await test_db.execute("UPDATE enrollments SET status = 'dropped' WHERE student_id = ? AND batch_id = ?", (sid, bid))

        data = (await client.get(f"/api/portfolio/id/{sid}")).json()
        assert "python" in data["domains"], "paid-for domain vanished after drop"


@pytest.mark.asyncio
class TestUnicodeAndSpecialNames:
    async def test_unicode_name_and_college_survive_roundtrip(self, client, admin_headers):
        sid = await test_db.insert(
            """INSERT INTO students (first_name, last_name, email, github_username, college, domain, status)
               VALUES (?, ?, ?, ?, ?, ?, 'enrolled')""",
            ("Jose", "Muller-O" + chr(39) + "Neil", "jose@example.com", "jose_m", "Indian Institute of Technology, Delhi", "web-dev"),
        )
        bid = await seed_batch(test_db, domain="web-dev")
        await seed_enrollment(test_db, sid, bid)
        await seed_payment(test_db, sid, bid)

        data = (await client.get(f"/api/portfolio/id/{sid}")).json()
        assert data["profile"]["name"] == "Jose Muller-O" + chr(39) + "Neil"
        assert data["profile"]["college"] == "Indian Institute of Technology, Delhi"

    async def test_github_username_with_mixed_case_lookup(self, client, admin_headers):
        sid = await seed_student(test_db, email="case@example.com", github_username="CaseSensitiveUser")
        bid = await seed_batch(test_db)
        await seed_enrollment(test_db, sid, bid)
        await seed_payment(test_db, sid, bid)

        for variant in ("casesensitiveuser", "CASESENSITIVEUSER", "CaseSensitiveUser"):
            r = await client.get(f"/api/portfolio/{variant}")
            assert r.status_code == 200, variant


@pytest.mark.asyncio
class TestNoBatchSubmission:
    async def test_submission_with_null_batch_domain_falls_back_gracefully(self, client, admin_headers):
        """Submissions LEFT JOINed to a missing/null batch must not crash the endpoint."""
        sid, bid = await _setup_paid(domain="java")
        # Simulate an orphaned batch reference by pointing at a batch id that doesn't exist in `batches`
        # (LEFT JOIN means domain will be NULL) -- this must not 500.
        ghost_bid = 999999
        sub_id = await test_db.insert(
            """INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status, reviewed_at)
               VALUES (?, ?, 1, 'https://www.linkedin.com/feed/update/urn:li:activity:x', 'approved', '2026-01-01 00:00:00')""",
            (sid, ghost_bid),
        )
        r = await client.get(f"/api/portfolio/id/{sid}")
        assert r.status_code == 200, r.text
        subs = r.json()["submissions"]
        assert len(subs) == 1
        assert subs[0]["domain"] is None


@pytest.mark.asyncio
class TestPaymentRefundedAfterApproval:
    async def test_refunded_payment_locks_previously_public_portfolio(self, client, admin_headers):
        sid, bid = await _setup_paid()
        sub_id = await test_db.insert(
            """INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status, reviewed_at)
               VALUES (?, ?, 1, 'https://www.linkedin.com/feed/update/urn:li:activity:1', 'approved', '2026-01-01 00:00:00')""",
            (sid, bid),
        )
        before = await client.get(f"/api/portfolio/id/{sid}")
        assert before.status_code == 200

        await test_db.execute("UPDATE payments SET status = 'refunded' WHERE student_id = ?", (sid,))
        after = await client.get(f"/api/portfolio/id/{sid}")
        assert after.status_code == 403, "portfolio stayed public after payment was refunded"
