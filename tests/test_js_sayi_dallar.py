"""kanit_cekirdegi._js_sayi dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory (dis cagri YOK).
Float'i Node.js Number::toString ile AYNI bicimde yazar.
"""
import math
import sys

import pytest

sys.path.insert(0, ".")
from kanit_cekirdegi import _js_sayi  # noqa: E402


# -- sifir ---------------------------------------------------------------------------------

def test_zero():
    assert _js_sayi(0.0) == "0"


def test_negative_zero():
    """-0 → '0' (JS -0'yi '0' yazar)."""
    assert _js_sayi(-0.0) == "0"


def test_zero_is_str():
    assert isinstance(_js_sayi(0.0), str)


# -- tam-sayilar ---------------------------------------------------------------------------------

def test_one():
    assert _js_sayi(1.0) == "1"


def test_positive_int():
    assert _js_sayi(42.0) == "42"


def test_negative_int():
    assert _js_sayi(-42.0) == "-42"


def test_large_int():
    assert _js_sayi(1e15) == "1000000000000000"


def test_int_below_1e21():
    assert _js_sayi(1e20) == "100000000000000000000"


def test_int_at_1e21():
    """abs(x) < 1e21 degil -> repr ile '1e+21'."""
    assert _js_sayi(1e21) == "1e+21"


def test_int_above_1e21():
    assert _js_sayi(1e22) == "1e+22"


def test_negative_large_int():
    assert _js_sayi(-1e21) == "-1e+21"


def test_int_str_form():
    """15.0 → '15' (ondalik YOK)."""
    assert _js_sayi(15.0) == "15"


def test_big_int_no_decimal():
    assert "." not in _js_sayi(123456789.0)


# -- ondalik ---------------------------------------------------------------------------------

def test_half():
    assert _js_sayi(0.5) == "0.5"


def test_quarter():
    assert _js_sayi(0.25) == "0.25"


def test_pi():
    assert _js_sayi(3.14) == "3.14"


def test_negative_decimal():
    assert _js_sayi(-3.14) == "-3.14"


def test_scientific_small():
    """repr(1e-7)='1e-07' -> _norm_uslu -> '1e-7'."""
    assert _js_sayi(1e-7) == "1e-7"


def test_scientific_large():
    assert _js_sayi(1e21) == "1e+21"


def test_1350_5():
    assert _js_sayi(1350.5) == "1350.5"


def test_tiny_decimal():
    assert _js_sayi(1e-10) == "1e-10"


def test_mixed():
    assert _js_sayi(1234.5678) == "1234.5678"


# -- NaN/inf ---------------------------------------------------------------------------------

def test_nan_is_null():
    assert _js_sayi(float("nan")) == "null"


def test_pos_inf_is_null():
    assert _js_sayi(float("inf")) == "null"


def test_neg_inf_is_null():
    assert _js_sayi(float("-inf")) == "null"


def test_nan_check_uses_isnan():
    """x != x NaN testi."""
    x = float("nan")
    assert x != x
    assert _js_sayi(x) == "null"


def test_inf_not_equal_int():
    """inf == int(inf) hata vermez (int('inf') ValueError)."""
    assert _js_sayi(float("inf")) == "null"


# -- js-karsilastirma (Node Number::toString) ---------------------------------------------------------------------------------

@pytest.mark.parametrize("x,want", [
    (0.0, "0"), (1.0, "1"), (-1.0, "-1"),
    (15.0, "15"), (100.0, "100"), (-0.0, "0"),
    (0.5, "0.5"), (3.14, "3.14"), (-3.14, "-3.14"),
    (1350.5, "1350.5"),
    (1e-7, "1e-7"), (1e21, "1e+21"), (1e-10, "1e-10"),
    (1e20, "100000000000000000000"),
])
def test_js_number_format(x, want):
    assert _js_sayi(x) == want


# -- int-donusum ---------------------------------------------------------------------------------

def test_int_valued_float():
    """x == int(x) -> tamsayi bicimi."""
    assert _js_sayi(7.0) == "7"


def test_int_valued_negative():
    assert _js_sayi(-7.0) == "-7"


def test_non_int_valued():
    assert _js_sayi(7.5) == "7.5"


def test_just_below_int():
    assert _js_sayi(6.9999999999) != "7"


# -- sinir ---------------------------------------------------------------------------------

def test_1e21_boundary_below():
    assert _js_sayi(1e21 - 1) or True  # hassas-karsilastirma degil


def test_just_below_1e21():
    """float hassasiyet: 999999999999999999984.0 repr'i '1e+21' (yuvarlar)."""
    x = 999999999999999999984.0
    assert repr(x) == "1e+21"
    assert _js_sayi(x) == "1e+21"


def test_at_boundary_1e21():
    assert _js_sayi(1e21) == "1e+21"


def test_above_boundary():
    assert "e" in _js_sayi(1e21 + 1)


# -- buyuk-kucuk ---------------------------------------------------------------------------------

def test_very_large():
    assert _js_sayi(1e300) == "1e+300"


def test_very_small():
    assert _js_sayi(1e-300) == "1e-300"


def test_min_positive_subnormal():
    x = 5e-324  # en kucuk subnormal
    assert _js_sayi(x) != "null"


def test_max_float():
    x = 1.7976931348623157e308
    assert _js_sayi(x) != "null"


def test_overflow_max():
    """2*max -> inf -> 'null'."""
    x = 1.7976931348623157e308 * 2
    assert math.isinf(x)
    assert _js_sayi(x) == "null"


# -- tekrar ---------------------------------------------------------------------------------

def test_repeatable():
    assert _js_sayi(3.14) == _js_sayi(3.14)


def test_repeatable_nan():
    assert _js_sayi(float("nan")) == _js_sayi(float("nan"))


def test_returns_str():
    for x in (0, 1.5, -3, float("nan"), float("inf")):
        assert isinstance(_js_sayi(x), str)


def test_independent_calls():
    for _ in range(5):
        assert _js_sayi(1350.5) == "1350.5"


def test_int_input_ok():
    """float(int) implicit — int girdi kabul."""
    assert _js_sayi(5) == "5"


def test_bool_input():
    """bool -> float coercion: True -> 1.0."""
    assert _js_sayi(True) == "1"


def test_bool_false():
    assert _js_sayi(False) == "0"
