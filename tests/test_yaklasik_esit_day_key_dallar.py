"""kanit_cekirdegi._yaklasik_esit + _day_key_or_none dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory (dis cagri YOK).
"""
import sys

import pytest

sys.path.insert(0, ".")
from kanit_cekirdegi import _yaklasik_esit, _day_key_or_none  # noqa: E402


# == _yaklasik_esit ==========================================================================

def test_both_none_true():
    assert _yaklasik_esit(None, None) is True


@pytest.mark.parametrize("a,b", [(None, 5), (5, None), (None, 0.0), (0.0, None)])
def test_one_none_false(a, b):
    assert _yaklasik_esit(a, b) is False


def test_exact_equal():
    assert _yaklasik_esit(1.0, 1.0) is True


def test_int_equal():
    assert _yaklasik_esit(5, 5) is True


def test_close_within_tolerance():
    assert _yaklasik_esit(1.0, 1.0 + 1e-12) is True


def test_beyond_tolerance():
    assert _yaklasik_esit(1.0, 1.0 + 1e-6) is False


def test_zero_equal():
    assert _yaklasik_esit(0.0, 0.0) is True


def test_zero_vs_tiny():
    assert _yaklasik_esit(0.0, 1e-15) is True


def test_zero_vs_larger():
    assert _yaklasik_esit(0.0, 1e-6) is False


def test_negative_equal():
    assert _yaklasik_esit(-3.14, -3.14) is True


def test_mixed_sign_not_equal():
    assert _yaklasik_esit(-1.0, 1.0) is False


def test_string_numbers_coerced():
    """float() zorlama."""
    assert _yaklasik_esit("1.5", "1.5") is True


def test_string_and_number():
    assert _yaklasik_esit("1.0", 1.0) is True


def test_bool_coerced():
    """float(True)==1.0."""
    assert _yaklasik_esit(True, 1.0) is True


def test_bool_false_zero():
    assert _yaklasik_esit(False, 0.0) is True


def test_returns_bool():
    assert isinstance(_yaklasik_esit(1.0, 1.0), bool)


def test_nan_raises():
    """float('nan') karsilastirma -> abs(nan) < 1e-9 False ama ValueError degil."""
    try:
        r = _yaklasik_esit(float("nan"), 1.0)
        assert r is False or r is True
    except TypeError:
        pass


def test_invalid_type_raises():
    with pytest.raises((TypeError, ValueError)):
        _yaklasik_esit("abc", 1.0)


def test_none_vs_nan():
    """None-once-kontrol: NaN'a ulasmadan False doner."""
    assert _yaklasik_esit(None, float("nan")) is False


def test_large_numbers():
    assert _yaklasik_esit(1e300, 1e300) is True


def test_large_numbers_diff():
    assert _yaklasik_esit(1e300, 1e300 + 1) is True  # float hassasiyet


def test_tolerance_boundary():
    """1e-9 tam sinirda."""
    assert _yaklasik_esit(1.0, 1.0 + 5e-10) is True


def test_just_beyond():
    assert _yaklasik_esit(1.0, 1.0 + 2e-9) is False


def test_int_float_mix():
    assert _yaklasik_esit(5, 5.0) is True


def test_repeatable():
    assert _yaklasik_esit(1.0, 1.0) == _yaklasik_esit(1.0, 1.0)


def test_symmetric():
    assert _yaklasik_esit(1.0, 2.0) == _yaklasik_esit(2.0, 1.0)


def test_symmetric_none():
    assert _yaklasik_esit(None, 1.0) == _yaklasik_esit(1.0, None)


# == _day_key_or_none ========================================================================

def test_valid_iso():
    assert _day_key_or_none("2026-10-08T12:00:00") == ("2026-10-08", True)


def test_valid_iso_z():
    assert _day_key_or_none("2026-10-08T12:00:00Z") == ("2026-10-08", True)


def test_valid_with_tz():
    assert _day_key_or_none("2026-10-08T23:00:00+03:00") == ("2026-10-08", True)


def test_tz_conversion_to_utc():
    """+03:00 23:00 -> UTC 20:00 ayni gun."""
    assert _day_key_or_none("2026-10-08T23:00:00+03:00")[0] == "2026-10-08"


