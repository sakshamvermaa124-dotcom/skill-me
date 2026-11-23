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
