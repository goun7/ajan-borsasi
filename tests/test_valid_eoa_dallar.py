"""mainnet_guard._valid_eoa dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory (ag YOK).
Kural-5: TEST beklentileri PROBE ciktilarina gore uretildi (production DEGISmedi).

ORTAM-ANATOMI: _valid_eoa(addr) 2 dal mantigi:
    (1) addr.startswith("0x") DEGILSE -> False (kisa-devre)
    (2) body = addr[2:]; len(body) == 40 VE tum char'lar hex ise -> True
EIP-55 checksum ZORUNLU DEGIL (env degerleri checksum'suz olabilir).

ORTAM-OGRENDILER:
  (1) PREFIX CASE-SENSITIVE: "0x" kabul, "0X" RED ('0X'+40hex -> False).
  (2) HEX case-INSENSITIVE: hem 'abc...' hem 'ABC...' gecerli (checksum
      kontrolu YAPILMAZ — uretim notu bunu acikca belirtir).
  (3) TAM-40 kurali: 39 hex RED, 41 hex RED, tam 40 kabul.
  (4) WHITESPACE STRIP YOK: bas/son bosluk RED (' 0x..', '0x..\\n' -> False).
  (5) NON-HEX karakter RED: 'z', 'g', '!', '_' hex-setinde degil.
  (6) GERI-ULASIM: startswith kontrolu ONCE oldugu icin 'abc' + 40 hex
      ('ab' + 'c'+40hex) yine False (prefix yok).
"""
import sys

import pytest

sys.path.insert(0, ".")
from mainnet_guard import _valid_eoa  # noqa: E402


# == gecerli adresler ====================================================================

_HEX40_LOWER = "0x" + "ab" * 20
_HEX40_UPPER = "0x" + "AB" * 20
_HEX40_MIXED = "0x" + "aB" * 20
_HEX40_ZEROS = "0x" + "00" * 20
_HEX40_NINES = "0x" + "99" * 20
_HEX40_FS = "0x" + "ff" * 20


@pytest.mark.parametrize("addr", [
    _HEX40_LOWER, _HEX40_UPPER, _HEX40_MIXED, _HEX40_ZEROS, _HEX40_NINES, _HEX40_FS,
])
def test_gecerli_40hex(addr):
    assert _valid_eoa(addr) is True


@pytest.mark.parametrize("addr", [
    "0x" + "0123456789abcdef" * 2 + "01234567",
    "0x" + "fedcba9876543210" * 2 + "fedcba98",
])
def test_gecerli_hex_dagilimi(addr):
    assert len(addr) == 42
    assert _valid_eoa(addr) is True


def test_gecerli_checksum_alinmaz():
    """ORTAM-OGRENDI (2): EIP-55 checksum ZORUNLU DEGIL — ham 40hex kabul."""
    assert _valid_eoa("0x" + "ab" * 20) is True
    assert _valid_eoa("0x" + "Ab" * 20) is True


# == prefix dali =========================================================================

@pytest.mark.parametrize("addr", [
    "",
    "abc",
    "0X" + "ab" * 20,      # ORTAM-OGRENDI (1): buyuk X RED
    "0" + "ab" * 20,
    "x" + "ab" * 20,
    "0y" + "ab" * 20,
])
def test_prefix_eksik_ve_yanlis(addr):
    assert _valid_eoa(addr) is False


def test_prefix_case_sensitive_karakterizasyonu():
    """ORTAM-OGRENDI (1): '0X' RED — startswith('0x') case-sensitive."""
    assert _valid_eoa("0x" + "ab" * 20) is True
    assert _valid_eoa("0X" + "ab" * 20) is False


def test_bos_adres():
    assert _valid_eoa("") is False


def test_sadece_prefix():
    assert _valid_eoa("0x") is False


# == uzunluk dali ========================================================================

@pytest.mark.parametrize("addr", [
    "0x" + "a" * 39,    # ORTAM-OGRENDI (3): 39 hex RED
    "0x" + "a" * 41,    # 41 hex RED
    "0x" + "a" * 1,
    "0x" + "a" * 20,
    "0x123",
])
def test_uzunluk_yanlis(addr):
    assert _valid_eoa(addr) is False


def test_tam_40_sinir_degeri():
    assert _valid_eoa("0x" + "a" * 40) is True
    assert _valid_eoa("0x" + "a" * 39) is False
    assert _valid_eoa("0x" + "a" * 41) is False


# == hex-olmayan karakterler ==============================================================

@pytest.mark.parametrize("karakter", ["z", "g", "Z", "G", "!", "_", "-", " ", "l", "o"])
def test_non_hex_karakter_red(karakter):
    """ORTAM-OGRENDI (5): hex-seti disinda herhangi bir karakter RED."""
    addr = "0x" + "a" * 39 + karakter
    assert len(addr) == 42
    assert _valid_eoa(addr) is False


@pytest.mark.parametrize("addr", [
    "0x" + "zz" * 20,
    "0x" + "g" * 40,
    "0x" + "!" * 40,
    "0x" + "_" * 40,
])
def test_hepsi_non_hex(addr):
    assert _valid_eoa(addr) is False


def test_ilk_char_non_hex():
    assert _valid_eoa("0x" + "z" + "a" * 39) is False


def test_son_char_non_hex():
    assert _valid_eoa("0x" + "a" * 39 + "z") is False


# == whitespace / format quirks ===========================================================

@pytest.mark.parametrize("addr", [
    " 0x" + "ab" * 20,       # ORTAM-OGRENDI (4): bas-bosluk RED
    "0x" + "ab" * 20 + " ",  # son-bosluk RED
    "0x" + "ab" * 20 + "\n",
    "0x" + "ab" * 20 + "\t",
    "\t0x" + "ab" * 20,
])
def test_whitespace_strip_yok(addr):
    """ORTAM-OGRENDI (4): strip YAPILMAZ — whitespace 40-char kuralini bozar."""
    assert _valid_eoa(addr) is False


def test_ic_bosluk_red():
    assert _valid_eoa("0x" + "ab" * 10 + " " + "ab" * 9) is False


# == geri-ulasim / entegrasyon ============================================================

def test_kisa_devre_prefix_once():
    """startswith kontrolu ONCE: '0x' olmadan 40 hex de RED."""
    assert _valid_eoa("ab" * 20) is False
    assert _valid_eoa("ab" * 20 + "@") is False


@pytest.mark.parametrize("n, beklenen", [
    (0, False),
    (1, False),
    (2, False),
    (40, True),
    (41, False),
])
def test_hex_uzunluk_matrisi(n, beklenen):
    assert _valid_eoa("0x" + "a" * n) is beklenen


@pytest.mark.parametrize("c, beklenen", [
    ("0", True), ("9", True), ("a", True), ("f", True),
    ("A", True), ("F", True),
    ("g", False), ("z", False), ("G", False), (" ", False), ("-", False),
])
def test_her_hex_char_siniri(c, beklenen):
    """40 adet ayni char: hepsi hex ise True, biri bile hex-disi ise False."""
    assert _valid_eoa("0x" + c * 40) is beklenen


def test_tipik_treasury_adres():
    """conftest'teki UNPUMP_TREASURY_EOA formati gecerli olmali."""
    import os
    addr = os.environ.get("UNPUMP_TREASURY_EOA", "0x" + "ab" * 20)
    assert _valid_eoa(addr) is True
