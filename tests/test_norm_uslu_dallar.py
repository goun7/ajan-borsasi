"""kanit_cekirdegi._norm_uslu dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory (dis cagri YOK).
Python repr float ussunu JS Number::ToString bicimine getirir.
"""
import sys

import pytest

sys.path.insert(0, ".")
from kanit_cekirdegi import _norm_uslu  # noqa: E402


# -- e-yok ---------------------------------------------------------------------------------

def test_no_e_returns_input():
    assert _norm_uslu("3.14") == "3.14"


def test_integer_no_e():
    assert _norm_uslu("42") == "42"


def test_empty_string():
    assert _norm_uslu("") == ""


def test_e_alone():
    """'e'.partition('e') = ('', 'e', '') -> sep DOLU -> us '' -> '0'."""
    assert _norm_uslu("e") == "e0"


def test_trailing_e():
    """('3', 'e', '') -> bos us -> '0' doldurulur."""
    assert _norm_uslu("3e") == "3e0"


def test_leading_e():
    assert _norm_uslu("e5") == "e5"


# -- pozitif-us ---------------------------------------------------------------------------------

def test_e_plus_leading_zero():
    """repr(1e-7)='1e-07' -> JS '1e-7'."""
    assert _norm_uslu("1e-07") == "1e-7"


def test_e_plus_explicit():
    assert _norm_uslu("1e+07") == "1e+7"


def test_e_plus_no_leading_zero():
    assert _norm_uslu("1e+7") == "1e+7"


def test_e_minus_double_zero():
    assert _norm_uslu("1e-007") == "1e-7"


def test_e_minus_single_zero():
    assert _norm_uslu("1e-0") == "1e-0"


def test_e_minus_none_zero():
    """us='0' -> lstrip('0') or '0' = '0'."""
    assert _norm_uslu("1e-0") == "1e-0"


def test_explicit_plus_kept():
    assert _norm_uslu("2e+3") == "2e+3"


def test_minus_kept():
    assert _norm_uslu("2e-3") == "2e-3"


# -- us-basamaklari ---------------------------------------------------------------------------------

def test_two_digit_us():
    assert _norm_uslu("1e+21") == "1e+21"


def test_two_digit_us_minus():
    assert _norm_uslu("1e-21") == "1e-21"


def test_three_digit_us():
    assert _norm_uslu("1e+300") == "1e+300"


def test_leading_zeros_multi():
    assert _norm_uslu("1e-007") == "1e-7"


def test_all_zeros_us():
    """'e+00' -> 'e+0'."""
    assert _norm_uslu("1e+00") == "1e+0"


def test_us_one():
    assert _norm_uslu("1e+1") == "1e+1"


# -- repr-entegrasyonu ---------------------------------------------------------------------------------

def test_repr_1e_minus_7():
    assert _norm_uslu(repr(1e-7)) == "1e-7"


def test_repr_1e21():
    assert _norm_uslu(repr(1e21)) == "1e+21"


def test_repr_1e_minus_21():
    assert _norm_uslu(repr(1e-21)) == "1e-21"


def test_repr_1e_minus_10():
    assert _norm_uslu(repr(1e-10)) == "1e-10"


def test_repr_small_no_e():
    assert _norm_uslu(repr(0.001)) == "0.001"


def test_repr_large_no_e():
    assert _norm_uslu(repr(123456.789)) == "123456.789"


def test_repr_zero():
    assert _norm_uslu(repr(0.0)) == "0.0"


def test_repr_negative():
    assert _norm_uslu(repr(-1e-7)) == "-1e-7"


# -- mantis-korunur ---------------------------------------------------------------------------------

def test_mantis_with_dot():
    assert _norm_uslu("3.14e-05") == "3.14e-5"


def test_massis_integer():
    assert _norm_uslu("5e-3") == "5e-3"


def test_mantis_negative():
    assert _norm_uslu("-1e-07") == "-1e-7"


def test_mantis_plus():
    assert _norm_uslu("+1e-07") == "+1e-7"


def test_mantis_scientific():
    """mantis icinde e yok (partition ilk 'e'den boler)."""
    assert _norm_uslu("1.5e-10") == "1.5e-10"


# -- buyuk 'E' ---------------------------------------------------------------------------------

def test_uppercase_e_no_match():
    """partition('e') BUYUK E'yi bolmez."""
    assert _norm_uslu("1E-07") == "1E-07"


def test_uppercase_e_passthrough():
    assert _norm_uslu("1E5") == "1E5"


# -- tekrar ---------------------------------------------------------------------------------

def test_repeatable():
    assert _norm_uslu("1e-07") == _norm_uslu("1e-07")


def test_idempotent():
    once = _norm_uslu("1e-007")
    twice = _norm_uslu(once)
    assert once == twice == "1e-7"


def test_idempotent_plus():
    x = _norm_uslu("1e+007")
    assert _norm_uslu(x) == x


def test_no_e_idempotent():
    x = _norm_uslu("3.14")
    assert _norm_uslu(x) == x


# -- karmasik ---------------------------------------------------------------------------------

def test_very_long_us():
    assert _norm_uslu("1e-0000000007") == "1e-7"


def test_mantis_many_digits():
    m = "1" + "0" * 20
    assert _norm_uslu(f"{m}e-07") == f"{m}e-7"


def test_us_only_minus_sign():
    """us='-' -> isaret='-', us='' -> lstrip or '0'."""
    assert _norm_uslu("1e-") == "1e-0"


def test_us_only_plus_sign():
    assert _norm_uslu("1e+") == "1e+0"


# -- js-karsilastirma ---------------------------------------------------------------------------------

def test_js_format_examples():
    cases = {
        "1e-07": "1e-7", "1e+07": "1e+7", "1e-21": "1e-21",
        "1e+21": "1e+21", "5e-3": "5e-3", "2.5e+10": "2.5e+10",
    }
    for src, want in cases.items():
        assert _norm_uslu(src) == want, src
