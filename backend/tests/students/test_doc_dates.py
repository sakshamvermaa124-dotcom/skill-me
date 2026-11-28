"""
Student Tests — Internship dates on the documents.

Certificate / LOR period = joining date to exactly one calendar month later (may be in the
future); the documents are dated with that end. A certificate holder may move the joining
date earlier from the dashboard, down to one month before the day the certificate was issued.
"""
from datetime import date

import pytest

from services.doc_dates_service import internship_period, shift_months, period_fields
from services.email_service import _render
from tests.conftest import (
    test_db, seed_student, seed_batch, seed_enrollment, seed_payment, seed_certificate, auth_headers,
)


# ── Pure date rules ──────────────────────────────────────────────────────────

class TestOneMonth:
    def test_plain_month(self):
        assert shift_months(date(2026, 11, 20), 1) == date(2026, 12, 20)

    def test_year_rollover(self):
        assert shift_months(date(2026, 12, 15), 1) == date(2027, 1, 15)

    def test_clamps_to_month_end(self):
        assert shift_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
        assert shift_months(date(2028, 1, 31), 1) == date(2028, 2, 29)
        assert shift_months(date(2026, 3, 31), -1) == date(2026, 2, 28)

    def test_period_from_start_ignores_issue_date(self):
        assert internship_period("2026-08-01", "2026-11-25 10:00:00") == (date(2026, 8, 1), date(2026, 9, 1))

    def test_period_can_end_in_future(self):
        start, end = internship_period("2099-01-10", "2099-01-12 08:00:00")
        assert end == date(2099, 2, 10)

    def test_legacy_without_start_ends_on_issue_date(self):
        assert internship_period(None, "2026-11-25 10:00:00") == (date(2026, 10, 25), date(2026, 11, 25))

    def test_period_fields_iso(self):
        assert period_fields("2026-11-20") == {"start_date": "2026-11-20", "end_date": "2026-12-20"}


# ── Helpers ─────────────────────────────────────────────────────────────────

async def _holder(start="2026-11-20", issued="2026-11-25 10:00:00", email="test@example.com", cert=True):
    sid = await seed_student(test_db, email=email, status="enrolled")
    bid = await seed_batch(test_db, batch_number=sid)
    await test_db.execute("UPDATE batches SET start_date = ? WHERE id = ?", (start, bid))
    await seed_enrollment(test_db, sid, bid)
    await seed_payment(test_db, sid, bid)
    if cert:
        await seed_certificate(test_db, sid, bid, cert_id=f"SM-TEST-{sid:04d}-0001")
        await test_db.execute("UPDATE certificates SET issued_at = ? WHERE student_id = ?", (issued, sid))
    return sid, bid


async def _dates(client, sid, email="test@example.com"):
    r = await client.get(f"/api/students/progress/id/{sid}", headers=auth_headers(sid, email))
    assert r.status_code == 200
    return r.json()["student"]["doc_dates"]


async def _move(client, sid, day, email="test@example.com"):
    return await client.put("/api/students/start-date", json={"student_id": sid, "start_date": day},
                            headers=auth_headers(sid, email))


# ── Dashboard status ─────────────────────────────────────────────────────────

class TestStatus:
    @pytest.mark.asyncio
    async def test_none_without_certificate(self, client):
        sid, _ = await _holder(cert=False)
        assert await _dates(client, sid) is None

    @pytest.mark.asyncio
    async def test_window_for_short_internship(self, client):
        sid, _ = await _holder(start="2026-11-20", issued="2026-11-25 10:00:00")
        d = await _dates(client, sid)
        assert d["start_date"] == "2026-11-20"
        assert d["end_date"] == "2026-12-20"
        assert d["min_start"] == "2026-10-25"   # issue date - 1 month
        assert d["max_start"] == "2026-11-20"   # original joining date
        assert d["can_edit"] is True
        assert d["changed"] is False

    @pytest.mark.asyncio
    async def test_long_internship_cannot_move(self, client):
        # Period already ends before the issue date: nothing to move.
        sid, _ = await _holder(start="2026-08-01", issued="2026-11-25 10:00:00")
        d = await _dates(client, sid)
        assert (d["start_date"], d["end_date"]) == ("2026-08-01", "2026-09-01")
        assert d["min_start"] == d["max_start"] == "2026-08-01"
        assert d["can_edit"] is False


