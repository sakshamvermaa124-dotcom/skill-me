"""phone_pay_region: which payment options a student sees by default (cards only abroad)."""

import pytest

from services.payment_service import phone_pay_region


@pytest.mark.parametrize("phone, expected", [
    ("+91 98765 43210", "in"),
    ("0091 9876543210", "in"),
    ("9876543210", "in"),
    ("98765-43210", "in"),
    ("919876543210", "in"),
    ("+23 353 620 6043", "intl"),   # Ghana, as typed in a real failed attempt
    ("+234 813 286 1326", "intl"),  # Nigeria
    ("+254 740 712372", "intl"),    # Kenya
    ("+1 415 555 0100", "intl"),
    ("00447911123456", "intl"),
    ("08131234567", None),          # Nigerian local format — don't guess
    ("0740712372", None),           # Kenyan local format — not an Indian mobile
    ("12345", None),
    ("", None),
    (None, None),
    ("+", None),
])
def test_phone_pay_region(phone, expected):
    assert phone_pay_region(phone) == expected
