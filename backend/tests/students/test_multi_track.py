"""
Student Tests — several applications per email (one per track).
"""
import pytest
from tests.conftest import test_db, seed_student, seed_batch, seed_enrollment, seed_otp, auth_headers

APP = {
    "first_name": "Multi",
    "last_name": "Track",
    "email": "multi@example.com",
    "phone": "+91 98765 43210",
    "college": "Test College",
    "year_of_study": "2nd Year",
    "domain": "web-dev",
    "motivation": "I want to build real projects and ship them every week.",
}


@pytest.mark.students
class TestApplyToSeveralTracks:
    async def test_second_track_creates_a_new_application(self, client):
        r1 = await client.post("/api/students/apply", json=APP)
        r2 = await client.post("/api/students/apply", json={**APP, "domain": "python"})
        assert r1.json()["status"] == "applied"
        assert r2.json()["status"] == "applied"
        assert r1.json()["student_id"] != r2.json()["student_id"]
        rows = await test_db.fetch_all("SELECT domain FROM students WHERE email = ?", (APP["email"],))
        assert sorted(r["domain"] for r in rows) == ["python", "web-dev"]

    async def test_same_track_twice_is_already_applied(self, client):
        await client.post("/api/students/apply", json=APP)
        r = await client.post("/api/students/apply", json={**APP, "email": "MULTI@example.com"})
        assert r.json()["status"] == "already_applied"

    async def test_status_lists_every_track(self, client):
        await client.post("/api/students/apply", json=APP)
        await client.post("/api/students/apply", json={**APP, "domain": "python"})
        data = (await client.get(f"/api/students/status/{APP['email']}")).json()
        assert sorted(a["domain"] for a in data["applications"]) == ["python", "web-dev"]
        assert all(set(a) == {"domain", "domain_label", "status", "enrollment_status", "created_at"} for a in data["applications"])


@pytest.mark.students
class TestSessionAcrossTracks:
    async def _two_tracks(self):
        web = await seed_student(test_db, email="pair@example.com", domain="web-dev", github_username="pair1")
        py = await seed_student(test_db, email="pair@example.com", domain="python", github_username="pair2")
        batch = await seed_batch(test_db, domain="python", batch_number=77)
        await seed_enrollment(test_db, py, batch)
        return web, py

    async def test_otp_login_works_with_several_applications(self, client):
        await self._two_tracks()
        await seed_otp(test_db, "pair@example.com")
        r = await client.post("/api/auth/verify-otp", json={"email": "pair@example.com", "otp": "123456"})
        assert r.status_code == 200
        assert r.json()["token"]

    async def test_applications_endpoint_defaults_to_the_enrolled_track(self, client):
        web, py = await self._two_tracks()
        data = (await client.get("/api/students/applications", headers=auth_headers(web, "pair@example.com"))).json()
        assert {a["student_id"] for a in data["applications"]} == {web, py}
        assert data["default_student_id"] == py

    async def test_progress_by_email_opens_the_enrolled_track(self, client):
        web, py = await self._two_tracks()
        data = (await client.get("/api/students/progress/pair@example.com", headers=auth_headers(web, "pair@example.com"))).json()
        assert data["student"]["id"] == py

    async def test_one_session_reads_both_tracks_but_not_others(self, client):
        web, py = await self._two_tracks()
        stranger = await seed_student(test_db, email="stranger@example.com")
        h = auth_headers(web, "pair@example.com")
        assert (await client.get(f"/api/students/progress/id/{py}", headers=h)).status_code == 200
        assert (await client.get(f"/api/students/progress/id/{web}", headers=h)).status_code == 200
        assert (await client.get(f"/api/students/progress/id/{stranger}", headers=h)).status_code == 403

    async def test_applications_needs_login(self, client):
        assert (await client.get("/api/students/applications")).status_code == 401
