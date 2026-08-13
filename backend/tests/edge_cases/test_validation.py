"""
Edge Case Tests — Input Validation, Boundaries, Negative Cases
"""
import pytest


@pytest.mark.edge
class TestSpecialCharactersInNames:
    async def test_apply_unicode_name(self, client):
        """Unicode characters in names should be accepted."""
        r = await client.post("/api/students/apply", json={
            "first_name": "Aarav",
            "last_name": "Müller-López",
            "email": "aarav@example.com",
            "domain": "web-dev",
        })
        assert r.status_code == 200
        assert r.json()["status"] == "applied"

    async def test_apply_name_with_apostrophe(self, client):
        r = await client.post("/api/students/apply", json={
            "first_name": "O'Brien",
            "last_name": "Mc'Donald",
            "email": "obrien@example.com",
            "domain": "python",
        })
        assert r.status_code == 200

    async def test_apply_name_with_spaces(self, client):
        r = await client.post("/api/students/apply", json={
            "first_name": "Mary Jane",
            "last_name": "Watson Smith",
            "email": "maryjane@example.com",
            "domain": "web-dev",
        })
        assert r.status_code == 200


@pytest.mark.edge
class TestBoundaryValues:
    async def test_apply_minimum_length_first_name(self, client):
        """Single character first name should be accepted (min_length=1)."""
        r = await client.post("/api/students/apply", json={
            "first_name": "A",
            "last_name": "B",
            "email": "ab@example.com",
            "domain": "web-dev",
        })
        assert r.status_code == 200

    async def test_apply_exactly_max_length_motivation(self, client):
        """Motivation at exactly 1000 chars should be accepted."""
        r = await client.post("/api/students/apply", json={
            "first_name": "Test",
            "last_name": "User",
            "email": "boundary@example.com",
            "domain": "web-dev",
            "motivation": "X" * 1000,
        })
        assert r.status_code == 200

    async def test_admin_batch_max_students_boundary(self, client, admin_headers):
        """max_students=100 (max allowed) should succeed."""
        r = await client.post("/api/admin/batches", json={
            "domain": "web-dev",
            "batch_number": 99,
            "max_students": 100,
        }, headers=admin_headers)
        assert r.status_code == 200

    async def test_admin_batch_number_min_boundary(self, client, admin_headers):
        """batch_number=1 (min allowed) should succeed."""
        r = await client.post("/api/admin/batches", json={
            "domain": "web-dev",
            "batch_number": 1,
        }, headers=admin_headers)
        assert r.status_code == 200


@pytest.mark.edge
class TestSQLInjectionPrevention:
    async def test_sql_injection_in_email_status(self, client):
        """SQL injection in email path param should not crash the server."""
        r = await client.get("/api/students/status/'; DROP TABLE students;--")
        # Should return 404 (not found) or 422 (validation), NOT 500
        assert r.status_code in (404, 422)
        assert r.status_code != 500

    async def test_sql_injection_in_apply_email(self, client):
        """SQL injection in apply body should not compromise DB."""
        r = await client.post("/api/students/apply", json={
            "first_name": "Test",
            "last_name": "User",
            "email": "'; DROP TABLE students; --@example.com",
            "domain": "web-dev",
        })
        assert r.status_code != 500

    async def test_sql_injection_in_cert_verify(self, client):
        r = await client.get("/api/certificates/verify/'; DROP TABLE certificates;--")
        assert r.status_code in (404, 422)
        assert r.status_code != 500


@pytest.mark.edge
class TestPaginationBoundaries:
    async def test_students_list_offset_zero(self, client, admin_headers):
        r = await client.get("/api/admin/students?limit=10&offset=0", headers=admin_headers)
        assert r.status_code == 200

    async def test_students_list_large_offset(self, client, admin_headers):
        """Large offset with empty DB should return empty list, not error."""
        r = await client.get("/api/admin/students?limit=10&offset=10000", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["count"] == 0

    async def test_email_logs_large_offset(self, client, admin_headers):
        r = await client.get("/api/admin/email/logs?limit=10&offset=99999", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["total"] == 0 or r.json()["logs"] == []


@pytest.mark.edge
class TestMalformedRequests:
    async def test_apply_invalid_json(self, client):
        r = await client.post(
            "/api/students/apply",
            content=b"this is not json",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 422

    async def test_create_batch_non_integer_batch_number(self, client, admin_headers):
        r = await client.post(
            "/api/admin/batches",
            json={"domain": "web-dev", "batch_number": "not_a_number"},
            headers=admin_headers,
        )
        assert r.status_code == 422

    async def test_update_student_status_integer_body(self, client, admin_headers, test_student):
        r = await client.patch(
            f"/api/admin/students/{test_student['id']}/status",
            json=42,
            headers=admin_headers,
        )
        assert r.status_code == 422
