"""
Student Tests — Top-performer stipend entry.

GET /api/students/stipend, POST /api/students/stipend/enter and the `stipend` status on the
progress payload: only certificate holders can enter, with their own certificate ID, once per
person, and they get an "entry confirmed" email.
"""
import pytest

from tests.conftest import (
    test_db, seed_student, seed_batch, seed_enrollment, seed_payment, seed_certificate, auth_headers,
)
from services.stipend_service import normalize_cert_id

CERT = "SM-A1B2-C3D4-E5F6"


async def _enter(client, sid, cert_id=CERT, email="test@example.com"):
    return await client.post("/api/students/stipend/enter", json={"cert_id": cert_id}, headers=auth_headers(sid, email))


async def _status(client, sid, email="test@example.com"):
    r = await client.get("/api/students/stipend", headers=auth_headers(sid, email))
    assert r.status_code == 200, r.text
    return r.json()


async def _certified(enrolled_student, cert_id=CERT):
    sid, bid = enrolled_student["id"], enrolled_student["batch_id"]
    await seed_payment(test_db, sid, bid)
    await seed_certificate(test_db, sid, bid, cert_id=cert_id)
    return sid


async def _entry_count():
    row = await test_db.fetch_one("SELECT COUNT(*) AS n FROM stipend_entries")
    return row["n"]


@pytest.mark.students
class TestNormalizeCertId:
    @pytest.mark.parametrize("raw", ["SM-A1B2-C3D4-E5F6", "sm-a1b2-c3d4-e5f6", "  SM A1B2 C3D4 E5F6 ", "a1b2c3d4e5f6"])
    def test_accepts_common_typings(self, raw):
        assert normalize_cert_id(raw) == CERT

    @pytest.mark.parametrize("raw", ["", None, "SM-A1B2", "SM-A1B2-C3D4-E5F6-0000", "hello world!"])
    def test_rejects_non_ids(self, raw):
        assert normalize_cert_id(raw) is None


@pytest.mark.students
class TestStipendStatus:
    async def test_without_certificate_not_eligible(self, client, enrolled_student):
        assert await _status(client, enrolled_student["id"]) == {"eligible": False, "entered": False, "entry": None, "certificate": None}

    async def test_paid_and_certified_is_eligible(self, client, enrolled_student):
        sid = await _certified(enrolled_student)
        st = await _status(client, sid)
        assert (st["eligible"], st["entered"]) == (True, False)

    async def test_progress_payload_carries_stipend(self, client, enrolled_student):
        sid = await _certified(enrolled_student)
        await _enter(client, sid)
        r = await client.get(f"/api/students/progress/id/{sid}", headers=auth_headers(sid))
        st = r.json()["student"]["stipend"]
        assert st["entered"] is True and st["entry"]["cert_id"] == CERT

    async def test_requires_login(self, client):
        assert (await client.get("/api/students/stipend")).status_code == 401


@pytest.mark.students
class TestStipendEntry:
    async def test_enter_with_own_certificate(self, client, enrolled_student):
        from routes import students as students_routes
        sid = await _certified(enrolled_student)
        r = await _enter(client, sid, "sm a1b2 c3d4 e5f6")
        assert r.status_code == 200, r.text
        assert r.json()["entry"]["cert_id"] == CERT
        assert (await _status(client, sid))["entered"] is True
        kw = students_routes.email_service.send_stipend_entry_confirmed.await_args.kwargs
        assert (kw["email"], kw["cert_id"], kw["first_name"]) == ("test@example.com", CERT, "Test")

    async def test_second_entry_is_refused(self, client, enrolled_student):
        from routes import students as students_routes
        sid = await _certified(enrolled_student)
        assert (await _enter(client, sid)).status_code == 200
        r = await _enter(client, sid)
        assert r.status_code == 409
        body = r.json()
        assert body["code"] == "already_entered" and body["entry"]["cert_id"] == CERT
        assert await _entry_count() == 1
        assert students_routes.email_service.send_stipend_entry_confirmed.await_count == 1

    async def test_one_seat_per_person_across_tracks(self, client, enrolled_student):
        sid = await _certified(enrolled_student)
        second = await seed_student(test_db, domain="python")
        batch2 = await seed_batch(test_db, domain="python", batch_number=2)
        await seed_enrollment(test_db, second, batch2)
        await seed_certificate(test_db, second, batch2, cert_id="SM-9999-8888-7777")
        assert (await _enter(client, sid)).status_code == 200
        r = await _enter(client, second, "SM-9999-8888-7777")
        assert r.status_code == 409
        assert await _entry_count() == 1

    async def test_someone_elses_certificate_is_refused(self, client, enrolled_student, test_batch):
        await _certified(enrolled_student)
        other = await seed_student(test_db, email="other@example.com")
        await seed_enrollment(test_db, other, test_batch["id"])
        r = await _enter(client, other, CERT, email="other@example.com")
        assert r.status_code == 403
        assert await _entry_count() == 0

    async def test_unknown_certificate(self, client, enrolled_student):
        await _certified(enrolled_student)
        r = await _enter(client, enrolled_student["id"], "SM-0000-0000-0000")
        assert r.status_code == 404
        assert await _entry_count() == 0

    async def test_malformed_id(self, client, enrolled_student):
        await _certified(enrolled_student)
        r = await _enter(client, enrolled_student["id"], "my certificate")
        assert r.status_code == 400
        assert "SM-XXXX-XXXX-XXXX" in r.json()["detail"]

    async def test_not_certified_cannot_enter(self, client, enrolled_student):
        r = await _enter(client, enrolled_student["id"])
        assert r.status_code == 404
        assert await _entry_count() == 0

    async def test_requires_login(self, client):
        r = await client.post("/api/students/stipend/enter", json={"cert_id": CERT})
        assert r.status_code == 401


@pytest.mark.students
class TestOneClickEntry:
    """The dashboard sends no ID: the seat is tied to the signed-in person's own certificate."""

    async def test_status_names_own_certificate(self, client, enrolled_student):
        sid = await _certified(enrolled_student)
        assert (await _status(client, sid))["certificate"]["cert_id"] == CERT

    @pytest.mark.parametrize("body", [{}, {"cert_id": None}, {"cert_id": "  "}, None])
    async def test_enter_without_typing_an_id(self, client, enrolled_student, body):
        sid = await _certified(enrolled_student)
        kw = {"json": body} if body is not None else {}
        r = await client.post("/api/students/stipend/enter", headers=auth_headers(sid), **kw)
        assert r.status_code == 200, r.text
        assert r.json()["entry"]["cert_id"] == CERT
        assert await _entry_count() == 1

    async def test_second_click_is_already_entered(self, client, enrolled_student):
        sid = await _certified(enrolled_student)
        await client.post("/api/students/stipend/enter", json={}, headers=auth_headers(sid))
        r = await client.post("/api/students/stipend/enter", json={}, headers=auth_headers(sid))
        assert r.status_code == 409 and r.json()["entry"]["cert_id"] == CERT
        assert await _entry_count() == 1

    async def test_without_certificate_is_refused(self, client, enrolled_student):
        r = await client.post("/api/students/stipend/enter", json={}, headers=auth_headers(enrolled_student["id"]))
        assert r.status_code == 403
        assert await _entry_count() == 0


@pytest.mark.students
class TestStipendEmail:
    def test_template_renders(self):
        from services.email_service import _render
        html = _render(
            "stipend_entry_confirmed.html", first_name="Asha", last_name="Rao",
            domain_label="Python", cert_id=CERT, entered_date="24 November 2026",
        )
        assert "Asha" in html and CERT in html and "$100" in html
