"""
Student Tests — Changing the name printed on documents.

PUT /api/students/name, the `name_change` status on the progress payload, the
2-change limit, the lock once a certificate is paid for / issued, the confirmation
email, the name showing everywhere afterwards, and the admin history.
"""
import pytest
from unittest.mock import patch

from tests.conftest import (
    test_db, seed_student, seed_batch, seed_enrollment, seed_payment, seed_certificate, auth_headers,
)


def _body(student_id, first="Saksham", last="Verma"):
    return {"student_id": student_id, "first_name": first, "last_name": last}


async def _change(client, sid, first="Saksham", last="Verma", email="test@example.com"):
    return await client.put("/api/students/name", json=_body(sid, first, last), headers=auth_headers(sid, email))


async def _status(client, sid):
    r = await client.get(f"/api/students/progress/id/{sid}", headers=auth_headers(sid))
    assert r.status_code == 200
    return r.json()["student"]


async def _db_name(sid):
    row = await test_db.fetch_one("SELECT first_name, last_name FROM students WHERE id = ?", (sid,))
    return f"{row['first_name']} {row['last_name']}"


async def _history_count(email="test@example.com"):
    row = await test_db.fetch_one("SELECT COUNT(*) AS n FROM name_changes WHERE email = ?", (email,))
    return row["n"]


# ── Status on the dashboard payload ──────────────────────────────────────────

@pytest.mark.students
class TestNameStatus:
    async def test_fresh_student_has_two_changes(self, client, enrolled_student):
        st = (await _status(client, enrolled_student["id"]))["name_change"]
        assert st == {"limit": 2, "used": 0, "remaining": 2, "can_edit": True, "locked_reason": None}

    async def test_status_counts_down(self, client, enrolled_student):
        sid = enrolled_student["id"]
        await _change(client, sid)
        st = (await _status(client, sid))["name_change"]
        assert (st["used"], st["remaining"], st["can_edit"]) == (1, 1, True)
        await _change(client, sid, "Saksham", "Kumar")
        st = (await _status(client, sid))["name_change"]
        assert (st["used"], st["remaining"], st["can_edit"], st["locked_reason"]) == (2, 0, False, "limit_reached")

    async def test_status_locked_after_payment(self, client, paid_student):
        st = (await _status(client, paid_student["id"]))["name_change"]
        assert st["can_edit"] is False
        assert st["locked_reason"] == "certificate_issued"


# ── Changing the name ────────────────────────────────────────────────────────

@pytest.mark.students
class TestNameChange:
    async def test_change_cleans_whitespace_and_returns_state(self, client, enrolled_student):
        r = await _change(client, enrolled_student["id"], "  saksham ", "  Verma   Kumar ")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "saksham Verma Kumar"
        assert data["previous_name"] == "Test Student"
        assert data["name_change"]["remaining"] == 1

    async def test_unicode_and_name_punctuation_allowed(self, client, test_student):
        assert (await _change(client, test_student["id"], "José-Marie", "O'Brien Jr.")).status_code == 200
        assert (await _change(client, test_student["id"], "साक्षम", "वर्मा")).status_code == 200

    @pytest.mark.parametrize("first,last", [
        ("", "Verma"), ("Saksham", "   "), ("Saksham1", "Verma"), ("Saksham", "<b>x</b>"),
        ("x" * 51, "Verma"), ("...", "Verma"), ("Saksham", "Verma 😀"),
    ])
    async def test_invalid_names_rejected_without_using_a_change(self, client, test_student, first, last):
        r = await _change(client, test_student["id"], first, last)
        assert r.status_code == 400
        assert isinstance(r.json()["detail"], str)
        assert await _db_name(test_student["id"]) == "Test Student"
        assert await _history_count() == 0

    async def test_missing_fields_rejected(self, client, test_student):
        r = await client.put("/api/students/name", json={"student_id": test_student["id"], "first_name": "A"},
                             headers=auth_headers(test_student["id"]))
        assert r.status_code == 422

    async def test_same_name_is_not_a_change(self, client, test_student):
        r = await _change(client, test_student["id"], " Test ", "Student")
        assert r.status_code == 400
        assert "already" in r.json()["detail"]
        assert await _history_count() == 0

    async def test_capitalisation_fix_counts_as_a_change(self, client, test_student):
        r = await _change(client, test_student["id"], "TEST", "Student")
        assert r.status_code == 200
        assert await _history_count() == 1

    async def test_requires_login_and_ownership(self, client, test_student):
        r = await client.put("/api/students/name", json=_body(test_student["id"]))
        assert r.status_code == 401
        other = await seed_student(test_db, email="other@example.com")
        r = await client.put("/api/students/name", json=_body(test_student["id"]),
                             headers=auth_headers(other, "other@example.com"))
        assert r.status_code == 403
        assert await _db_name(test_student["id"]) == "Test Student"

    async def test_history_records_old_and_new_name(self, client, test_student):
        await _change(client, test_student["id"], "Saksham", "Verma")
        await _change(client, test_student["id"], "Saksham", "Kumar")
        rows = await test_db.fetch_all(
            "SELECT * FROM name_changes WHERE email = ? ORDER BY change_number", ("test@example.com",))
        assert [(r["change_number"], r["old_first_name"], r["old_last_name"], r["new_first_name"], r["new_last_name"])
                for r in rows] == [(1, "Test", "Student", "Saksham", "Verma"), (2, "Saksham", "Verma", "Saksham", "Kumar")]
        assert all(r["student_id"] == test_student["id"] for r in rows)


