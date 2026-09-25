"""
Regression: Turso's HTTP (Hrana) API wraps every value as {"type": ..., "value": ...}
and sends integers as a STRING (matching how request args are encoded). Any endpoint
that does arithmetic on a fetch_one/fetch_all result (COUNT(*), pagination math, etc.)
crashed in production with `TypeError: bad operand type for unary -: 'str'` because
`_run_turso_http` returned the raw string instead of the typed value.

This only reproduces when a Turso auth token is set without the libsql_experimental
native driver installed (production's actual setup — see requirements.txt), which is
exactly the code path admin.py's pagination hit. The in-memory sqlite3 test DB never
exercises `_run_turso_http`, so this file tests the coercion helper directly.
"""
import pytest
from db.database import Database


@pytest.mark.edge
class TestHranaValueCoercion:
    def test_integer_value_sent_as_string_is_coerced_to_int(self):
        """Turso sends {"type": "integer", "value": "5"} — value is a JSON string."""
        assert Database._coerce_hrana_value({"type": "integer", "value": "5"}) == 5
        assert isinstance(Database._coerce_hrana_value({"type": "integer", "value": "5"}), int)

    def test_zero_count_is_coerced_not_falsy_string(self):
        """COUNT(*) = 0 must become int 0, not the truthy string '0'."""
        result = Database._coerce_hrana_value({"type": "integer", "value": "0"})
        assert result == 0
        assert isinstance(result, int)

    def test_float_value_passes_through(self):
        assert Database._coerce_hrana_value({"type": "float", "value": 1.5}) == 1.5

    def test_text_value_stays_string(self):
        assert Database._coerce_hrana_value({"type": "text", "value": "hello"}) == "hello"

    def test_null_value_becomes_none(self):
        assert Database._coerce_hrana_value({"type": "null"}) is None
        assert Database._coerce_hrana_value({"type": "integer", "value": None}) is None

    def test_non_dict_value_passes_through_unchanged(self):
        """Defensive: if the API shape ever changes, don't crash — pass through as-is."""
        assert Database._coerce_hrana_value("already_plain") == "already_plain"
        assert Database._coerce_hrana_value(42) == 42

    def test_malformed_integer_value_falls_back_gracefully(self):
        """If Turso ever sends a non-numeric string for an integer column, don't crash."""
        assert Database._coerce_hrana_value({"type": "integer", "value": "not_a_number"}) == "not_a_number"

    def test_coerced_count_supports_pagination_arithmetic(self):
        """The exact expression that crashed in production: max(1, -(-total // limit))."""
        total = Database._coerce_hrana_value({"type": "integer", "value": "37"})
        assert max(1, -(-total // 15)) == 3
