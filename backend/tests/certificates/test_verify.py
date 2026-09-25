"""
Certificate Tests — Verification
Tests the public GET /api/certificates/verify/{cert_id} endpoint.
"""
import pytest
from tests.conftest import test_db, seed_certificate, seed_student, seed_batch


@pytest.mark.certificates
class TestCertificateVerify:
    async def test_verify_valid_cert(self, client, paid_student, test_batch):
        """Valid certificate ID should return verification data."""
        await seed_certificate(test_db, paid_student["id"], test_batch["id"], "SM-VALID-CERT-001")

        r = await client.get("/api/certificates/verify/SM-VALID-CERT-001")
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is True
        assert "cert_id" in data
        assert "holder" in data
        assert "domain" in data
        assert "issued_at" in data

    async def test_verify_invalid_cert_id(self, client):
        """Non-existent cert ID should return 404."""
        r = await client.get("/api/certificates/verify/SM-DOES-NOT-EXIST")
        assert r.status_code == 404

    async def test_verify_cert_id_case_insensitive(self, client, paid_student, test_batch):
        """Certificate ID lookup should be case-insensitive (uppercased internally)."""
        await seed_certificate(test_db, paid_student["id"], test_batch["id"], "SM-CASE-TEST-001")

        r = await client.get("/api/certificates/verify/sm-case-test-001")
        assert r.status_code == 200

    async def test_verify_empty_cert_id(self, client):
        r = await client.get("/api/certificates/verify/")
        assert r.status_code in (404, 405)


@pytest.mark.certificates
class TestCertificateMetadata:
    async def test_get_metadata_for_issued_cert(self, client, paid_student, test_batch):
        await seed_certificate(test_db, paid_student["id"], test_batch["id"])

        r = await client.get(
            f"/api/certificates/metadata/{paid_student['id']}/{test_batch['id']}"
        )
        assert r.status_code == 200
        data = r.json()
        assert "cert_id" in data
        assert "student_id" in data
        assert "batch_id" in data
        assert "issued_at" in data

    async def test_get_metadata_not_found(self, client, test_student, test_batch):
        r = await client.get(
            f"/api/certificates/metadata/{test_student['id']}/{test_batch['id']}"
        )
        assert r.status_code == 404


@pytest.mark.certificates
class TestCertificatesWithoutBatches:
    async def test_verify_response_has_no_batch_field(self, client, paid_student, test_batch):
        await seed_certificate(test_db, paid_student["id"], test_batch["id"], "SM-NOBATCH-0001")
        data = (await client.get("/api/certificates/verify/SM-NOBATCH-0001")).json()
        assert data["valid"] is True
        assert data["domain"] == "web-dev"
        assert not any("batch" in k for k in data)

    async def test_verify_survives_missing_enrollment_row(self, client, paid_student, test_batch):
        """Even if the internal enrollment row vanished, an issued certificate still verifies."""
        await seed_certificate(test_db, paid_student["id"], test_batch["id"], "SM-ORPHAN-0001")
        await test_db.execute("DELETE FROM batches WHERE id = ?", (test_batch["id"],))
        r = await client.get("/api/certificates/verify/sm-orphan-0001")
        assert r.status_code == 200
        assert r.json()["domain"] == "web-dev"  # falls back to the student's domain

    async def test_metadata_resolves_missing_batch_id(self, client, paid_student, test_batch):
        """certificate.html / lor.html send batch_id=0 when the URL has none."""
        await seed_certificate(test_db, paid_student["id"], test_batch["id"], "SM-ZERO-0001")
        r = await client.get(f"/api/certificates/metadata/{paid_student['id']}/0")
        assert r.status_code == 200
        assert r.json()["cert_id"] == "SM-ZERO-0001"

    async def test_metadata_unpaid_still_locked(self, client, enrolled_student, test_batch):
        await seed_certificate(test_db, enrolled_student["id"], test_batch["id"], "SM-LOCK-0001")
        r = await client.get(f"/api/certificates/metadata/{enrolled_student['id']}/0")
        assert r.status_code == 402

    async def test_issued_cert_id_is_stable(self, client, admin_headers, paid_student, test_batch):
        """Cert IDs are derived from (student, enrollment) — they must not change after this refactor."""
        from services.certificate_service import _cert_id_from_student
        r = await client.post(f"/api/certificates/issue/{paid_student['id']}/{test_batch['id']}", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["cert_id"] == _cert_id_from_student(paid_student["id"], test_batch["id"])
        # issuing again returns the stored ID
        r2 = await client.post(f"/api/certificates/issue/{paid_student['id']}/{test_batch['id']}", headers=admin_headers)
        assert r2.json()["cert_id"] == r.json()["cert_id"]

    async def test_issue_for_unenrolled_student_rejected(self, client, admin_headers, test_student):
        r = await client.post(f"/api/certificates/issue/{test_student['id']}/0", headers=admin_headers)
        assert r.status_code == 400
