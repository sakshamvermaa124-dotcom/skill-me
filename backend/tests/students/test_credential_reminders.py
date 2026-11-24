"""
Credential follow-ups and funnel.

- "credentials waiting": unlocked (3 approved weeks or admin unlock), unpaid, 2+ days after unlock,
  at most 3 emails a week apart, never to opted-out / test accounts or someone emailed in the last day.
- "stipend seat open": certificate holder without a seat, same cadence, carries the certificate ID.
- POST /api/students/funnel records each step once per enrollment; funnel_report lines them up.
"""
from datetime import datetime, timedelta

import pytest

from tests.conftest import test_db, seed_student, seed_batch, seed_enrollment, seed_payment, auth_headers
from services import credential_reminder_service as crs
from services.email_service import email_service as real_email_service

CERT = "SM-A1B2-C3D4-E5F6"


def _ts(days_ago: float) -> str:
    return (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")


async def _approve(sid, bid, weeks, days_ago=5):
    for w in range(1, weeks + 1):
        await test_db.execute(
            """INSERT INTO submissions (student_id, batch_id, week, linkedin_url, status, submitted_at, reviewed_at)
               VALUES (?, ?, ?, 'https://linkedin.com/x', 'approved', ?, ?)""",
            (sid, bid, w, _ts(days_ago + 1), _ts(days_ago)))
        await test_db.execute(
            "INSERT INTO progress (student_id, batch_id, week, issues_completed) VALUES (?, ?, ?, 1)", (sid, bid, w))


async def _student(email="ana@example.com", weeks=3, days_ago=5, is_test=False):
    sid = await seed_student(test_db, email=email, first_name="Ana", last_name="Roy", github_username=email.split("@")[0])
    bid = await seed_batch(test_db, batch_number=sid)
    await seed_enrollment(test_db, sid, bid)
    if is_test:
        await test_db.execute("UPDATE students SET is_test = 1 WHERE id = ?", (sid,))
    await _approve(sid, bid, weeks, days_ago)
    return sid, bid


async def _certify(sid, bid, days_ago=3, cert_id=CERT):
    await seed_payment(test_db, sid, bid)
    await test_db.execute("INSERT INTO certificates (student_id, batch_id, cert_id, issued_at) VALUES (?, ?, ?, ?)",
                          (sid, bid, cert_id, _ts(days_ago)))


async def _log(email, kind, days_ago):
    await test_db.execute(
        "INSERT INTO email_logs (recipient_email, email_type, subject, status, sent_at) VALUES (?, ?, 's', 'sent', ?)",
        (email, kind, _ts(days_ago)))


async def _due():
    return [(c["email"], c["kind"], c["step"]) for c in await crs.get_candidates()]


@pytest.mark.students
class TestCredentialsWaiting:
    async def test_unlocked_unpaid_gets_first_reminder(self, client):
        await _student()
        assert await _due() == [("ana@example.com", "credentials_waiting", 1)]

    async def test_waits_two_days_after_unlock(self, client):
        await _student(days_ago=1)
        assert await _due() == []

    async def test_two_weeks_is_not_unlocked(self, client):
        await _student(weeks=2)
        assert await _due() == []

    async def test_admin_unlock_counts(self, client):
        sid, bid = await _student(weeks=1)
        await test_db.execute("UPDATE enrollments SET payment_unlocked_at = ? WHERE student_id = ?", (_ts(4), sid))
        assert await _due() == [("ana@example.com", "credentials_waiting", 1)]

    async def test_week_between_reminders_then_stops_after_three(self, client):
        await _student(days_ago=30)
        await _log("ana@example.com", "credentials_waiting", 3)
        assert await _due() == []  # too soon after the first
        await test_db.execute("UPDATE email_logs SET sent_at = ?", (_ts(8),))
        assert await _due() == [("ana@example.com", "credentials_waiting", 2)]
        await _log("ana@example.com", "credentials_waiting", 9)
        await _log("ana@example.com", "credentials_waiting", 10)
        assert await _due() == []  # three sent: done for good

    async def test_paid_student_is_not_reminded_to_pay(self, client):
        sid, bid = await _student()
        await seed_payment(test_db, sid, bid)
        assert all(k != "credentials_waiting" for _, k, _ in await _due())

    async def test_opted_out_test_and_recently_emailed_are_skipped(self, client):
        await _student("opt@example.com")
        await test_db.execute("INSERT INTO notification_preferences (email, reminders_opt_out) VALUES ('opt@example.com', 1)")
        await _student("qa@example.com", is_test=True)
        await _student("busy@example.com")
        await _log("busy@example.com", "task_reminder", 0.2)
        assert await _due() == []


@pytest.mark.students
class TestStipendSeatReminder:
    async def test_certified_without_seat_gets_reminder(self, client):
        sid, bid = await _student()
        await _certify(sid, bid)
        assert await _due() == [("ana@example.com", "stipend_seat_reminder", 1)]

    async def test_not_before_two_days_after_issue(self, client):
        sid, bid = await _student()
        await _certify(sid, bid, days_ago=0.5)
        assert await _due() == []

    async def test_seat_taken_stops_it(self, client):
        sid, bid = await _student()
        await _certify(sid, bid)
        await test_db.execute(
            "INSERT INTO stipend_entries (email, student_id, batch_id, cert_id) VALUES ('ana@example.com', ?, ?, ?)",
            (sid, bid, CERT))
        assert await _due() == []

    async def test_send_passes_cert_id_and_counts(self, client):
        sid, bid = await _student()
        await _certify(sid, bid)
        await _student("ben@example.com")
        summary = await crs.send_credential_reminders(throttle=0)
        assert summary == {"sent": 2, "failed": 0, "credentials_waiting": 1, "stipend_seat_reminder": 1}
        mock = crs.email_service
        args = mock.send_stipend_seat_reminder.await_args
        assert CERT in args.args and args.args[-1] == 1
        assert mock.send_credentials_waiting.await_args.args[2] == "ben@example.com"


@pytest.mark.students
class TestFunnel:
    async def _post(self, client, sid, step, email="ana@example.com", bid=None):
        return await client.post("/api/students/funnel", json={"step": step, "student_id": sid, "batch_id": bid},
                                 headers=auth_headers(sid, email))

    async def test_step_recorded_once(self, client):
        sid, bid = await _student()
        for _ in range(3):
            r = await self._post(client, sid, "cred_checkout_opened", bid=bid)
            assert r.status_code == 204, r.text
        row = await test_db.fetch_one(
            "SELECT COUNT(*) AS n FROM student_events WHERE event_type = 'cred_checkout_opened'")
        assert row["n"] == 1

    async def test_unknown_step_rejected(self, client):
        sid, _ = await _student()
        assert (await self._post(client, sid, "drop_table")).status_code == 400

    async def test_cannot_record_for_someone_else(self, client):
        sid, _ = await _student()
        other, _ = await _student("eve@example.com")
        r = await client.post("/api/students/funnel", json={"step": "cred_offer_seen", "student_id": other},
                              headers=auth_headers(sid, "ana@example.com"))
        assert r.status_code == 403

    async def test_requires_login(self, client):
        r = await client.post("/api/students/funnel", json={"step": "cred_offer_seen", "student_id": 1})
        assert r.status_code == 401

    async def test_report_lines_up_steps(self, client):
        sid, bid = await _student()
        for step in ("cred_offer_seen", "cred_checkout_opened", "cred_pay_clicked"):
            await self._post(client, sid, step, bid=bid)
        await _certify(sid, bid)
        await test_db.execute(
            "INSERT INTO stipend_entries (email, student_id, batch_id, cert_id) VALUES ('ana@example.com', ?, ?, ?)",
            (sid, bid, CERT))
        await _student("ben@example.com")  # unlocked, never looked
        rep = await crs.funnel_report()
        counts = [s["count"] for s in rep["steps"]]
        assert counts == [2, 1, 1, 1, 1, 1]
        assert rep["steps"][1]["pct_of_unlocked"] == 50.0
        assert rep["tracking_since"]


@pytest.mark.students
class TestTemplates:
    @pytest.mark.parametrize("step", [1, 2, 3])
    def test_credentials_waiting_renders(self, step):
        from services.email_service import _render
        html = _render("credentials_waiting.html", first_name="Ana", last_name="Roy", domain_label="Web Development",
                       step=step, last=step >= 3, cta_url="https://x/dashboard.html#checkout", unsubscribe_url="https://x/u")
        assert "Issue my credentials" in html and "Only genuine interns compete" in html and "https://x/u" in html
        assert ("last email" in html) == (step == 3)
        assert "₹" not in html and "deadline" not in html.lower()

    @pytest.mark.parametrize("step", [1, 3])
    def test_stipend_seat_reminder_renders(self, step):
        from services.email_service import _render
        html = _render("stipend_seat_reminder.html", first_name="Ana", last_name="Roy", domain_label="Web Development",
                       cert_id=CERT, step=step, last=step >= 3, cta_url="https://x/dashboard.html#stipend",
                       unsubscribe_url="https://x/u")
        assert CERT in html and "Confirm my seat" in html and "deadline" not in html.lower()

    def test_real_sender_exists(self):
        assert callable(real_email_service.send_credentials_waiting)
        assert callable(real_email_service.send_stipend_seat_reminder)
