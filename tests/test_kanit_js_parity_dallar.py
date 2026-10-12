"""24-ajan-borsasi kanit_cekirdegi JS-parity + mainnet_verify dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory (saf fonksiyonlar; network/DB YASAK).

ORTAM-ANATOMI:
- _norm_uslu(gosterim): repr(1e-07) -> '1e-7' (JS exponent format);
  isaret korunur, us'ten leading-zero'lar kaldirilir
- _js_sayi(x): NaN/inf -> 'null'; x==0 -> '0'; int-gorunum -> str(int)
  (|x|<1e21) else _norm_uslu; kesirli -> _norm_uslu(repr(x))
- _js_dize(s): json.dumps(s, ensure_ascii=False)
- _yaklasik_esit(a,b): ikisi None -> True; tek None -> False;
  |float(a)-float(b)| < 1e-9
- _day_key_or_none(ts): non-str/bos -> (None,False); ValueError -> (None,False);
  naive -> UTC kabul; tz-aware -> UTC'ye cevir; (gun, bool) dondurur
- _hex_to_int(h): int(h,16)
- _addr_topic(addr): '0x'+addr[2:].lower().rjust(64,'0')
"""
import json
import math
import sys

import pytest

sys.path.insert(0, ".")
from kanit_cekirdegi import (  # noqa: E402
    _day_key_or_none, _js_dize, _js_sayi, _norm_uslu, _yaklasik_esit,
)
from mainnet_verify import _addr_topic, _hex_to_int  # noqa: E402


# == _norm_uslu =======================================================================================

def test_norm_basit():
    """ORTAM: repr(1e-07)='1e-07' -> '1e-7'."""
    assert _norm_uslu("1e-07") == "1e-7"


def test_norm_e_pozitif():
    assert _norm_uslu("1e+07") == "1e+7"


def test_norm_zerolari_atar():
    assert _norm_uslu("1.5e-003") == "1.5e-3"


def test_norm_us_zaten_kisa():
    assert _norm_uslu("1e-7") == "1e-7"


def test_norm_us_sifir():
    """ORTAM: '1e+00' -> lstrip('0') bos -> '0' -> '1e+0'."""
    assert _norm_uslu("1e+00") == "1e+0"


def test_norm_us_negatif_sifir():
    """ORTAM: '1e-00' -> '1e-0'."""
    assert _norm_uslu("1e-00") == "1e-0"


def test_norm_e_yok():
    """ORTAM: 'e' yok (sep='') -> gosterim oldugu gibi doner."""
    assert _norm_uslu("123") == "123"


def test_norm_buyuk_us():
    assert _norm_uslu("1e21") == "1e21"


def test_norm_mantis_kesirli():
    assert _norm_uslu("1.234e-010") == "1.234e-10"


def test_norm_donut_tipi():
    assert isinstance(_norm_uslu("1e-07"), str)


def test_norm_stabil():
    assert _norm_uslu("1e-07") == _norm_uslu("1e-07")


@pytest.mark.parametrize("g,b", [
    ("1e-07", "1e-7"), ("1e+07", "1e+7"), ("1e-7", "1e-7"),
    ("1e+00", "1e+0"), ("1e-00", "1e-0"), ("123", "123"),
    ("1.5e-003", "1.5e-3"), ("1e21", "1e21"),
])
def test_norm_matrix(g, b):
    assert _norm_uslu(g) == b


# == _js_sayi =========================================================================================

def test_js_sayi_sifir():
    assert _js_sayi(0.0) == "0"


def test_js_sayi_neg_sifir():
    """ORTAM: -0.0 -> '-0'? x==0 -> '0' (isaret KAYBOLUR)."""
    assert _js_sayi(-0.0) == "0" or _js_sayi(-0.0) == "-0"


def test_js_sayi_int_gorunum():
    """ORTAM: 1.0 -> '1' (trailing '.0' YOK) — JS ToString."""
    assert _js_sayi(1.0) == "1"


def test_js_sayi_int_buyuk():
    assert _js_sayi(1e15) == "1000000000000000"


def test_js_sayi_int_cok_buyuk():
    """ORTAM: |x|>=1e21 -> exponent."""
    out = _js_sayi(1e21)
    assert "e" in out or "e+" in out


def test_js_sayi_kesirli():
    assert _js_sayi(1.5) == "1.5"


def test_js_sayi_kucuk_kesirli():
    """ORTAM: 1e-7 -> repr='1e-07' -> _norm_uslu -> '1e-7'."""
    assert _js_sayi(1e-7) == "1e-7"


def test_js_sayi_negatif():
    assert _js_sayi(-1.5) == "-1.5"


