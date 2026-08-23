"""
Admin Tests — Batch CRUD
Tests full Create/Read/Delete lifecycle for batches.
"""
import pytest
from tests.conftest import test_db, seed_batch


@pytest.mark.admin
class TestBatchCreate:
    async def test_create_batch_returns_created(self, client, admin_headers):
        r = await client.post(
            "/api/admin/batches",
            json={"domain": "web-dev", "batch_number": 1},
            headers=admin_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "created"
        assert "batch" in data
        assert data["batch"]["domain"] == "web-dev"
        assert data["batch"]["batch_number"] == 1

    async def test_create_batch_stores_in_db(self, client, admin_headers):
        await client.post(
            "/api/admin/batches",
            json={"domain": "python", "batch_number": 2},
            headers=admin_headers,
        )
        r = await client.get("/api/admin/batches", headers=admin_headers)
        batches = r.json()["batches"]
        assert any(b["domain"] == "python" and b["batch_number"] == 2 for b in batches)

    async def test_create_batch_with_start_date(self, client, admin_headers):
        r = await client.post(
            "/api/admin/batches",
            json={"domain": "ml", "batch_number": 1, "start_date": "2025-08-01"},
            headers=admin_headers,
        )
        assert r.status_code == 200

    async def test_create_batch_with_max_students(self, client, admin_headers):
        r = await client.post(
            "/api/admin/batches",
            json={"domain": "react", "batch_number": 1, "max_students": 20},
            headers=admin_headers,
        )
        assert r.status_code == 200

    async def test_create_duplicate_batch_fails(self, client, admin_headers):
        """Creating same domain+batch_number twice should fail with 409."""
        await client.post(
            "/api/admin/batches",
            json={"domain": "web-dev", "batch_number": 1},
            headers=admin_headers,
        )
        r2 = await client.post(
            "/api/admin/batches",
            json={"domain": "web-dev", "batch_number": 1},
            headers=admin_headers,
        )
        assert r2.status_code == 409

    async def test_create_batch_missing_domain(self, client, admin_headers):
        r = await client.post(
            "/api/admin/batches",
            json={"batch_number": 1},
            headers=admin_headers,
        )
        assert r.status_code == 422

    async def test_create_batch_missing_batch_number(self, client, admin_headers):
        r = await client.post(
            "/api/admin/batches",
            json={"domain": "web-dev"},
            headers=admin_headers,
        )
        assert r.status_code == 422

    async def test_create_batch_max_students_too_high(self, client, admin_headers):
        """max_students > 100 should fail Pydantic validation."""
        r = await client.post(
            "/api/admin/batches",
            json={"domain": "web-dev", "batch_number": 1, "max_students": 101},
            headers=admin_headers,
        )
        assert r.status_code == 422

    async def test_create_batch_batch_number_zero_fails(self, client, admin_headers):
        """batch_number must be >= 1."""
        r = await client.post(
            "/api/admin/batches",
            json={"domain": "web-dev", "batch_number": 0},
            headers=admin_headers,
        )
        assert r.status_code == 422


@pytest.mark.admin
class TestBatchList:
    async def test_list_batches_empty(self, client, admin_headers):
        r = await client.get("/api/admin/batches", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["batches"] == []
        assert r.json()["count"] == 0

    async def test_list_batches_with_data(self, client, admin_headers, test_batch):
        r = await client.get("/api/admin/batches", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["count"] == 1
        assert r.json()["batches"][0]["id"] == test_batch["id"]

    async def test_list_batches_has_enrolled_students_count(self, client, admin_headers, enrolled_student):
        r = await client.get("/api/admin/batches", headers=admin_headers)
        batch = r.json()["batches"][0]
        assert "enrolled_students" in batch
        assert batch["enrolled_students"] == 1

    async def test_list_batches_filter_by_status(self, client, admin_headers, test_batch):
        r = await client.get("/api/admin/batches?status=active", headers=admin_headers)
        assert r.status_code == 200
        # test_batch is active
        assert r.json()["count"] >= 1


@pytest.mark.admin
class TestBatchGet:
    async def test_get_batch_by_id(self, client, admin_headers, test_batch):
        r = await client.get(f"/api/admin/batches/{test_batch['id']}", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == test_batch["id"]
        assert data["domain"] == test_batch["domain"]

    async def test_get_nonexistent_batch(self, client, admin_headers):
        r = await client.get("/api/admin/batches/99999", headers=admin_headers)
        assert r.status_code == 404


@pytest.mark.admin
class TestBatchDelete:
    async def test_delete_batch(self, client, admin_headers, test_batch):
        r = await client.delete(
            f"/api/admin/batches/{test_batch['id']}",
            headers=admin_headers,
        )
        assert r.status_code == 200
        assert r.json()["status"] == "success"

    async def test_delete_batch_removes_from_list(self, client, admin_headers, test_batch):
        await client.delete(f"/api/admin/batches/{test_batch['id']}", headers=admin_headers)
        r = await client.get("/api/admin/batches", headers=admin_headers)
        assert r.json()["count"] == 0

    async def test_delete_nonexistent_batch(self, client, admin_headers):
        r = await client.delete("/api/admin/batches/99999", headers=admin_headers)
        assert r.status_code == 404

    async def test_delete_cascades_to_enrollments(self, client, admin_headers, enrolled_student):
        batch_id = enrolled_student["batch_id"]
        r = await client.delete(f"/api/admin/batches/{batch_id}", headers=admin_headers)
        assert r.status_code == 200

        # Enrollment should also be gone
        from tests.conftest import test_db
        enrollment = await test_db.fetch_one(
            "SELECT id FROM enrollments WHERE batch_id = ?", (batch_id,)
        )
        assert enrollment is None


@pytest.mark.admin
class TestBatchAnalytics:
    async def test_analytics_returns_correct_shape(self, client, admin_headers, test_batch):
        r = await client.get(
            f"/api/admin/batches/{test_batch['id']}/analytics",
            headers=admin_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert "batch" in data
        assert "enrollments" in data
        assert "weekly_progress" in data
        assert "submission_stats" in data
        assert "revenue" in data
        assert "student_grid" in data

    async def test_analytics_nonexistent_batch(self, client, admin_headers):
        r = await client.get("/api/admin/batches/99999/analytics", headers=admin_headers)
        assert r.status_code == 404
