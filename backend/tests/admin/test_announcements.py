"""
Admin Tests — Announcements
Tests the submission-flow-update announcement preview + send flow.
"""
import pytest
from tests.conftest import test_db, seed_student


@pytest.mark.admin
class TestAnnouncements:
    async def test_list_announcements(self, client, admin_headers):
        r = await client.get("/api/admin/announcements", headers=admin_headers)
        assert r.status_code == 200
        keys = [a["key"] for a in r.json()["announcements"]]
        assert "submission-flow-update" in keys

    async def test_preview_unknown_announcement(self, client, admin_headers):
        r = await client.get("/api/admin/announcements/nonexistent/preview", headers=admin_headers)
        assert r.status_code == 404

    async def test_preview_enrolled_students(self, client, admin_headers, enrolled_student):
        await test_db.execute("UPDATE students SET status = 'enrolled' WHERE id = ?", (enrolled_student["id"],))
        r = await client.get(
            "/api/admin/announcements/submission-flow-update/preview?status=enrolled",
            headers=admin_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 1
        assert data["students"][0]["email"] == enrolled_student["email"]

    async def test_send_to_status_filter(self, client, admin_headers, enrolled_student):
        await test_db.execute("UPDATE students SET status = 'enrolled' WHERE id = ?", (enrolled_student["id"],))
        r = await client.post(
            "/api/admin/announcements/submission-flow-update/send",
            json={"status": "enrolled"},
            headers=admin_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "dispatched"
        assert len(data["sent_to"]) == 1
        assert data["sent_to"][0]["email"] == enrolled_student["email"]

    async def test_send_to_explicit_student_ids(self, client, admin_headers):
        s1 = await seed_student(test_db, email="ann1@example.com")
        s2 = await seed_student(test_db, email="ann2@example.com")

        r = await client.post(
            "/api/admin/announcements/submission-flow-update/send",
            json={"student_ids": [s1, s2]},
            headers=admin_headers,
        )
        assert r.status_code == 200
        data = r.json()
        emails = {s["email"] for s in data["sent_to"]}
        assert emails == {"ann1@example.com", "ann2@example.com"}

    async def test_send_no_targets(self, client, admin_headers):
        r = await client.post(
            "/api/admin/announcements/submission-flow-update/send",
            json={"status": "nonexistent-status"},
            headers=admin_headers,
        )
        assert r.status_code == 200
        assert r.json()["status"] == "no_targets"

    async def test_send_unknown_announcement(self, client, admin_headers):
        r = await client.post(
            "/api/admin/announcements/nonexistent/send",
            json={"status": "enrolled"},
            headers=admin_headers,
        )
        assert r.status_code == 404

    async def test_send_requires_admin_key(self, client):
        r = await client.post(
            "/api/admin/announcements/submission-flow-update/send",
            json={"status": "enrolled"},
        )
        assert r.status_code == 403
