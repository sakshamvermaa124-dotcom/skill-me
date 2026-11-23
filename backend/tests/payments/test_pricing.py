"""Certificate price by country: India ₹129, abroad US$4, lower-income countries US$2."""
import pytest
from unittest.mock import patch

from services import pricing
from config import settings
from tests.conftest import auth_headers, test_db
from tests.payments.test_payments import _make_razorpay_mock


INR = settings.certificate_price_paise  # the test env pins this (see conftest)


@pytest.mark.parametrize("student, hint, expected", [
    ({"country": "IN"}, None, ("INR", INR)),
    ({"country": "in "}, "intl", ("INR", INR)),        # stored country beats the browser hint
    ({"country": "US"}, None, ("USD", 400)),
    ({"country": "GB"}, "in", ("USD", 400)),
    ({"country": "NG"}, None, ("USD", 200)),
    ({"country": "PK"}, None, ("USD", 200)),
    ({"country": "KE"}, None, ("USD", 200)),
    ({"phone": "+91 98765 43210"}, "intl", ("INR", INR)),  # phone fallback
    ({"phone": "+1 415 555 0100"}, "in", ("USD", 400)),
    ({"phone": "0813 000 0000"}, "intl", ("USD", 400)),      # unknown -> browser hint
    ({"phone": "0813 000 0000"}, "in", ("INR", INR)),
])
def test_price_for_student(student, hint, expected):
    p = pricing.price_for_student(student, hint)
    assert (p["currency"], p["amount"]) == expected


def test_unknown_without_hint_is_none():
    assert pricing.price_for_student({}, None) is None
    assert set(pricing.price_options()) == {"in", "intl"}


def test_labels():
    assert pricing.price_for_student({"country": "IN"})["label"] == f"₹{INR / 100:g}"
    assert pricing.price_for_student({"country": "US"})["label"] == "US$4"
    assert pricing.price_for_student({"country": "NG"})["label"] == "US$2"


def test_inr_equivalent():
    assert pricing.to_inr_paise(INR, "INR") == INR
    assert pricing.to_inr_paise(400, "USD") == round(400 * pricing.settings.usd_inr_rate)


def test_india_never_reduced():
    assert "IN" not in pricing.REDUCED_PRICE_COUNTRIES


@pytest.mark.payments
@pytest.mark.parametrize("country, hint, currency, amount", [
    ("US", "in", "USD", 400),     # a client claiming India can't get the rupee price
    ("NG", None, "USD", 200),
    ("IN", "intl", "INR", INR),
])
async def test_create_order_charges_country_price(client, enrolled_student, test_batch, country, hint, currency, amount):
    sid = enrolled_student["id"]
    await test_db.execute("UPDATE students SET country = ? WHERE id = ?", (country, sid))
    for week in (1, 2, 3):
        await test_db.insert(
            "INSERT INTO progress (student_id, batch_id, week, issues_completed, score) VALUES (?, ?, ?, 1, 100)",
            (sid, test_batch["id"], week))
    mock_client = _make_razorpay_mock(order_id=f"order_{country}")
    with patch("routes.payments.httpx.AsyncClient", return_value=mock_client):
        r = await client.post("/api/payments/create-order", headers=auth_headers(sid),
                              json={"student_id": sid, "batch_id": test_batch["id"], "payer_region": hint})
    assert r.status_code == 200, r.text
    assert (r.json()["currency"], r.json()["amount"]) == (currency, amount)
    sent = mock_client.post.call_args.kwargs["json"]
    assert (sent["currency"], sent["amount"]) == (currency, amount)
    row = await test_db.fetch_one("SELECT amount, currency, amount_inr FROM payments WHERE razorpay_order_id = ?",
                                  (f"order_{country}",))
    assert (row["currency"], row["amount"]) == (currency, amount)
    assert row["amount_inr"] == pricing.to_inr_paise(amount, currency)


@pytest.mark.admin
async def test_usd_sale_counts_in_inr_revenue(client, admin_headers):
    """A US$4 sale shows as US$4 in the tiers, but adds its INR equivalent to revenue."""
    from tests.conftest import seed_batch
    sid = await test_db.insert(
        "INSERT INTO students (first_name, last_name, email, domain, country) VALUES ('U', 'S', 'us@x.com', 'web-dev', 'US')")
    b = await seed_batch(test_db, batch_number=77)
    await test_db.insert("INSERT INTO enrollments (student_id, batch_id) VALUES (?, ?)", (sid, b))
    inr = pricing.to_inr_paise(400, "USD")
    await test_db.insert(
        "INSERT INTO payments (student_id, batch_id, razorpay_order_id, razorpay_payment_id, amount, currency, amount_inr,"
        " status, initiated_at, completed_at) VALUES (?, ?, 'order_us', 'pay_live_us', 400, 'USD', ?, 'paid',"
        " datetime('now'), datetime('now'))", (sid, b, inr))
    r = await client.get("/api/admin/analytics?fresh=true", headers=admin_headers)
    assert r.status_code == 200
    rev = r.json()["payments"]["revenue"]
    assert rev["total_rupees"] == inr / 100
    assert [(t["label"], t["orders"]) for t in rev["tiers"]] == [("US$4", 1)]

    r = await client.get("/api/admin/payments", headers=admin_headers)
    row = r.json()["payments"][0]
    assert (row["currency"], row["amount"], row["amount_inr"]) == ("USD", 400, inr)