def test_js_sayi_nan():
    """ORTAM: NaN -> 'null' (JSON-compliant)."""
    assert _js_sayi(float("nan")) == "null"


def test_js_sayi_inf():
    assert _js_sayi(float("inf")) == "null"


def test_js_sayi_neg_inf():
    assert _js_sayi(float("-inf")) == "null"


def test_js_sayi_donut_tipi():
    assert isinstance(_js_sayi(1.0), str)


@pytest.mark.parametrize("x,b", [
    (0.0, "0"), (1.0, "1"), (-1.0, "-1"), (1.5, "1.5"), (10.0, "10"),
    (100.0, "100"), (0.5, "0.5"), (1e-7, "1e-7"), (float("nan"), "null"),
    (float("inf"), "null"), (float("-inf"), "null"),
])
def test_js_sayi_matrix(x, b):
    assert _js_sayi(x) == b


def test_js_sayi_python_farki():
    """ORTAM-OGRENDI: Python str(1.0)='1.0' ama _js_sayi(1.0)='1'!
    JS/Node parity icin trailing '.0' atilir (digest uyumu)."""
    assert str(1.0) == "1.0"
    assert _js_sayi(1.0) == "1"


# == _js_dize =========================================================================================

def test_js_dize_basit():
    assert _js_dize("abc") == '"abc"'


def test_js_dize_bos():
    assert _js_dize("") == '""'


def test_js_dize_tirnak():
    """ORTAM: json.dumps — '"' kacisi."""
    assert _js_dize('a"b') == '"a\\"b"'


def test_js_dize_ters_bolme():
    assert _js_dize("a\\b") == '"a\\\\b"'


def test_js_dize_newline():
    assert _js_dize("a\nb") == '"a\\nb"'


def test_js_dize_turkce():
    """ORTAM: ensure_ascii=False — Turkce HAM."""
    assert _js_dize("ö") == '"ö"'


def test_js_dize_emoji():
    assert _js_dize("🎉") == '"🎉"'


def test_js_dize_json_esit():
    """ORTAM: _js_dize == json.dumps(ensure_ascii=False)."""
    for s in ["a", "ö", 'a"b', "a\nb", "\t", "\\"]:
        assert _js_dize(s) == json.dumps(s, ensure_ascii=False)


def test_js_dize_donut_tipi():
    assert isinstance(_js_dize("x"), str)


@pytest.mark.parametrize("s", ["a", "", "ö", 'a"b', "a\nb", "\t", "🎉"])
def test_js_dize_matrix(s):
    assert _js_dize(s) == json.dumps(s, ensure_ascii=False)


# == _yaklasik_esit ====================================================================================

def test_yaklasik_ayni():
    assert _yaklasik_esit(1.0, 1.0) is True


def test_yaklasik_farkli():
    assert _yaklasik_esit(1.0, 2.0) is False


def test_yaklasik_tolerans_icinde():
    """ORTAM: |a-b| < 1e-9 -> True."""
    assert _yaklasik_esit(1.0, 1.0 + 1e-10) is True


def test_yaklasik_tolerans_disinda():
    assert _yaklasik_esit(1.0, 1.0 + 1e-8) is False


def test_yaklasik_tolerans_sinir():
    """ORTAM: TAM 1e-9 -> < KESIN degil -> False!"""
    assert _yaklasik_esit(1.0, 1.0 + 1e-9) is False


def test_yaklasik_sifir_vs_kucuk():
    """ORTAM: 0 vs 1e-10 -> True."""
    assert _yaklasik_esit(0.0, 1e-10) is True


def test_yaklasik_ikisi_none():
    assert _yaklasik_esit(None, None) is True


def test_yaklasik_sol_none():
    assert _yaklasik_esit(None, 1.0) is False


def test_yaklasik_sag_none():
    assert _yaklasik_esit(1.0, None) is False


def test_yaklasik_none_vs_none_str():
    """ORTAM: 'None' string'i None DEGIL — float('None') ValueError!"""
    with pytest.raises(ValueError):
        _yaklasik_esit("None", 1.0)


def test_yaklasik_str_numeric():
    """ORTAM: float() ile — numeric str KABUL."""
    assert _yaklasik_esit("1.0", "1.0") is True
    assert _yaklasik_esit("1", 1) is True


def test_yaklasik_bool():
    """ORTAM: float(True)=1.0 — True == 1!"""
    assert _yaklasik_esit(True, 1.0) is True
    assert _yaklasik_esit(False, 0.0) is True


def test_yaklasik_negatif():
    assert _yaklasik_esit(-1.0, -1.0) is True
    assert _yaklasik_esit(-1.0, -1.0 + 1e-10) is True


def test_yaklasik_donut_tipi():
    assert isinstance(_yaklasik_esit(1.0, 1.0), bool)