# ── The 2-change limit ───────────────────────────────────────────────────────

@pytest.mark.students
class TestNameChangeLimit:
    async def test_third_change_is_refused(self, client, test_student):
        sid = test_student["id"]
        assert (await _change(client, sid, "A", "One")).status_code == 200
        assert (await _change(client, sid, "A", "Two")).status_code == 200
        r = await _change(client, sid, "A", "Three")
        assert r.status_code == 409
        assert "both" in r.json()["detail"]
        assert await _db_name(sid) == "A Two"
        assert await _history_count() == 2

    async def test_changing_back_still_uses_a_change(self, client, test_student):
        sid = test_student["id"]
        await _change(client, sid, "A", "One")
        await _change(client, sid, "Test", "Student")
        assert (await _change(client, sid, "A", "One")).status_code == 409

    async def test_limit_is_per_person_across_tracks(self, client, test_student):
        second = await seed_student(test_db, domain="python")
        await _change(client, test_student["id"], "A", "One")
        await _change(client, second, "A", "Two")
        r = await _change(client, test_student["id"], "A", "Three")
        assert r.status_code == 409

    async def test_limit_is_per_email_case_insensitive(self, client, test_student):
        second = await seed_student(test_db, email="TEST@Example.com", domain="python")
        await _change(client, test_student["id"], "A", "One")
        await _change(client, second, "A", "Two", email="TEST@Example.com")
        assert (await _change(client, test_student["id"], "A", "Three")).status_code == 409

    async def test_other_people_have_their_own_limit(self, client, test_student):
        other = await seed_student(test_db, email="other@example.com")
        await _change(client, test_student["id"], "A", "One")
        await _change(client, test_student["id"], "A", "Two")
        r = await _change(client, other, "B", "One", email="other@example.com")
        assert r.status_code == 200

    async def test_concurrent_change_for_the_same_slot_is_refused(self, client, test_student):
        """Two tabs both see 1 change used and submit: the unique slot lets only one win."""
        sid = test_student["id"]
        await _change(client, sid, "A", "One")
        from services import name_change_service as svc
        real = svc.name_status

        async def stale_status(email):  # what the losing request read before the winner wrote
            st = await real(email)
            return {**st, "used": 0, "remaining": 2, "can_edit": True, "locked_reason": None}

        with patch.object(svc, "name_status", stale_status):
            r = await _change(client, sid, "A", "Two")
        assert r.status_code == 409
        assert await _db_name(sid) == "A One"
        assert await _history_count() == 1


# ── Lock once the certificate is paid for / issued ───────────────────────────

@pytest.mark.students
class TestNameLock:
    async def test_locked_after_payment(self, client, paid_student):
        r = await _change(client, paid_student["id"])
        assert r.status_code == 409
        assert "certificate" in r.json()["detail"]
        assert await _db_name(paid_student["id"]) == "Test Student"
        assert await _history_count() == 0

    async def test_locked_after_certificate_issued(self, client, enrolled_student):
        await seed_certificate(test_db, enrolled_student["id"], enrolled_student["batch_id"])
        assert (await _change(client, enrolled_student["id"])).status_code == 409

    async def test_payment_on_another_track_locks_the_name(self, client, test_student):
        second = await seed_student(test_db, domain="python")
        batch = await seed_batch(test_db, domain="python")
        await seed_enrollment(test_db, second, batch)
        await seed_payment(test_db, second, batch)
        assert (await _change(client, test_student["id"])).status_code == 409

    @pytest.mark.parametrize("status", ["created", "failed"])
    async def test_unfinished_payment_does_not_lock(self, client, enrolled_student, status):
        await seed_payment(test_db, enrolled_student["id"], enrolled_student["batch_id"], status=status)
        assert (await _change(client, enrolled_student["id"])).status_code == 200


# ── The new name shows everywhere ────────────────────────────────────────────