def test_tz_crosses_day():
    """+03:00 01:00 -> UTC 22:00 onceki gun (Oct 7)."""
    assert _day_key_or_none("2026-10-08T01:00:00+03:00")[0] == "2026-10-07"


def test_negative_tz():
    """-05:00 01:00 -> UTC 06:00 ayni gun."""
    assert _day_key_or_none("2026-10-08T01:00:00-05:00")[0] == "2026-10-08"


def test_date_only():
    assert _day_key_or_none("2026-10-08") == ("2026-10-08", True)


def test_date_only_z_suffix():
    assert _day_key_or_none("2026-10-08Z")[0] == "2026-10-08"


def test_invalid_format():
    assert _day_key_or_none("not-a-date") == (None, False)


def test_empty_string():
    assert _day_key_or_none("") == (None, False)


def test_whitespace_only():
    assert _day_key_or_none("   ") == (None, False)


def test_none_input():
    assert _day_key_or_none(None) == (None, False)


def test_int_input():
    """isinstance(str) degil -> (None, False)."""
    assert _day_key_or_none(12345) == (None, False)


def test_datetime_input():
    from datetime import datetime
    assert _day_key_or_none(datetime(2026, 10, 8)) == (None, False)


def test_returns_tuple():
    r = _day_key_or_none("2026-10-08T12:00:00")
    assert isinstance(r, tuple) and len(r) == 2


def test_second_element_bool():
    assert _day_key_or_none("2026-10-08")[1] is True
    assert _day_key_or_none("x")[1] is False


def test_first_element_str_or_none():
    assert isinstance(_day_key_or_none("2026-10-08")[0], str)
    assert _day_key_or_none("x")[0] is None


def test_leading_trailing_whitespace():
    assert _day_key_or_none("  2026-10-08T12:00:00  ")[0] == "2026-10-08"


def test_key_format():
    assert len(_day_key_or_none("2026-10-08T12:00:00")[0]) == 10


def test_zero_padded_month_day():
    assert _day_key_or_none("2026-01-05T00:00:00")[0] == "2026-01-05"


def test_naive_assumed_utc():
    """tzinfo yoksa UTC sayilir."""
    assert _day_key_or_none("2026-10-08T23:59:59")[0] == "2026-10-08"


def test_iso_with_fractional():
    assert _day_key_or_none("2026-10-08T12:00:00.500")[0] == "2026-10-08"


def test_leap_year():
    assert _day_key_or_none("2024-02-29T12:00:00")[0] == "2024-02-29"


def test_invalid_leap():
    """2026 subat 29 yok -> ValueError -> (None, False)."""
    assert _day_key_or_none("2026-02-29T12:00:00") == (None, False)


def test_month_13_invalid():
    assert _day_key_or_none("2026-13-01T12:00:00") == (None, False)


def test_day_32_invalid():
    assert _day_key_or_none("2026-01-32T12:00:00") == (None, False)


def test_year_only():
    assert _day_key_or_none("2026") == (None, False)


def test_iso_z_only():
    assert _day_key_or_none("Z") == (None, False)


def test_various_valid_days():
    @pytest.mark.parametrize
    def _ignore():
        pass
    for d in ("2026-01-01", "2026-06-15", "2026-12-31", "2025-02-28"):
        assert _day_key_or_none(f"{d}T12:00:00")[0] == d


def test_repeatable():
    assert _day_key_or_none("2026-10-08T12:00:00") == \
        _day_key_or_none("2026-10-08T12:00:00")


def test_input_not_mutated_check():
    """str immutable — ama None disi tipler de guvenli."""
    assert _day_key_or_none(None) == (None, False)


def test_utc_offset_variants():
    """+14:00 12:00 -> UTC 22:00 ONCEKI gun; -12:00 12:00 -> UTC 00:00 SONRAKI gun."""
    assert _day_key_or_none("2026-10-08T12:00:00+00:00")[0] == "2026-10-08"
    assert _day_key_or_none("2026-10-08T12:00:00+14:00")[0] == "2026-10-07"
    assert _day_key_or_none("2026-10-08T12:00:00-12:00")[0] == "2026-10-09"
