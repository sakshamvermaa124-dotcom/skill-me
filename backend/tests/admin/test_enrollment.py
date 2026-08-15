"""
Admin Tests — Student Enrollment
Tests adding/removing students from batches.
"""
import pytest
from tests.conftest import test_db, seed_student, seed_batch, seed_enrollment


@pytest.mark.admin
class TestAddStudentToBatch:
    async def test_enroll_student_returns_enrolled(self, client, admin_headers, test_student, test_batch):
        r = await client.post(
            f"/api/admin/batches/{test_batch['id']}/students",
            json={"student_id": test_student["id"]},
            headers=admin_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "enrolled"

    async def test_enroll_student_creates_db_record(self, client, admin_headers, test_student, test_batch):
        await client.post(
            f"/api/admin/batches/{test_batch['id']}/students",
            json={"student_id": test_student["id"]},
            headers=admin_headers,
        )
        enrollment = await test_db.fetch_one(
            "SELECT id, status FROM enrollments WHERE student_id = ? AND batch_id = ?",
            (test_student["id"], test_batch["id"]),
        )
        assert enrollment is not None
        assert enrollment["status"] == "enrolled"

    async def test_enroll_nonexistent_student(self, client, admin_headers, test_batch):
        r = await client.post(
            f"/api/admin/batches/{test_batch['id']}/students",
            json={"student_id": 99999},
            headers=admin_headers,
        )
        assert r.status_code in (400, 404, 500)

    async def test_enroll_to_nonexistent_batch(self, client, admin_headers, test_student):
        r = await client.post(
            "/api/admin/batches/99999/students",
            json={"student_id": test_student["id"]},
            headers=admin_headers,
        )
        assert r.status_code in (400, 404, 500)

    async def test_enroll_duplicate_is_idempotent_or_rejected(self, client, admin_headers, enrolled_student):
        """Enrolling same student twice should not crash — either 200 or 400."""
        r = await client.post(
            f"/api/admin/batches/{enrolled_student['batch_id']}/students",
            json={"student_id": enrolled_student["id"]},
            headers=admin_headers,
        )
        assert r.status_code in (200, 400)


@pytest.mark.admin
class TestAutoEnrollStudent:
    async def test_auto_enroll_student_creates_batch_repo_and_enrolls(self, client, admin_headers, test_student):
        """1-click auto-enroll creates personal batch/repo and enrolls student."""
        r = await client.post(
            f"/api/admin/students/{test_student['id']}/enroll",
            headers=admin_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "enrolled"
        assert "batch_id" in data
        assert "repo_name" in data
        assert data["student_id"] == test_student["id"]

        # Verify DB batch record created
        batch = await test_db.fetch_one("SELECT * FROM batches WHERE id = ?", (data["batch_id"],))
        assert batch is not None
        assert batch["repo_name"] == data["repo_name"]

        # Verify enrollment record created
        enrollment = await test_db.fetch_one(
            "SELECT * FROM enrollments WHERE student_id = ? AND batch_id = ?",
            (test_student["id"], data["batch_id"]),
        )
        assert enrollment is not None
        assert enrollment["status"] == "enrolled"

        # Verify student status updated in DB
        student = await test_db.fetch_one("SELECT status FROM students WHERE id = ?", (test_student["id"],))
        assert student["status"] == "enrolled"

    async def test_auto_enroll_nonexistent_student(self, client, admin_headers):
        r = await client.post(
            "/api/admin/students/99999/enroll",
            headers=admin_headers,
        )
        assert r.status_code in (400, 404, 500)

    async def test_auto_enroll_already_enrolled_student(self, client, admin_headers, enrolled_student):
        r = await client.post(
            f"/api/admin/students/{enrolled_student['id']}/enroll",
            headers=admin_headers,
        )
        assert r.status_code in (400, 409)


@pytest.mark.admin
class TestRemoveStudentFromBatch:
    async def test_remove_enrolled_student(self, client, admin_headers, enrolled_student):
        r = await client.delete(
            f"/api/admin/batches/{enrolled_student['batch_id']}/students/{enrolled_student['id']}",
            headers=admin_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "removed"

    async def test_remove_student_updates_enrollment_status(self, client, admin_headers, enrolled_student):
        await client.delete(
            f"/api/admin/batches/{enrolled_student['batch_id']}/students/{enrolled_student['id']}",
            headers=admin_headers,
        )
        enrollment = await test_db.fetch_one(
            "SELECT status FROM enrollments WHERE student_id = ? AND batch_id = ?",
            (enrolled_student["id"], enrolled_student["batch_id"]),
        )
        # Either the record is deleted or marked as dropped
        assert enrollment is None or enrollment["status"] == "dropped"

    async def test_remove_nonexistent_student_from_batch(self, client, admin_headers, test_batch):
        """Removing non-enrolled student should not crash."""
        r = await client.delete(
            f"/api/admin/batches/{test_batch['id']}/students/99999",
            headers=admin_headers,
        )
        assert r.status_code in (200, 400, 404)


@pytest.mark.admin
class TestBatchProgress:
    async def test_batch_progress_empty(self, client, admin_headers, test_batch):
        r = await client.get(
            f"/api/admin/batches/{test_batch['id']}/progress",
            headers=admin_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert "batch" in data
        assert "students" in data
        assert data["total_students"] == 0

    async def test_batch_progress_with_enrollment(self, client, admin_headers, enrolled_student):
        r = await client.get(
            f"/api/admin/batches/{enrolled_student['batch_id']}/progress",
            headers=admin_headers,
        )
        assert r.status_code == 200
        assert r.json()["total_students"] == 1

    async def test_batch_progress_nonexistent_batch(self, client, admin_headers):
        r = await client.get("/api/admin/batches/99999/progress", headers=admin_headers)
        assert r.status_code == 404
