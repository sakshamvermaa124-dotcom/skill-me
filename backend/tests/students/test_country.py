"""
Applicant country: picked on the apply form (stored as ISO2), or inferred from the phone
number / college when an older form doesn't send it. Also covers the inference helpers
used by scripts/backfill_country.py.
"""
import pytest

from services.countries import COUNTRIES, country_from_college, country_from_phone, infer_country, normalize_iso
from tests.conftest import test_db

BASE = {
    "first_name": "Ada",
    "last_name": "Obi",
    "email": "ada@example.com",
    "phone": "+234 813 123 4567",
    "college": "University of Lagos",
    "year_of_study": "2nd Year",
    "domain": "web-dev",
    "motivation": "I want to build real projects and learn from code review every week.",
}


async def _row(email):
    return await test_db.fetch_one("SELECT country, country_source, phone FROM students WHERE email = ?", (email,))


@pytest.mark.students
class TestApplyStoresCountry:
    async def test_picked_country_is_stored(self, client):
        r = await client.post("/api/students/apply", json={**BASE, "country": "ng"})
        assert r.status_code == 200
        row = await _row("ada@example.com")
        assert row["country"] == "NG"
        assert row["country_source"] == "selected"
        assert row["phone"] == "+234 813 123 4567"

    async def test_picked_country_wins_over_phone(self, client):
        # Someone abroad on an Indian number still gets the country they chose.
        await client.post("/api/students/apply", json={**BASE, "phone": "+91 98765 43210", "country": "AE"})
        assert (await _row("ada@example.com"))["country"] == "AE"

    async def test_missing_country_is_inferred_from_phone(self, client):
        await client.post("/api/students/apply", json=BASE)
        row = await _row("ada@example.com")
        assert (row["country"], row["country_source"]) == ("NG", "phone")

    async def test_unknown_code_falls_back_to_inference(self, client):
        await client.post("/api/students/apply", json={**BASE, "country": "ZZ", "phone": "0813 123 4567"})
        row = await _row("ada@example.com")
        assert (row["country"], row["country_source"]) == ("NG", "college")

    async def test_country_longer_than_two_chars_is_rejected(self, client):
        r = await client.post("/api/students/apply", json={**BASE, "country": "India"})
        assert r.status_code == 422


class TestInference:
    def test_country_list_is_complete_and_unique(self):
        codes = [c[0] for c in COUNTRIES]
        assert len(codes) == len(set(codes)) >= 240
        assert normalize_iso(" in ") == "IN" and normalize_iso("XX") is None

    @pytest.mark.parametrize("phone,expected", [
        ("+91 98765 43210", "IN"), ("9876543210", "IN"), ("919876543210", "IN"),
        ("+1 416 555 0100", "CA"), ("+1 212 555 0100", "US"), ("+7 701 234 5678", "KZ"), ("+7 912 345 6789", "RU"),
        ("+44 7700 900123", "GB"), ("0044 1534 123456", "JE"), ("+977 9812345678", "NP"), ("+234 813 123 4567", "NG"),
        ("0813 123 4567", None), ("09876543210", None), ("123", None), ("", None),
    ])
    def test_country_from_phone(self, phone, expected):
        assert country_from_phone(phone) == expected

    def test_loose_phone_read_needs_strict_off(self):
        assert country_from_phone("2347010968937") is None
        assert country_from_phone("2347010968937", strict=False) == "NG"

    @pytest.mark.parametrize("college,expected", [
        ("COMSATS University Islamabad", "PK"), ("IIT Delhi", "IN"), ("MIT Pune", "IN"),
        ("Quezon City University", "PH"), ("Al-Farabi Kazakh National University", "KZ"),
        ("Université du Québec", "CA"), ("New Jersey Institute of Technology", "US"),
        ("University of New South Wales", "AU"), ("Some College", None), ("", None),
    ])
    def test_country_from_college(self, college, expected):
        assert country_from_college(college) == expected

    def test_college_beats_loose_phone(self):
        # An Indian mobile with an extra digit would otherwise read as Sri Lanka (+94).
        assert infer_country("94100097704", "Manipal University Jaipur") == ("IN", "college")
        assert infer_country("967783779736", "") == ("YE", "phone")
        assert infer_country(None, None) == (None, None)