# ── Changing the joining date ────────────────────────────────────────────────

class TestChange:
    @pytest.mark.asyncio
    async def test_move_earlier(self, client):
        sid, bid = await _holder()
        r = await _move(client, sid, "2026-10-25")
        assert r.status_code == 200, r.text
        body = r.json()
        assert (body["start_date"], body["end_date"]) == ("2026-10-25", "2026-11-25")
        assert body["changed"] is True
        row = await test_db.fetch_one("SELECT start_date, original_start_date, end_date FROM batches WHERE id = ?", (bid,))
        assert row["start_date"] == "2026-10-25"
        assert row["original_start_date"] == "2026-11-20"
        assert row["end_date"] == "2026-11-25"

    @pytest.mark.asyncio
    async def test_window_stays_fixed_after_a_change(self, client):
        sid, _ = await _holder()
        assert (await _move(client, sid, "2026-11-01")).status_code == 200
        # Can go back up to the original, and down to the floor, but not past either
        assert (await _move(client, sid, "2026-11-20")).status_code == 200
        assert (await _move(client, sid, "2026-11-21")).status_code == 400
        assert (await _move(client, sid, "2026-10-24")).status_code == 400
        d = await _dates(client, sid)
        assert (d["min_start"], d["max_start"]) == ("2026-10-25", "2026-11-20")
        assert d["changed"] is False  # back on the original date

    @pytest.mark.asyncio
    async def test_rejects_later_than_original(self, client):
        sid, _ = await _holder()
        r = await _move(client, sid, "2026-11-21")
        assert r.status_code == 400
        assert "between" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_rejects_garbage(self, client):
        sid, _ = await _holder()
        assert (await _move(client, sid, "not-a-dt")).status_code == 400

    @pytest.mark.asyncio
    async def test_needs_certificate(self, client):
        sid, _ = await _holder(cert=False)
        assert (await _move(client, sid, "2026-11-01")).status_code == 409

    @pytest.mark.asyncio
    async def test_cannot_change_someone_else(self, client):
        sid, _ = await _holder()
        other, _ = await _holder(email="other@example.com")
        r = await client.put("/api/students/start-date", json={"student_id": sid, "start_date": "2026-11-01"},
                             headers=auth_headers(other, "other@example.com"))
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_requires_login(self, client):
        sid, _ = await _holder()
        r = await client.put("/api/students/start-date", json={"student_id": sid, "start_date": "2026-11-01"})
        assert r.status_code in (401, 403)


# ── Documents read the new dates ─────────────────────────────────────────────

class TestDocuments:
    @pytest.mark.asyncio
    async def test_verify_and_metadata_return_one_month(self, client):
        sid, bid = await _holder()
        cert_id = f"SM-TEST-{sid:04d}-0001"
        v = (await client.get(f"/api/certificates/verify/{cert_id}")).json()
        assert (v["start_date"], v["end_date"]) == ("2026-11-20", "2026-12-20")
        m = (await client.get(f"/api/certificates/metadata/{sid}/{bid}")).json()
        assert (m["start_date"], m["end_date"]) == ("2026-11-20", "2026-12-20")

    @pytest.mark.asyncio
    async def test_change_shows_on_certificate_and_offer(self, client):
        sid, bid = await _holder()
        await _move(client, sid, "2026-10-25")
        v = (await client.get(f"/api/certificates/verify/SM-TEST-{sid:04d}-0001")).json()
        assert (v["start_date"], v["end_date"]) == ("2026-10-25", "2026-11-25")
        from services.auth_service import offer_ref
        o = (await client.get(f"/api/students/offer/{sid}/{offer_ref(sid)}")).json()
        assert o["start_date"] == "2026-10-25"

    @pytest.mark.asyncio
    async def test_issue_certificate_dated_with_completion(self, client):
        from services.certificate_service import certificate_service
        sid, bid = await _holder(start="2026-11-20", cert=False)
        out = await certificate_service.issue_certificate(sid, bid, suppress_email=True, via="admin")
        assert out["issued_on"] == "20 December 2026"

    @pytest.mark.asyncio
    async def test_pdf_renders(self, client):
        from services.certificate_service import generate_certificate_pdf
        pdf, _ = generate_certificate_pdf(
            {"id": 1, "first_name": "A", "last_name": "B", "domain": "web-dev"},
            {"id": 1, "domain": "web-dev", "start_date": "2026-11-20"},
        )
        assert pdf[:4] == b"%PDF"


