"""mainnet_verify._hex_to_int + _addr_topic dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory (int/str, dis cagri YOK).
Hex-parse ve adres-topic gomme (32-byte basindan sifir-doldurma).
"""
import sys

import pytest

sys.path.insert(0, ".")
from mainnet_verify import _hex_to_int, _addr_topic  # noqa: E402


# == _hex_to_int =============================================================================

def test_basic():
    assert _hex_to_int("10") == 16


def test_zero():
    assert _hex_to_int("0") == 0


def test_ff():
    assert _hex_to_int("ff") == 255


def test_returns_int():
    assert isinstance(_hex_to_int("10"), int)


def test_with_0x_prefix():
    assert _hex_to_int("0x10") == 16


def test_uppercase():
    assert _hex_to_int("FF") == 255


def test_mixed_case():
    assert _hex_to_int("AbCdEf") == 0xabcdef


def test_empty_raises():
    with pytest.raises(ValueError):
        _hex_to_int("")


def test_invalid_char_raises():
    with pytest.raises(ValueError):
        _hex_to_int("gg")


def test_invalid_raises():
    with pytest.raises(ValueError):
        _hex_to_int("xyz")


def test_whitespace_stripped():
    """ORTAM: int(str,16) bosluklari KIRPAR (ValueError DEGIL)."""
    assert _hex_to_int(" 10") == 16


def test_long_hash():
    h = "0x" + "a" * 64
    assert _hex_to_int(h) == int("a" * 64, 16)


def test_32_byte_max():
    assert _hex_to_int("f" * 64) == 2**256 - 1


def test_typed_hash():
    """0x1234..."""
    assert _hex_to_int("0x1234") == 0x1234


def test_single_digit():
    assert _hex_to_int("a") == 10


def test_big_number():
    assert _hex_to_int("deadbeef") == 3735928559


@pytest.mark.parametrize("h,want", [
    ("0", 0), ("1", 1), ("a", 10), ("f", 15), ("10", 16),
    ("ff", 255), ("100", 256), ("0x64", 100),
])
def test_matrix(h, want):
    assert _hex_to_int(h) is want


@pytest.mark.parametrize("bad", ["", "g", "zz", "0xg", "1.5"])
def test_invalid_matrix(bad):
    with pytest.raises(ValueError):
        _hex_to_int(bad)


def test_negative_accepted():
    """ORTAM: int('-1',16) = -1 (negatif-isyaret kabul)."""
    assert _hex_to_int("-1") == -1


# == _addr_topic =============================================================================

def test_addr_topic_length():
    assert len(_addr_topic("0x" + "a" * 40)) == 66


def test_addr_topic_pads():
    """40-harf adres 32-byte'a 0-doldurulur."""
    t = _addr_topic("0x" + "a" * 40)
    assert t == "0x" + "0" * 24 + "a" * 40


def test_returns_str():
    assert isinstance(_addr_topic("0x" + "a" * 40), str)


def test_starts_0x():
    assert _addr_topic("0x" + "b" * 40).startswith("0x")


def test_lowercase():
    """buyuk-harf adres kucuk-harfe cevrilir."""
    t = _addr_topic("0xABCDEF" + "0" * 34)
    assert "abcdef" in t


def test_mixed_case_lowered():
    t = _addr_topic("0xAbCdEf" + "0" * 34)
    assert "abcdef" in t and "ABCD" not in t


def test_checksum_address():
    """EIP-55 checksum adres kucuk-harfe duser."""
    addr = "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"
    t = _addr_topic(addr)
    assert addr[2:].lower() in t


def test_all_zeros():
    t = _addr_topic("0x" + "0" * 40)
    assert t == "0x" + "0" * 64


def test_all_ff():
    t = _addr_topic("0x" + "f" * 40)
    assert t == "0x" + "0" * 24 + "f" * 40


def test_no_prefix():
    """'0x' yoksa addr[2:] ilk-2 karakteri atar."""
    t = _addr_topic("zz" + "a" * 40)
    assert t == "0x" + "0" * 24 + "a" * 40


def test_short_addr_pads_more():
    """kisa adres daha fazla 0-dolgu."""
    t = _addr_topic("0xabc")
    assert t == "0x" + "0" * 61 + "abc"


def test_40_chars_exact():
    addr = "0x" + "1234567890abcdef" * 2 + "12345678"
    assert len(addr) == 42
    t = _addr_topic(addr)
    assert t == "0x" + "0" * 24 + addr[2:]


def test_deterministic():
    addr = "0x" + "a" * 40
    assert _addr_topic(addr) == _addr_topic(addr)


def test_unicode_raises_or_truncates():
    """Turkce karakter addr[2:] farkli uzunluk verir."""
    t = _addr_topic("0x" + "ç" * 40)
    assert t.startswith("0x")


def test_topic_is_64_hex():
    t = _addr_topic("0x" + "deadbeef" * 5)
    assert len(t) == 66
    int(t, 16)


def test_roundtrip_value():
    """gomme adresin tam degerini tasir."""
    addr = "0x" + "a" * 40
    t = _addr_topic(addr)
    assert int(t, 16) == int(addr, 16)


@pytest.mark.parametrize("n", range(0, 41, 5))
def test_various_lengths(n):
    addr = "0x" + "a" * n
    t = _addr_topic(addr)
    assert len(t) == 66
    assert t.endswith("a" * n)
