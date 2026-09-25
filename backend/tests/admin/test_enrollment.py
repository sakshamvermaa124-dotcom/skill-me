"""
Admin Tests — Student Enrollment
Enrollment is one click (no batch selection): applied/shortlisted → enrolled.
"""
import pytest
from tests.conftest import test_db, seed_student, seed_batch, seed_enrollment, seed_payment


@pytest.mark.admin
class TestEnrollStudent:
    async def test_enroll_student_creates_enrollment(self, client, admin_headers, test_student):
        r = await client.post(
            f"/api/admin/students/{test_student['id']}/enroll",
            headers=admin_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "enrolled"
        assert data["student_id"] == test_student["id"]
        assert data["reactivated"] is False

        enrollment = await test_db.fetch_one(
            "SELECT * FROM enrollments WHERE student_id = ? AND batch_id = ?",
            (test_student["id"], data["batch_id"]),
        )
        assert enrollment is not None
        assert enrollment["status"] == "enrolled"

        student = await test_db.fetch_one("SELECT status FROM students WHERE id = ?", (test_student["id"],))
        assert student["status"] == "enrolled"

    async def test_enroll_shortlisted_student(self, client, admin_headers):
        sid = await seed_student(test_db, email="short@example.com", status="shortlisted")
        r = await client.post(f"/api/admin/students/{sid}/enroll", headers=admin_headers)
        assert r.status_code == 200

    async def test_each_student_gets_own_enrollment(self, client, admin_headers):
        """Two students in the same domain never share an enrollment record."""
        a = await seed_student(test_db, email="a@example.com")
        b = await seed_student(test_db, email="b@example.com")
        ra = await client.post(f"/api/admin/students/{a}/enroll", headers=admin_headers)
        rb = await client.post(f"/api/admin/students/{b}/enroll", headers=admin_headers)
        assert ra.json()["batch_id"] != rb.json()["batch_id"]

    async def test_enroll_nonexistent_student(self, client, admin_headers):
        r = await client.post("/api/admin/students/99999/enroll", headers=admin_headers)
        assert r.status_code == 400

    async def test_enroll_already_enrolled_student(self, client, admin_headers, enrolled_student):
        r = await client.post(
            f"/api/admin/students/{enrolled_student['id']}/enroll",
            headers=admin_headers,
        )
        assert r.status_code == 400

    async def test_reenroll_dropped_student_keeps_enrollment(self, client, admin_headers, enrolled_student):
        """Re-enrolling after a drop reuses the old enrollment so progress/certificates stay attached."""
        await client.patch(
            f"/api/admin/students/{enrolled_student['id']}/status",
            json={"status": "dropped"},
            headers=admin_headers,
        )
        r = await client.post(
            f"/api/admin/students/{enrolled_student['id']}/enroll",
            headers=admin_headers,
        )
        assert r.status_code == 200
        assert r.json()["batch_id"] == enrolled_student["batch_id"]
        assert r.json()["reactivated"] is True

    async def test_reenroll_prefers_paid_enrollment(self, client, admin_headers, test_student):
        """A legacy student with several dropped enrollments gets back the one they paid for."""
        paid_batch = await seed_batch(test_db, batch_number=10)
        other_batch = await seed_batch(test_db, batch_number=11)
        await seed_enrollment(test_db, test_student["id"], paid_batch)
        await seed_enrollment(test_db, test_student["id"], other_batch)
        await seed_payment(test_db, test_student["id"], paid_batch)
        await test_db.execute("UPDATE enrollments SET status = 'dropped' WHERE student_id = ?", (test_student["id"],))

        r = await client.post(f"/api/admin/students/{test_student['id']}/enroll", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["batch_id"] == paid_batch

    async def test_enroll_sends_offer_letter_without_batch(self, client, admin_headers, test_student):
        from routes import admin as admin_routes
        r = await client.post(f"/api/admin/students/{test_student['id']}/enroll", headers=admin_headers)
        assert r.status_code == 200
        admin_routes.email_service.send_offer_letter.assert_called_once()
        kwargs = admin_routes.email_service.send_offer_letter.call_args.kwargs
        assert "batch_number" not in kwargs
        assert kwargs["email"] == test_student["email"]


@pytest.mark.admin
class TestStatusTransitions:
    async def test_patch_enrolled_creates_real_enrollment(self, client, admin_headers, test_student):
        """Setting status=enrolled must not leave a student with no enrollment (dashboard would break)."""
        r = await client.patch(
            f"/api/admin/students/{test_student['id']}/status",
            json={"status": "enrolled"},
            headers=admin_headers,
        )
        assert r.status_code == 200
        enrollment = await test_db.fetch_one(
            "SELECT status FROM enrollments WHERE student_id = ?", (test_student["id"],)
        )
        assert enrollment is not None and enrollment["status"] == "enrolled"

    async def test_cannot_shortlist_enrolled_student(self, client, admin_headers, enrolled_student):
        r = await client.patch(
            f"/api/admin/students/{enrolled_student['id']}/status",
            json={"status": "shortlisted"},
            headers=admin_headers,
        )
        assert r.status_code == 400

    async def test_drop_deactivates_enrollment(self, client, admin_headers, enrolled_student):
        await client.patch(
            f"/api/admin/students/{enrolled_student['id']}/status",
            json={"status": "dropped"},
            headers=admin_headers,
        )
        enrollment = await test_db.fetch_one(
            "SELECT status FROM enrollments WHERE student_id = ?", (enrolled_student["id"],)
        )
        assert enrollment["status"] == "dropped"

    async def test_shortlist_twice_emails_once(self, client, admin_headers, test_student):
        from routes import admin as admin_routes
        for _ in range(2):
            r = await client.patch(
                f"/api/admin/students/{test_student['id']}/status",
                json={"status": "shortlisted"},
                headers=admin_headers,
            )
            assert r.status_code == 200
        assert admin_routes.email_service.send_shortlist_notification.call_count == 1


@pytest.mark.admin
class TestBatchEndpointsRemoved:
    @pytest.mark.parametrize("method,path", [
        ("get", "/api/admin/batches"),
        ("post", "/api/admin/batches"),
        ("get", "/api/admin/batches/1"),
        ("delete", "/api/admin/batches/1"),
        ("get", "/api/admin/batches/1/analytics"),
        ("post", "/api/admin/batches/1/students"),
    ])
    async def test_batch_endpoint_gone(self, client, admin_headers, method, path):
        r = await getattr(client, method)(path, headers=admin_headers)
        assert r.status_code in (404, 405)


@pytest.mark.admin
class TestReenrollWindow:
    async def test_reenroll_after_window_restarts_private_dates(self, client, admin_headers, enrolled_student):
        await test_db.execute("UPDATE batches SET start_date = date('now', '-60 days') WHERE id = ?", (enrolled_student["batch_id"],))
        await test_db.execute("UPDATE enrollments SET status = 'dropped' WHERE student_id = ?", (enrolled_student["id"],))
        await client.post(f"/api/admin/students/{enrolled_student['id']}/enroll", headers=admin_headers)
        row = await test_db.fetch_one("SELECT start_date = date('now') AS fresh FROM batches WHERE id = ?", (enrolled_student["batch_id"],))
        assert row["fresh"] == 1

    async def test_reenroll_never_moves_shared_legacy_batch_dates(self, client, admin_headers, enrolled_student):
        other = await seed_student(test_db, email="classmate@example.com")
        await seed_enrollment(test_db, other, enrolled_student["batch_id"])
        await test_db.execute("UPDATE batches SET start_date = '2025-01-01' WHERE id = ?", (enrolled_student["batch_id"],))
        await test_db.execute("UPDATE enrollments SET status = 'dropped' WHERE student_id = ?", (enrolled_student["id"],))
        r = await client.post(f"/api/admin/students/{enrolled_student['id']}/enroll", headers=admin_headers)
        assert r.status_code == 200
        row = await test_db.fetch_one("SELECT start_date FROM batches WHERE id = ?", (enrolled_student["batch_id"],))
        assert row["start_date"] == "2025-01-01"

    async def test_delete_keeps_shared_legacy_batch_for_classmates(self, client, admin_headers, enrolled_student):
        other = await seed_student(test_db, email="classmate2@example.com")
        await seed_enrollment(test_db, other, enrolled_student["batch_id"])
        await client.delete(f"/api/admin/students/{enrolled_student['id']}", headers=admin_headers)
        assert await test_db.fetch_one("SELECT id FROM batches WHERE id = ?", (enrolled_student["batch_id"],)) is not None