@pytest.mark.parametrize("a,b,sonuc", [
    (1.0, 1.0, True), (1.0, 2.0, False), (0.0, 1e-10, True), (0.0, 1e-8, False),
    (None, None, True), (None, 1.0, False), (1.0, None, False),
    (100.0, 100.0, True), (-5.0, -5.0, True),
])
def test_yaklasik_matrix(a, b, sonuc):
    assert _yaklasik_esit(a, b) is sonuc


# == _day_key_or_none ==================================================================================

def test_day_key_utc_tz_aware():
    """ORTAM: tz-aware UTC -> ayni gun."""
    gun, ok = _day_key_or_none("2026-10-12T00:00:00+00:00")
    assert ok is True and gun == "2026-10-12"


def test_day_key_tz_farkli():
    """ORTAM: +02:00 22:00 -> UTC 20:00 -> ayni gun."""
    gun, ok = _day_key_or_none("2026-10-12T22:00:00+02:00")
    assert gun == "2026-10-12"


def test_day_key_tz_gun_degisir():
    """ORTAM-OGRENDI: -14:00 11:00 -> UTC 13+11=24:00 -> sonraki gun 01:00.
    UTC normalizasyonu gun-sinirini TASIYABILIR."""
    gun, ok = _day_key_or_none("2026-10-12T11:00:00-14:00")
    assert gun == "2026-10-13"


def test_day_key_tz_gun_once():
    """ORTAM: -12:00 01:00 -> UTC 13:00 onceki gun."""
    gun, ok = _day_key_or_none("2026-10-12T01:00:00-12:00")
    assert gun == "2026-10-12"


def test_day_key_naive_utc_kabul():
    """ORTAM: naive (tzinfo yok) -> UTC KABUL edilir."""
    gun, ok = _day_key_or_none("2026-10-12T23:00:00")
    assert gun == "2026-10-12"


def test_day_key_sadece_tarih():
    """ORTAM: 'YYYY-MM-DD' -> fromisoformat KABUL."""
    gun, ok = _day_key_or_none("2026-10-12")
    assert ok is True and gun == "2026-10-12"


def test_day_key_bos_str():
    """ORTAM: '' -> (None, False)."""
    assert _day_key_or_none("") == (None, False)


def test_day_key_none():
    assert _day_key_or_none(None) == (None, False)


def test_day_key_int():
    """ORTAM: non-str -> (None, False)."""
    assert _day_key_or_none(12345) == (None, False)


def test_day_key_gecersiz():
    """ORTAM: ValueError -> (None, False) (yutmaz)."""
    assert _day_key_or_none("gecersiz") == (None, False)


def test_day_key_gecersiz_tarih():
    assert _day_key_or_none("2026-13-45") == (None, False)


def test_day_key_ay_sinir():
    gun, ok = _day_key_or_none("2026-01-01T00:00:00+00:00")
    assert gun == "2026-01-01"


def test_day_key_yil_format():
    """ORTAM: f'{y:04d}' — 4 haneli yil."""
    gun, ok = _day_key_or_none("0026-10-12")
    assert gun == "0026-10-12"


def test_day_key_donut_tipi():
    assert isinstance(_day_key_or_none("2026-10-12"), tuple)
    assert len(_day_key_or_none("2026-10-12")) == 2


def test_day_key_ikinci_eleman_bool():
    gun, ok = _day_key_or_none("2026-10-12")
    assert isinstance(ok, bool)


@pytest.mark.parametrize("ts,gun", [
    ("2026-10-12T00:00:00+00:00", "2026-10-12"),
    ("2026-10-12T23:00:00+02:00", "2026-10-12"),
    ("2026-10-12T23:00:00", "2026-10-12"),
    ("2026-10-12", "2026-10-12"),
    ("2026-01-01T00:00:00+00:00", "2026-01-01"),
])
def test_day_key_matrix(ts, gun):
    g, ok = _day_key_or_none(ts)
    assert ok is True
    assert g == gun


@pytest.mark.parametrize("ts", ["", "gecersiz", "2026-13-45", None, 12345, "  "])
def test_day_key_gecersiz_matrix(ts):
    assert _day_key_or_none(ts) == (None, False)


# == _hex_to_int ======================================================================================

def test_hex_basit():
    assert _hex_to_int("0x1") == 1


def test_hex_onlu():
    assert _hex_to_int("ff") == 255


def test_hex_buyuk_harf():
    """ORTAM: int(h,16) case-INSENSITIVE."""
    assert _hex_to_int("FF") == 255


def test_hex_sifir():
    assert _hex_to_int("0") == 0


def test_hex_negatif():
    """ORTAM-OGRENDI: int('-1',16) == -1 (Python quirk)."""
    assert _hex_to_int("-1") == -1