@pytest.mark.students
class TestNameShowsEverywhere:
    async def test_offer_letter_dashboard_and_portfolio_use_new_name(self, client, enrolled_student):
        sid = enrolled_student["id"]
        await _change(client, sid, "Saksham", "Verma")
        student = await _status(client, sid)
        assert student["name"] == "Saksham Verma"
        assert (student["first_name"], student["last_name"]) == ("Saksham", "Verma")

        offer = (await client.get(f"/api/students/offer/{sid}/{student['offer_ref']}")).json()
        assert offer["name"] == "Saksham Verma"

        portfolio = await client.get(f"/api/portfolio/{sid}")
        if portfolio.status_code == 200:
            assert "Saksham" in portfolio.text

    async def test_every_application_is_renamed(self, client, test_student):
        second = await seed_student(test_db, domain="python")
        await _change(client, test_student["id"])
        assert await _db_name(second) == "Saksham Verma"

    async def test_other_peoples_names_are_untouched(self, client, test_student):
        other = await seed_student(test_db, email="other@example.com", first_name="Other", last_name="Person")
        await _change(client, test_student["id"])
        assert await _db_name(other) == "Other Person"

    async def test_certificate_after_payment_carries_new_name(self, client, enrolled_student):
        sid, bid = enrolled_student["id"], enrolled_student["batch_id"]
        await _change(client, sid, "Saksham", "Verma")
        await seed_payment(test_db, sid, bid)
        await seed_certificate(test_db, sid, bid, cert_id="SM-NAME-TEST-0001")
        r = await client.get("/api/certificates/verify/SM-NAME-TEST-0001")
        assert r.json()["holder"] == "Saksham Verma"

    async def test_changing_the_name_sends_no_email(self, client, test_student):
        from routes import students as students_routes
        await _change(client, test_student["id"])
        assert students_routes.email_service.method_calls == []

    async def test_later_emails_use_new_name(self, client, enrolled_student):
        """Emails read the name at send time, e.g. the task feedback email."""
        from routes import students as students_routes
        await _change(client, enrolled_student["id"], "Saksham", "Verma")
        r = await client.post("/api/students/submit-task", headers=auth_headers(enrolled_student["id"]), json={
            "student_id": enrolled_student["id"], "week": 1,
            "linkedin_url": "https://www.linkedin.com/posts/saksham-verma_skillme-activity-7200000000000000000-abcd",
        })
        assert r.status_code == 200, r.text
        kw = students_routes.email_service.send_submission_feedback.await_args.kwargs
        assert (kw["first_name"], kw["last_name"]) == ("Saksham", "Verma")


# ── Admin history ────────────────────────────────────────────────────────────

@pytest.mark.students
class TestAdminNameHistory:
    async def test_requires_admin(self, client):
        r = await client.get("/api/admin/name-changes")
        assert r.status_code in (401, 403)

    async def test_empty(self, client, admin_headers):
        data = (await client.get("/api/admin/name-changes", headers=admin_headers)).json()
        assert data["changes"] == [] and data["total"] == 0
        assert data["stats"] == {"changes": 0, "people": 0, "maxed_out": 0, "last_7_days": 0}

    async def test_lists_newest_first_with_stats(self, client, admin_headers, test_student):
        other = await seed_student(test_db, email="other@example.com")
        await _change(client, test_student["id"], "A", "One")
        await _change(client, test_student["id"], "A", "Two")
        await _change(client, other, "B", "One", email="other@example.com")
        data = (await client.get("/api/admin/name-changes", headers=admin_headers)).json()
        assert data["total"] == 3
        assert data["changes"][0]["new_name"] == "B One"
        first = next(c for c in data["changes"] if c["new_name"] == "A Two")
        assert (first["old_name"], first["change_number"], first["current_name"], first["paid"]) == \
               ("A One", 2, "A Two", False)
        assert data["stats"] == {"changes": 3, "people": 2, "maxed_out": 1, "last_7_days": 3}
        assert data["limit"] == 2

    async def test_search_and_pagination(self, client, admin_headers, test_student):
        other = await seed_student(test_db, email="other@example.com")
        await _change(client, test_student["id"], "A", "One")
        await _change(client, other, "Zed", "Person", email="other@example.com")
        data = (await client.get("/api/admin/name-changes?q=zed", headers=admin_headers)).json()
        assert [c["new_name"] for c in data["changes"]] == ["Zed Person"]
        data = (await client.get("/api/admin/name-changes?q=TEST@example", headers=admin_headers)).json()
        assert data["total"] == 1
        data = (await client.get("/api/admin/name-changes?limit=1&page=2", headers=admin_headers)).json()
        assert len(data["changes"]) == 1 and data["total_pages"] == 2

    async def test_paid_flag(self, client, admin_headers, enrolled_student):
        await _change(client, enrolled_student["id"])
        await seed_payment(test_db, enrolled_student["id"], enrolled_student["batch_id"])
        data = (await client.get("/api/admin/name-changes", headers=admin_headers)).json()
        assert data["changes"][0]["paid"] is True

    async def test_history_removed_with_last_application(self, client, admin_headers, test_student):
        await _change(client, test_student["id"])
        r = await client.delete(f"/api/admin/students/{test_student['id']}", headers=admin_headers)
        assert r.status_code == 200, r.text
        assert await _history_count() == 0

    async def test_history_kept_while_another_application_remains(self, client, admin_headers, test_student):
        await seed_student(test_db, domain="python")
        await _change(client, test_student["id"])
        await client.delete(f"/api/admin/students/{test_student['id']}", headers=admin_headers)
        assert await _history_count() == 1