# ── Email ────────────────────────────────────────────────────────────────────

class TestEmail:
    def _html(self, **over):
        ctx = dict(first_name="Asha", last_name="K", domain_label="Python Developer", cert_id="SM-AAAA-BBBB-CCCC",
                   start_long="20 November 2026", end_long="20 December 2026",
                   min_long="25 October 2026", max_long="20 November 2026",
                   can_edit=True, ends_in_future=True,
                   dashboard_url="https://x/dashboard.html#dates", certificate_url="https://x/certificate.html")
        ctx.update(over)
        return _render("dates_update.html", **ctx)

    def test_future_end_offers_change(self):
        html = self._html()
        assert "20 November 2026 – 20 December 2026" in html
        assert "is in the future" in html
        assert "25 October 2026" in html
        assert "Review my dates" in html
        assert "SM-AAAA-BBBB-CCCC (unchanged)" in html

    def test_no_change_option_when_not_editable(self):
        html = self._html(can_edit=False, ends_in_future=False)
        assert "is in the future" not in html
        assert "move your joining date" not in html.lower()
        assert "Open my dashboard" in html


# ── Gate: only after payment AND certificate issued ─────────────────────────

def _pdf_text(pdf: bytes) -> str:
    """Concatenated, decompressed content streams of a ReportLab PDF."""
    import base64, re, zlib
    out = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        data = m.group(1).strip()
        try:
            if data.endswith(b"~>"):  # ReportLab: ASCII85 over Flate
                data = base64.a85decode(data[:-2].removeprefix(b"<~"))
            out.append(zlib.decompress(data).decode("latin-1"))
        except Exception:
            pass
    return "".join(out)


class TestGateAndEndToEnd:
    @pytest.mark.asyncio
    async def test_hidden_when_certificate_but_not_paid(self, client):
        sid, bid = await _holder()
        await test_db.execute("UPDATE payments SET status = 'failed' WHERE student_id = ?", (sid,))
        assert await _dates(client, sid) is None
        assert (await _move(client, sid, "2026-11-01")).status_code == 409

    @pytest.mark.asyncio
    async def test_hidden_when_paid_but_no_certificate(self, client):
        sid, _ = await _holder(cert=False)
        assert await _dates(client, sid) is None

    @pytest.mark.asyncio
    async def test_change_reaches_every_document(self, client):
        sid, bid = await _holder()
        cert_id = f"SM-TEST-{sid:04d}-0001"
        assert (await _move(client, sid, "2026-10-25")).status_code == 200

        # Public verification (certificate page, LOR page, verify page, QR codes)
        v = await client.get(f"/api/certificates/verify/{cert_id}")
        assert v.status_code == 200 and v.json()["valid"] is True
        assert (v.json()["start_date"], v.json()["end_date"]) == ("2026-10-25", "2026-11-25")
        assert v.json()["cert_id"] == cert_id  # ID never changes

        # Student's own certificate / LOR view
        m = (await client.get(f"/api/certificates/metadata/{sid}/{bid}")).json()
        assert (m["start_date"], m["end_date"], m["cert_id"]) == ("2026-10-25", "2026-11-25", cert_id)

        # Offer letter
        from services.auth_service import offer_ref
        assert (await client.get(f"/api/students/offer/{sid}/{offer_ref(sid)}")).json()["start_date"] == "2026-10-25"

        # Downloadable PDF certificate
        r = await client.get(f"/api/certificates/download/{sid}/{bid}")
        assert r.status_code == 200 and r.content[:4] == b"%PDF"
        text = _pdf_text(r.content)
        assert "25 October 2026 to 25 November 2026" in text
        assert cert_id in text