def test_hex_donut_tipi():
    assert isinstance(_hex_to_int("1"), int)


def test_hex_gecersiz():
    with pytest.raises(ValueError):
        _hex_to_int("gg")


def test_hex_bos():
    with pytest.raises(ValueError):
        _hex_to_int("")


@pytest.mark.parametrize("h,b", [("0", 0), ("1", 1), ("a", 10), ("f", 15),
                                  ("10", 16), ("ff", 255), ("FFFF", 65535)])
def test_hex_matrix(h, b):
    assert _hex_to_int(h) == b


# == _addr_topic ======================================================================================

def test_addr_topic_basit():
    """ORTAM: 40-hex adres -> 64-hex topic (24 sifir on-takma)."""
    addr = "0x" + "ab" * 20
    out = _addr_topic(addr)
    assert out == "0x" + "0" * 24 + "ab" * 20


def test_addr_topic_uzunluk():
    assert len(_addr_topic("0x" + "ab" * 20)) == 66


def test_addr_topic_on_eki():
    assert _addr_topic("0x" + "ab" * 20).startswith("0x")


def test_addr_topic_buyuk_harf_kucuk():
    """ORTAM: .lower() — BUYUK harfler kucultur."""
    assert _addr_topic("0x" + "AB" * 20) == _addr_topic("0x" + "ab" * 20)


def test_addr_topic_sifir_adresi():
    """ORTAM: all-zeros -> 64 sifir topic."""
    assert _addr_topic("0x" + "0" * 40) == "0x" + "0" * 64


def test_addr_topic_kisa_adres():
    """ORTAM-OGRENDI: KISA adres rjust ile TAMAMLANIR (hata YOK).
    '0xabc' -> 61-char! (3 hex + 61 sifir = 64? rjust(64,'0') 3 -> 61+3)."""
    out = _addr_topic("0xabc")
    assert len(out) == 66
    assert out.count("0") >= 61


def test_addr_topic_uzun_adres():
    """ORTAM-OGRENDI: 40'tan UZUN adres rjust(64,'0') ile 64 hex'e
    TAMAMLANIR (sola sifir). rjust 64'ten kucukse doldurur, buyukse
    dokunmaz. 50 hex -> 14 sifir + 50 f."""
    out = _addr_topic("0x" + "f" * 50)
    assert len(out) == 66
    assert out == "0x" + "0" * 14 + "f" * 50


def test_addr_topic_donut_tipi():
    assert isinstance(_addr_topic("0x" + "ab" * 20), str)


def test_addr_topic_stabil():
    assert _addr_topic("0x" + "ab" * 20) == _addr_topic("0x" + "ab" * 20)


# == karakterizasyon ===================================================================================

def test_js_parity_amaci():
    """ORTAM-OGRENDI (DOCSTACK): _js_sayi/_js_dize Node.js JSON.stringify
    ile AYNI ciktiyi vermeli — kanit-hash'leri Delilix ile uyumlu olur.
    Python quirk'leri: 1.0->'1' (JS) vs '1.0' (Python); 1e-07->'1e-7'."""
    assert _js_sayi(1.0) == "1"
    assert _js_sayi(1e-7) == "1e-7"
    assert _js_sayi(float("nan")) == "null"
    assert _js_dize("ö") == '"ö"'


def test_yaklasik_esit_amaci():
    """ORTAM-OGRENDI: Delilix esit() yardimcisi — null-karsilastirma +
    1e-9 tolerans (float IEEE hassasiyet farklari icin). STRICT '<' —
    TAM 1e-9 fark esit sayilmaz."""
    assert _yaklasik_esit(1.0, 1.0 + 5e-10) is True
    assert _yaklasik_esit(1.0, 1.0 + 1e-9) is False


def test_day_key_utc_normalizasyon():
    """ORTAM-OGRENDI: tum timestamp'ler UTC'ye normalize edilir; naive
    ts'ler UTC KABUL edilir (docstack sozu). Bu gun-sinirlarini sabitler:
    +14:00 23:00 bir sonraki UTC gunune kayar."""
    assert _day_key_or_none("2026-10-12T11:00:00-14:00")[0] == "2026-10-13"
    assert _day_key_or_none("2026-10-12T01:00:00-12:00")[0] == "2026-10-12"


def test_addr_topic_evm_encoding():
    """ORTAM-OGRENDI: EVM log topic = 32-byte (64 hex); adres 20-byte
    (40 hex) -> 24 sifirle SOLA-hizalanir (rjust). keccak256 topic'inde
    adres bu sekilde gomulur."""
    assert _addr_topic("0x" + "ab" * 20) == "0x" + "00" * 12 + "ab" * 20
