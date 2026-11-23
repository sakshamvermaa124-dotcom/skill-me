"""
SkillMe — Certificate price by country

Each student is shown, and charged, exactly one price, decided here on the server:

  India                              INR 129   (UPI, cards, netbanking)
  Outside India                      USD 4     (international cards)
  Lower-income countries (below)     USD 2

Razorpay asked for a higher ticket on foreign payments than ₹129, so students abroad pay in USD.
The country comes from the student record (picked on the apply form, or inferred from the phone
number / college at signup); the phone number is the fallback. Only when neither tells us anything
does the browser's hint ('in' / 'intl', from its timezone) count.
"""

from __future__ import annotations

from config import settings
from services.countries import normalize_iso
from services.payment_service import phone_pay_region

# World Bank low-income + lower-middle-income economies (FY2025 classification), minus India.
# $4 is a real cost for students here, so they pay $2. Edit this set to move a country.
REDUCED_PRICE_COUNTRIES: frozenset[str] = frozenset({
    # Low income
    "AF", "BF", "BI", "CF", "TD", "CD", "ER", "ET", "GM", "GW", "KP", "LR", "MG", "MW", "ML",
    "MZ", "NE", "RW", "SL", "SO", "SS", "SD", "SY", "TG", "UG", "YE",
    # Lower-middle income
    "AO", "BD", "BJ", "BT", "BO", "KH", "CM", "KM", "CG", "CI", "DJ", "EG", "SZ", "GH", "GN",
    "HT", "HN", "IR", "JO", "KE", "KI", "KG", "LA", "LB", "LS", "MR", "FM", "MN", "MA", "MM",
    "NP", "NI", "NG", "PK", "PG", "PH", "WS", "ST", "SN", "SB", "LK", "TJ", "TZ", "TL", "TN",
    "UZ", "VU", "VN", "ZM", "ZW", "PS",
})


def _tier(tier: str) -> dict:
    """amount is in the currency's minor unit (paise / cents), as Razorpay expects."""
    if tier == "in":
        amount = settings.certificate_price_paise
        return {"tier": "in", "currency": "INR", "amount": amount, "label": f"₹{amount / 100:g}"}
    cents = settings.certificate_price_usd_reduced_cents if tier == "reduced" else settings.certificate_price_usd_cents
    return {"tier": tier, "currency": "USD", "amount": cents, "label": f"US${cents / 100:g}"}


def resolve_country_region(student: dict) -> tuple[str | None, str | None]:
    """(iso2 | None, 'in' | 'intl' | None) from what we have on record."""
    country = normalize_iso(student.get("country"))
    if country:
        return country, ("in" if country == "IN" else "intl")
    return None, phone_pay_region(student.get("phone"))


def price_for_student(student: dict, hint: str | None = None) -> dict | None:
    """The one price this student pays. None = we can't tell where they are and no hint was given."""
    country, region = resolve_country_region(student)
    if country:
        if country == "IN":
            return _tier("in")
        return _tier("reduced" if country in REDUCED_PRICE_COUNTRIES else "intl")
    region = region or (hint if hint in ("in", "intl") else None)
    if region is None:
        return None
    return _tier(region)


def price_options() -> dict:
    """Used only by the dashboard when the student's country is unknown: it picks by timezone."""
    return {"in": _tier("in"), "intl": _tier("intl")}


def to_inr_paise(amount: int, currency: str) -> int:
    """INR-equivalent of an order, so revenue analytics stay in one currency."""
    if (currency or "INR").upper() == "USD":
        return round(amount * settings.usd_inr_rate)
    return amount
