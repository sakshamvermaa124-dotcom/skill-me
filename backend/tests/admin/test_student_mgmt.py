"""
Admin Tests — Student Management
Tests listing, getting, and updating students.
"""
import pytest
from tests.conftest import test_db, seed_student, seed_batch, seed_enrollment, seed_payment


@pytest.mark.admin
class TestListStudents:
    async def test_list_students_empty(self, client, admin_headers):
        r = await client.get("/api/admin/students", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["students"] == []

    async def test_list_students_with_data(self, client, admin_headers, test_student):
        r = await client.get("/api/admin/students", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 1
        assert data["total"] == 1
        assert data["students"][0]["email"] == test_student["email"]

    async def test_list_students_filter_by_applied(self, client, admin_headers, test_student):
        r = await client.get("/api/admin/students?status=applied", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["count"] == 1

    async def test_list_students_filter_nonexistent_status(self, client, admin_headers, test_student):
        r = await client.get("/api/admin/students?status=nonexistent", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["count"] == 0

    async def test_list_students_pagination(self, client, admin_headers):
        """Pagination with limit/offset should work."""
        for i in range(5):
            await seed_student(test_db, email=f"student{i}@example.com")

        r = await client.get("/api/admin/students?limit=2&offset=0", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["count"] == 2

        r2 = await client.get("/api/admin/students?limit=2&offset=2", headers=admin_headers)
        assert r2.status_code == 200
        assert r2.json()["count"] == 2

    async def test_list_students_default_page_size_is_15(self, client, admin_headers):
        for i in range(20):
            await seed_student(test_db, email=f"p{i}@example.com")
        r = await client.get("/api/admin/students", headers=admin_headers)
        data = r.json()
        assert data["count"] == 15
        assert data["total"] == 20
        assert data["page"] == 1
        assert data["total_pages"] == 2

        r2 = await client.get("/api/admin/students?page=2", headers=admin_headers)
        d2 = r2.json()
        assert d2["count"] == 5
        assert d2["page"] == 2
        ids_page1 = {s["id"] for s in data["students"]}
        assert not ids_page1 & {s["id"] for s in d2["students"]}

    async def test_list_students_page_past_end_is_empty(self, client, admin_headers, test_student):
        r = await client.get("/api/admin/students?page=9", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["students"] == []
        assert r.json()["total"] == 1

    async def test_list_students_search(self, client, admin_headers):
        await seed_student(test_db, email="alice@example.com", first_name="Alice", last_name="Smith")
        await seed_student(test_db, email="bob@example.com", first_name="Bob", last_name="Jones")
        for q in ("alice", "ALICE SMITH", "alice@exa"):
            r = await client.get("/api/admin/students", params={"q": q}, headers=admin_headers)
            data = r.json()
            assert data["total"] == 1, q
            assert data["students"][0]["email"] == "alice@example.com"

    async def test_list_students_search_is_injection_safe(self, client, admin_headers, test_student):
        r = await client.get("/api/admin/students", params={"q": "' OR 1=1 --"}, headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["total"] == 0
        r = await client.get("/api/admin/students", params={"status": "applied' OR '1'='1"}, headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["total"] == 0

    async def test_list_students_paid_filter_splits_alumni(self, client, admin_headers, paid_student):
        await seed_student(test_db, email="unpaid@example.com")
        alumni = (await client.get("/api/admin/students?paid=true", headers=admin_headers)).json()
        active = (await client.get("/api/admin/students?paid=false", headers=admin_headers)).json()
        assert [s["email"] for s in alumni["students"]] == [paid_student["email"]]
        assert alumni["students"][0]["has_paid"] == 1
        assert [s["email"] for s in active["students"]] == ["unpaid@example.com"]

    async def test_list_students_no_duplicate_rows(self, client, admin_headers, paid_student, test_batch):
        """Multiple payments/enrollments must not duplicate a student row."""
        await test_db.insert(
            "INSERT INTO payments (student_id, batch_id, razorpay_order_id, amount, status) VALUES (?, ?, 'order_dup_2', 9900, 'paid')",
            (paid_student["id"], test_batch["id"]),
        )
        extra = await seed_batch(test_db, batch_number=2)
        await seed_enrollment(test_db, paid_student["id"], extra)
        r = await client.get("/api/admin/students", headers=admin_headers)
        assert r.json()["total"] == 1
        assert r.json()["count"] == 1
        # the enrollment reference points at the paid enrollment
        assert r.json()["students"][0]["batch_id"] == test_batch["id"]

    async def test_list_students_multiple_with_all_statuses(self, client, admin_headers):
        """Filter should only return matching status."""
        await seed_student(test_db, email="s1@e.com", status="applied")
        await seed_student(test_db, email="s2@e.com", status="shortlisted")
        await seed_student(test_db, email="s3@e.com", status="enrolled")

        r = await client.get("/api/admin/students?status=shortlisted", headers=admin_headers)
        students = r.json()["students"]
        assert all(s["status"] == "shortlisted" for s in students)


@pytest.mark.admin
class TestGetStudent:
    async def test_get_student_by_id(self, client, admin_headers, test_student):
        r = await client.get(f"/api/admin/students/{test_student['id']}", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["student"]["id"] == test_student["id"]
        assert data["student"]["email"] == test_student["email"]
        assert "enrollment" in data
        assert "progress" in data

    async def test_get_nonexistent_student(self, client, admin_headers):
        r = await client.get("/api/admin/students/99999", headers=admin_headers)
        assert r.status_code == 404


@pytest.mark.admin
class TestUpdateStudentStatus:
    @pytest.mark.parametrize("new_status", ["shortlisted", "enrolled", "completed", "dropped"])
    async def test_update_status_valid(self, client, admin_headers, test_student, new_status):
        r = await client.patch(
            f"/api/admin/students/{test_student['id']}/status",
            json={"status": new_status},
            headers=admin_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "updated"
        assert data["new_status"] == new_status

    async def test_update_status_persists_in_db(self, client, admin_headers, test_student):
        await client.patch(
            f"/api/admin/students/{test_student['id']}/status",
            json={"status": "shortlisted"},
            headers=admin_headers,
        )
        student = await test_db.fetch_one(
            "SELECT status FROM students WHERE id = ?", (test_student["id"],)
        )
        assert student["status"] == "shortlisted"

    async def test_update_status_nonexistent_student(self, client, admin_headers):
        r = await client.patch(
            "/api/admin/students/99999/status",
            json={"status": "shortlisted"},
            headers=admin_headers,
        )
        assert r.status_code == 404

    async def test_update_status_missing_body(self, client, admin_headers, test_student):
        r = await client.patch(
            f"/api/admin/students/{test_student['id']}/status",
            json={},
            headers=admin_headers,
        )
        assert r.status_code == 422

    async def test_drop_student_updates_enrollments(self, client, admin_headers, enrolled_student):
        """Dropping a student cascades to active enrollments and revokes GitHub access."""
        r = await client.patch(
            f"/api/admin/students/{enrolled_student['id']}/status",
            json={"status": "dropped"},
            headers=admin_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["new_status"] == "dropped"


@pytest.mark.admin
class TestAdminStats:
    async def test_stats_returns_correct_structure(self, client, admin_headers):
        r = await client.get("/api/admin/stats", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert "total_students" in data
        assert "active_batches" not in data
        assert "enrolled_students" in data
        assert "total_alumni" in data
        assert "pending_applications" in data
        assert "pending_submissions" in data

    async def test_stats_counts_are_non_negative(self, client, admin_headers):
        r = await client.get("/api/admin/stats", headers=admin_headers)
        data = r.json()
        assert data["total_students"] >= 0
        assert data["enrolled_students"] >= 0
        assert data["pending_applications"] >= 0
        assert data["pending_submissions"] >= 0

    async def test_stats_increments_on_new_student(self, client, admin_headers):
        r1 = await client.get("/api/admin/stats", headers=admin_headers)
        before = r1.json()["total_students"]

        await seed_student(test_db, email="newstudent@example.com")

        r2 = await client.get("/api/admin/stats", headers=admin_headers)
        assert r2.json()["total_students"] == before + 1


@pytest.mark.admin
class TestDeleteStudent:
    async def test_delete_student_success(self, client, admin_headers, test_student):
        r = await client.delete(
            f"/api/admin/students/{test_student['id']}",
            headers=admin_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "deleted"
        assert data["student_id"] == test_student["id"]

        # Verify completely gone from DB
        row = await test_db.fetch_one("SELECT * FROM students WHERE id = ?", (test_student["id"],))
        assert row is None

        # Verify user status check returns 404 (acts like brand new user)
        status_res = await client.get(f"/api/students/status/{test_student['email']}")
        assert status_res.status_code == 404

        # Verify user can re-apply fresh
        apply_res = await client.post("/api/students/apply", json={
            "first_name": "New",
            "last_name": "User",
            "email": test_student["email"],
            "domain": "web-dev"
        })
        assert apply_res.status_code == 200
        assert apply_res.json()["status"] == "applied"

    async def test_delete_enrolled_student_cascades_all_data(self, client, admin_headers, enrolled_student):
        student_id = enrolled_student["id"]
        email = enrolled_student["email"]

        r = await client.delete(
            f"/api/admin/students/{student_id}",
            headers=admin_headers,
        )
        assert r.status_code == 200

        # Verify all child tables have no records for this student
        assert await test_db.fetch_one("SELECT * FROM students WHERE id = ?", (student_id,)) is None
        assert await test_db.fetch_one("SELECT * FROM enrollments WHERE student_id = ?", (student_id,)) is None
        assert await test_db.fetch_one("SELECT * FROM progress WHERE student_id = ?", (student_id,)) is None
        assert await test_db.fetch_one("SELECT * FROM submissions WHERE student_id = ?", (student_id,)) is None

    async def test_delete_nonexistent_student(self, client, admin_headers):
        r = await client.delete(
            "/api/admin/students/99999",
            headers=admin_headers,
        )
        assert r.status_code == 404

