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
