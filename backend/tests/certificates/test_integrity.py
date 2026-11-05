"""
Certificates must hang off a real enrollment; completion is recorded from approvals;
deleting a student must not silently erase revenue history.
"""
import pytest

from tests.conftest import auth_headers, seed_student, seed_batch, seed_enrollment, seed_payment, test_db


async def _enrolled(email="c@x.com", status="enrolled", batch_number=1):
    sid = await seed_student(test_db, email=email)
    b = await seed_batch(test_db, batch_number=batch_number)
    eid = await seed_enrollment(test_db, sid, b)
    if status != "enrolled":
        await test_db.execute("UPDATE enrollments SET status = ? WHERE id = ?", (status, eid))
    return sid, b


@pytest.mark.certificates
class TestCertificateIntegrity:
    async def test_admin_issue_records_how_it_was_issued(self, client, admin_headers):
        sid, b = await _enrolled()
        r = await client.post(f"/api/certificates/issue/{sid}/{b}", headers=admin_headers)
        assert r.status_code == 200
        row = await test_db.fetch_one("SELECT * FROM certificates WHERE student_id = ?", (sid,))
        assert row["issued_via"] == "admin" and row["payment_id"] is None

    async def test_no_certificate_without_an_enrollment(self, client):
        from services.certificate_service import certificate_service
        sid = await seed_student(test_db, email="n@x.com")
        b = await seed_batch(test_db)                       # batch exists, but is not THIS student's enrollment
        with pytest.raises(ValueError):
            await certificate_service.issue_certificate(sid, b, suppress_email=True)
        assert (await test_db.fetch_one("SELECT COUNT(*) n FROM certificates"))["n"] == 0

    async def test_enrollment_of_a_different_student_does_not_count(self, client):
        from services.certificate_service import certificate_service
        owner, b = await _enrolled("owner@x.com")
        thief = await seed_student(test_db, email="thief@x.com", domain="python")
        with pytest.raises(ValueError):
            await certificate_service.issue_certificate(thief, b, suppress_email=True)

    async def test_no_certificate_for_a_dropped_enrollment(self, client):
        from services.certificate_service import certificate_service
        sid, b = await _enrolled("d@x.com", status="dropped")
        with pytest.raises(ValueError):
            await certificate_service.issue_certificate(sid, b, suppress_email=True)

    async def test_payment_path_requires_a_paid_payment(self, client):
        from services.certificate_service import certificate_service
        sid, b = await _enrolled("p@x.com")
        await seed_payment(test_db, sid, b, status="pending")
        with pytest.raises(ValueError):
            await certificate_service.issue_certificate(sid, b, suppress_email=True, via="payment")
        await test_db.execute("UPDATE payments SET status = 'paid'")
        out = await certificate_service.issue_certificate(sid, b, suppress_email=True, via="payment")
        row = await test_db.fetch_one("SELECT * FROM certificates WHERE student_id = ?", (sid,))
        assert row["cert_id"] == out["cert_id"] and row["payment_id"] is not None

    async def test_reissue_returns_existing_without_new_row(self, client):
        from services.certificate_service import certificate_service
        sid, b = await _enrolled("r@x.com")
        a = await certificate_service.issue_certificate(sid, b, suppress_email=True)
        c = await certificate_service.issue_certificate(sid, b, suppress_email=True)
        assert a["cert_id"] == c["cert_id"]
        assert (await test_db.fetch_one("SELECT COUNT(*) n FROM certificates"))["n"] == 1


@pytest.mark.regression
class TestCompletionIsRecorded:
    async def _approve_all(self, sid, b, n=4):
        from services.submission_service import submission_service
        ids = []
        for w in range(1, n + 1):
            sub = await test_db.insert(
                "INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status) VALUES (?,?,?,'u','pending')",
                (sid, b, w))
            await submission_service.approve_submission(sub)
            ids.append(sub)
        return ids

    async def test_fourth_approval_completes_the_enrollment(self, client):
        sid, b = await _enrolled("done@x.com")
        await self._approve_all(sid, b, 3)
        e = await test_db.fetch_one("SELECT status, completed_at FROM enrollments WHERE student_id = ?", (sid,))
        assert e["status"] == "enrolled" and e["completed_at"] is None       # 3/4 is eligible, not complete
        await self._approve_all_week4(sid, b)
        e = await test_db.fetch_one("SELECT status, completed_at FROM enrollments WHERE student_id = ?", (sid,))
        assert e["status"] == "completed" and e["completed_at"]

    async def _approve_all_week4(self, sid, b):
        from services.submission_service import submission_service
        sub = await test_db.insert(
            "INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status) VALUES (?,?,4,'u','pending')", (sid, b))
        await submission_service.approve_submission(sub)

    async def test_reversing_an_approval_uncompletes(self, client):
        from services.submission_service import submission_service
        sid, b = await _enrolled("rev@x.com")
        ids = await self._approve_all(sid, b, 4)
        await submission_service.reject_submission(ids[-1], "not original")
        e = await test_db.fetch_one("SELECT status, completed_at FROM enrollments WHERE student_id = ?", (sid,))
        assert e["status"] == "enrolled" and e["completed_at"] is None

    async def test_double_approve_is_idempotent(self, client):
        from services.submission_service import submission_service
        sid, b = await _enrolled("idem@x.com")
        ids = await self._approve_all(sid, b, 4)
        again = await submission_service.approve_submission(ids[-1])
        assert again.get("already") is True
        p = await test_db.fetch_one("SELECT SUM(issues_completed) n FROM progress WHERE student_id = ?", (sid,))
        assert p["n"] == 4

    async def test_review_timestamps_use_one_format(self, client):
        from services.submission_service import submission_service
        sid, b = await _enrolled("ts@x.com")
        (sub,) = await self._approve_all(sid, b, 1)
        row = await test_db.fetch_one("SELECT reviewed_at FROM submissions WHERE id = ?", (sub,))
        assert "T" not in row["reviewed_at"] and len(row["reviewed_at"]) == 19


@pytest.mark.admin
class TestDeleteProtectsRevenueHistory:
    async def test_paid_student_needs_force(self, client, admin_headers):
        sid, b = await _enrolled("paid@x.com")
        await test_db.insert(
            "INSERT INTO payments (student_id, batch_id, razorpay_order_id, razorpay_payment_id, amount, status) "
            "VALUES (?,?, 'o1', 'pay_Real', 12900, 'paid')", (sid, b))
        r = await client.delete(f"/api/admin/students/{sid}", headers=admin_headers)
        assert r.status_code == 409 and "force=true" in r.json()["detail"]
        assert (await test_db.fetch_one("SELECT COUNT(*) n FROM payments"))["n"] == 1
        r = await client.delete(f"/api/admin/students/{sid}?force=true", headers=admin_headers)
        assert r.status_code == 200

    async def test_unpaid_and_test_students_delete_normally(self, client, admin_headers):
        sid, b = await _enrolled("free@x.com")
        assert (await client.delete(f"/api/admin/students/{sid}", headers=admin_headers)).status_code == 200
        t, tb = await _enrolled("test@x.com", batch_number=2)
        await test_db.execute("UPDATE students SET is_test = 1 WHERE id = ?", (t,))
        await test_db.insert(
            "INSERT INTO payments (student_id, batch_id, razorpay_order_id, razorpay_payment_id, amount, status) "
            "VALUES (?,?, 'o2', 'pay_Real2', 500, 'paid')", (t, tb))
        assert (await client.delete(f"/api/admin/students/{t}", headers=admin_headers)).status_code == 200
