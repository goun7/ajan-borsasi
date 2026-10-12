"""24-ajan-borsasi kanit_cekirdegi._norm_uslu/_js_sayi/_js_dize/_stringify/_day_key_or_none/_yaklasik_esit dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory (saf fonksiyonlar; network/DB YASAK).

ORTAM-ANATOMI:
- _norm_uslu(gosterim): repr(1e-7)='1e-07' -> JS '1e-7' (uss on-sifir
  atilir, isaret korunur); 'e' YOKSA gosterim OLDUGU GIBI
- _js_sayi(x): NaN/inf -> 'null' (JSON.stringify); 0/-0.0 -> '0';
  tam-sayi & abs<1e21 -> str(int); else _norm_uslu(repr(x))
- _js_dize(s): json.dumps(s, ensure_ascii=False)
- _stringify(v): recursive Node.js JSON.stringify — bool ONCE (int'ten);
  dict anahtar SIRASI KORUNUR (sorted DEGIL!); bilinmeyen tip -> dize
- _day_key_or_none(ts): (None,False) non-str/bos/gecersiz; else
  (YYYY-MM-DD, True) — naive -> +UTC, tz -> UTC'ye cevir
- _yaklasik_esit(a,b): ikisi None -> True; biri None -> False;
  abs(float(a)-float(b)) < 1e-9
"""
import json
import sys

import pytest

sys.path.insert(0, ".")
from kanit_cekirdegi import (  # noqa: E402
    _day_key_or_none, _js_dize, _js_sayi, _norm_uslu, _stringify,
    _yaklasik_esit,
)


# == _norm_uslu =======================================================================================

def test_norm_eksili():
    """ORTAM: repr(1e-7)='1e-07' -> JS '1e-7' (on-sifir ATILIR)."""
    assert _norm_uslu("1e-07") == "1e-7"


def test_norm_artili():
    """ORTAM: repr(1e21)='1e+21' -> '1e+21' (isaret KORUNUR)."""
    assert _norm_uslu("1e+21") == "1e+21"


def test_norm_mantisli():
    assert _norm_uslu("1.5e-003") == "1.5e-3"


def test_norm_e_yok():
    """ORTAM: 'e' YOKSA gosterim OLDUGU GIBI."""
    assert _norm_uslu("düz") == "düz"
    assert _norm_uslu("1350.5") == "1350.5"


def test_norm_sifir_ussu():
    """ORTAM-OGRENDI: '1e+00' -> '1e+0' (lstrip('0') -> '' -> '0'
    fallback; ISARET KORUNUR)."""
    assert _norm_uslu("1e+00") == "1e+0"
    assert _norm_uslu("1e-00") == "1e-0"


def test_norm_isaret_korunur():
    assert _norm_uslu("-2.5e-010") == "-2.5e-10"


def test_norm_buyuk_ussu():
    assert _norm_uslu("1e+100") == "1e+100"


def test_norm_bos_us():
    """ORTAM: 'e' var, us bos -> isaret yok, lstrip -> '0'."""
    assert _norm_uslu("5e") == "5e0"


def test_norm_donut_tipi():
    assert isinstance(_norm_uslu("1e-07"), str)


def test_norm_stabil():
    assert _norm_uslu("3.14e-002") == _norm_uslu("3.14e-002")


@pytest.mark.parametrize("g,b", [
    ("1e-07", "1e-7"), ("1e+21", "1e+21"), ("1.5e-003", "1.5e-3"),
    ("düz", "düz"), ("1e+00", "1e+0"),
])
def test_norm_matrix(g, b):
    assert _norm_uslu(g) == b


# == _js_sayi ==========================================================================================

def test_js_sayi_tam():
    """ORTAM: 15.0 -> '15' (JS ile ayni; tam-sayi <1e21)."""
    assert _js_sayi(15.0) == "15"


def test_js_sayi_negatif_tam():
    assert _js_sayi(-3.0) == "-3"


def test_js_sayi_sifir():
    """ORTAM: 0 -> '0'."""
    assert _js_sayi(0.0) == "0"


def test_js_sayi_negatif_sifir():
    """ORTAM-OGRENDI: -0.0 -> '0' (JS Number::toString(-0)='0' ile ayni)."""
    assert _js_sayi(-0.0) == "0"


def test_js_sayi_ondalik():
    assert _js_sayi(1350.5) == "1350.5"


def test_js_sayi_kucuk_ussu():
    """ORTAM: 1e-7 -> '1e-7' (repr('1e-07') -> _norm_uslu)."""
    assert _js_sayi(1e-07) == "1e-7"


def test_js_sayi_buyuk_ussu():
    """ORTAM: 1e21 -> '1e+21' (1e21 int'e esit DEGIL)."""
    assert _js_sayi(1e21) == "1e+21"


def test_js_sayi_tam_sinir():
    """ORTAM: abs<1e21 tam-sayi -> str(int)."""
    assert _js_sayi(1e20) == str(int(1e20))


def test_js_sayi_tam_1e21_ussu():
    """ORTAM-OGRENDI: 1e21 tam-sayi ama abs<1e21 DEGIL -> usslu '1e+21'."""
    assert _js_sayi(1e21) == "1e+21"


def test_js_sayi_nan_null():
    """ORTAM-OGRENDI: NaN -> 'null' (JSON.stringify(NaN)='null' — RFC
    8259 izin verse de JS JSON.stringify null yapar; Delilix sozlesmesi)."""
    assert _js_sayi(float("nan")) == "null"


def test_js_sayi_inf_null():
    assert _js_sayi(float("inf")) == "null"
    assert _js_sayi(float("-inf")) == "null"


def test_js_sayi_int_girisi():
    """ORTAM: int giris — x==int(x) True, abs<1e21 -> str(int)."""
    assert _js_sayi(42) == "42"


def test_js_sayi_negatif_ondalik():
    assert _js_sayi(-0.5) == "-0.5"


def test_js_sayi_cok_kucuk():
    """ORTAM: 2.93e-07 -> '2.93e-7'."""
    assert _js_sayi(2.93e-07) == "2.93e-7"


def test_js_sayi_donut_tipi():
    assert isinstance(_js_sayi(1.5), str)


@pytest.mark.parametrize("v,b", [
    (15.0, "15"), (0.0, "0"), (-0.0, "0"), (1350.5, "1350.5"),
    (1e-07, "1e-7"), (1e21, "1e+21"), (float("nan"), "null"),
    (float("inf"), "null"), (42, "42"),
])
def test_js_sayi_matrix(v, b):
    assert _js_sayi(v) == b


# == _js_dize ==========================================================================================

def test_js_dize_basit():
    """ORTAM: json.dumps(ensure_ascii=False) — tırnaklar EKLENIR."""
    assert _js_dize("merhaba") == '"merhaba"'


def test_js_dize_bos():
    assert _js_dize("") == '""'


def test_js_dize_tirnak():
    """ORTAM: JSON kacis — '"' -> '\"'."""
    assert _js_dize('a"b') == '"a\\"b"'


def test_js_dize_ters_egik():
    assert _js_dize("a\\b") == '"a\\\\b"'


def test_js_dize_newline():
    assert _js_dize("a\nb") == '"a\\nb"'


def test_js_dize_tab():
    """ORTAM: tab JSON '\\t' kacisi."""
    assert _js_dize("a\tb") == '"a\\tb"'


def test_js_dize_turkce():
    """ORTAM-OGRENDI: ensure_ascii=False — UTF-8 KORUNUR (\\uXXXX yapilmaz)."""
    assert _js_dize("Örnek") == '"Örnek"'


def test_js_dize_emoji():
    assert _js_dize("😀") == '"😀"'


def test_js_dize_kontrol():
    """ORTAM: kontrol karakterleri \\uXXXX."""
    assert _js_dize("\x01") == '"\\u0001"'


def test_js_dize_donut_tipi():
    assert isinstance(_js_dize("x"), str)


@pytest.mark.parametrize("s,b", [
    ("", '""'), ("a", '"a"'), ('"a"', '"\\"a\\""'), ("a\nb", '"a\\nb"'),
    ("Ö", '"Ö"'),
])
def test_js_dize_matrix(s, b):
    assert _js_dize(s) == b


# == _stringify ========================================================================================

def test_stringify_none():
    """ORTAM: None -> 'null' (JS null)."""
    assert _stringify(None) == "null"


def test_stringify_true():
    assert _stringify(True) == "true"


def test_stringify_false():
    assert _stringify(False) == "false"


def test_stringify_bool_once():
    """ORTAM-OGRENDI: bool int'ın ATASI — ONCE ele alinir (True '1'
    DEGIL 'true')."""
    assert _stringify(True) == "true"
    assert _stringify(1) == "1"


def test_stringify_int():
    assert _stringify(42) == "42"
    assert _stringify(-7) == "-7"
    assert _stringify(0) == "0"


def test_stringify_float_tam():
    """ORTAM: float -> _js_sayi."""
    assert _stringify(15.0) == "15"


def test_stringify_float_ondalik():
    assert _stringify(1.5) == "1.5"


def test_stringify_float_ussu():
    assert _stringify(1e-07) == "1e-7"


def test_stringify_float_nan():
    """ORTAM: NaN -> 'null' (JSON.stringify)."""
    assert _stringify(float("nan")) == "null"


def test_stringify_str():
    assert _stringify("merhaba") == '"merhaba"'


def test_stringify_str_kacis():
    assert _stringify('a"b') == '"a\\"b"'


def test_stringify_bos_liste():
    assert _stringify([]) == "[]"


def test_stringify_liste():
    """ORTAM: liste recursive."""
    assert _stringify([1, 2, 3]) == "[1,2,3]"


def test_stringify_liste_karisik():
    assert _stringify([1, "a", True, None]) == '[1,"a",true,null]'


def test_stringify_icice_liste():
    assert _stringify([[1], [2]]) == "[[1],[2]]"


def test_stringify_tuple():
    """ORTAM: tuple list gibi (list|tuple dalinda)."""
    assert _stringify((1, 2)) == "[1,2]"


def test_stringify_bos_dict():
    assert _stringify({}) == "{}"


def test_stringify_dict():
    assert _stringify({"a": 1}) == '{"a":1}'


def test_stringify_dict_anahtar_sira_korunur():
    """ORTAM-OGRENDI (KRITIK-FARK): dict anahtar SIRASI KORUNUR —
    sorted DEGIL! (js_stringify ≈ JSON.stringify; Veridrome/Fractiona
    RFC-8785 JCS sorted-ters; burada GONDERENIN SIRASI).
    AjanIslem.kanonik() sirayi sabitler (JS destructure sirasi)."""
    assert _stringify({"b": 2, "a": 1}) == '{"b":2,"a":1}'


def test_stringify_dict_icice():
    assert _stringify({"a": {"b": 1}}) == '{"a":{"b":1}}'


def test_stringify_dict_str_olmayan_anahtar():
    """ORTAM: anahtar str(k) — int anahtar string."""
    assert _stringify({1: "x"}) == '{"1":"x"}'


def test_stringify_dict_liste_deger():
    assert _stringify({"a": [1, 2]}) == '{"a":[1,2]}'


def test_stringify_bilinmeyen_tip_dize():
    """ORTAM-OGRENDI: bilinmeyen tip -> _js_dize(str(v)) (JS gibi)."""
    v = _stringify(complex(1, 2))
    assert v == json.dumps(str(complex(1, 2)), ensure_ascii=False)


def test_stringify_bilinmeyen_tip_set():
    assert _stringify({1, 2}) == json.dumps(str({1, 2}), ensure_ascii=False)


def test_stringify_donut_tipi():
    assert isinstance(_stringify(1), str)


def test_stringify_stabil():
    assert _stringify({"b": 2, "a": 1}) == _stringify({"b": 2, "a": 1})


@pytest.mark.parametrize("v,b", [
    (None, "null"), (True, "true"), (False, "false"), (42, "42"),
    (15.0, "15"), ("a", '"a"'), ([], "[]"), ({}, "{}"), ([1, "a"], '[1,"a"]'),
])
def test_stringify_matrix(v, b):
    assert _stringify(v) == b


# == _day_key_or_none ===================================================================================

def test_day_z_aware():
    """ORTAM: 'Z' -> '+00:00' -> UTC gun."""
    assert _day_key_or_none("2026-01-02T12:00:00Z") == ("2026-01-02", True)


def test_day_tarih_only():
    """ORTAM: sadece tarih -> naive 00:00 -> +UTC."""
    assert _day_key_or_none("2026-01-02") == ("2026-01-02", True)


def test_day_naive():
    """ORTAM-OGRENDI: tzinfo None -> replace(tzinfo=utc) (yerel DEGIL)."""
    assert _day_key_or_none("2026-01-02T23:00:00") == ("2026-01-02", True)


def test_day_offset_cevrilir():
    """ORTAM-OGRENDI: tz-aware offset UTC'ye CEVRILIR — 22:00+02:00 =
    20:00 UTC ayni gun; 23:00+02:00 = 21:00 UTC hala ayni gun; 01:00-05:00
    = 06:00 UTC ayni gun; gun kaymasi icin 20:00-05:00 = 01:00 UTC
    SONRAKI gun!"""
    assert _day_key_or_none("2026-01-02T22:00:00+02:00") == ("2026-01-02", True)
    assert _day_key_or_none("2026-01-02T20:00:00-05:00") == ("2026-01-03", True)


def test_day_negatif_offset():
    """ORTAM: -05:00 -> +05 saat ekle."""
    assert _day_key_or_none("2026-01-02T20:00:00-05:00") == ("2026-01-03", True)


def test_day_mikro():
    assert _day_key_or_none("2026-01-02T12:00:00.123456Z") == ("2026-01-02", True)


def test_day_bosluk_kirpma():
    """ORTAM: ts.strip() — bosluklar kirpilir."""
    assert _day_key_or_none("  2026-01-02  ") == ("2026-01-02", True)


def test_day_gecersiz():
    """ORTAM: ValueError -> (None, False)."""
    assert _day_key_or_none("gecersiz") == (None, False)


def test_day_bos():
    assert _day_key_or_none("") == (None, False)


def test_day_sadece_bosluk():
    """ORTAM: not ts.strip() -> (None, False)."""
    assert _day_key_or_none("   ") == (None, False)


def test_day_none():
    """ORTAM: isinstance str kontrolu — None -> (None, False)."""
    assert _day_key_or_none(None) == (None, False)


def test_day_int():
    assert _day_key_or_none(20260102) == (None, False)


def test_day_tarih_gecersiz():
    """ORTAM: '2026-02-30' ValueError -> (None, False)."""
    assert _day_key_or_none("2026-02-30") == (None, False)


def test_day_donut_tuple():
    assert isinstance(_day_key_or_none("2026-01-02"), tuple)


def test_day_uzunluk2():
    assert len(_day_key_or_none("2026-01-02")) == 2


def test_day_stabil():
    assert _day_key_or_none("2026-01-02T12:00:00Z") == \
        _day_key_or_none("2026-01-02T12:00:00Z")


@pytest.mark.parametrize("ts,g,b", [
    ("2026-01-02T12:00:00Z", "2026-01-02", True),
    ("2026-01-02", "2026-01-02", True),
    ("gecersiz", None, False), ("", None, False),
])
def test_day_matrix(ts, g, b):
    assert _day_key_or_none(ts) == (g, b)


# == _yaklasik_esit ====================================================================================

def test_yaklasik_ikisi_none():
    """ORTAM: ikisi None -> True."""
    assert _yaklasik_esit(None, None) is True


def test_yaklasik_biri_none():
    """ORTAM: biri None -> False (null karsilastirmasi)."""
    assert _yaklasik_esit(None, 1.0) is False
    assert _yaklasik_esit(1.0, None) is False


def test_yaklasik_esit():
    assert _yaklasik_esit(1.0, 1.0) is True


def test_yaklasik_tolerans():
    """ORTAM: 1e-9 tolerans — 1e-10 fark KABUL."""
    assert _yaklasik_esit(1.0, 1.0 + 1e-10) is True


def test_yaklasik_tolerans_disinda():
    """ORTAM: 1e-9'dan buyuk fark RED."""
    assert _yaklasik_esit(1.0, 1.0 + 1e-8) is False


def test_yaklasik_esik():
    """ORTAM-OGRENDI: tam esikte abs(diff) < 1e-9 -> False (KATI)."""
    assert _yaklasik_esit(1.0, 1.0 + 1e-9) is False


def test_yaklasik_negatif():
    assert _yaklasik_esit(-1.0, -1.0) is True


def test_yaklasik_sifir():
    assert _yaklasik_esit(0.0, 0.0) is True


def test_yaklasik_sifir_kucuk_fark():
    assert _yaklasik_esit(0.0, 1e-10) is True


def test_yaklasik_str_cast():
    """ORTAM: float() cast — string KABUL."""
    assert _yaklasik_esit("1.0", "1.0") is True
    assert _yaklasik_esit("1.0", "2.0") is False


def test_yaklasik_int():
    assert _yaklasik_esit(1, 1) is True
    assert _yaklasik_esit(1, 2) is False


def test_yaklasik_bool():
    """ORTAM: bool float'a — True==1.0."""
    assert _yaklasik_esit(True, 1.0) is True
    assert _yaklasik_esit(False, 0.0) is True


def test_yaklasik_buyuk_sayi():
    """ORTAM-OGRENDI: mutlak-tolerans — buyuk sayilarda 1e-9 cok KUCUK
    (goreceli DEGIL; abs(diff) < 1e-9)."""
    assert _yaklasik_esit(1e9, 1e9 + 1e-10) is True
    assert _yaklasik_esit(1e9, 1e9 + 1) is False


def test_yaklasik_donut_bool():
    assert isinstance(_yaklasik_esit(1.0, 1.0), bool)


def test_yaklasik_stabil():
    assert _yaklasik_esit(3.14, 3.14) is True


@pytest.mark.parametrize("a,b,r", [
    (None, None, True), (None, 1.0, False), (1.0, None, False),
    (1.0, 1.0, True), (1.0, 1.0 + 1e-10, True), (1.0, 1.0 + 1e-8, False),
])
def test_yaklasik_matrix(a, b, r):
    assert _yaklasik_esit(a, b) is r


# == karakterizasyon ===================================================================================

def test_js_sayi_amaci():
    """ORTAM-OGRENDI (DOCSTACK): Node.js JSON.stringify ile BIRE-BIR ayni
    cikti — kanit-hash'lerinin JS <-> Python tasinabilirligi; Delilix
    ile sozlesme (degistirilirse KIRILIR). NaN/Infinity -> 'null'
    (JSON.stringify JS davranisi; RFC 8259 izin verse de). -0.0 -> '0'."""
    assert _js_sayi(float("nan")) == "null"
    assert _js_sayi(15.0) == "15"


def test_stringify_amaci():
    """ORTAM-OGRENDI (KRITIK-FARK): js_stringify ≈ JSON.stringify —
    dict anahtar SIRASI KORUNUR (sorted DEGIL!). Bu RFC 8785 JCS'den
    (Veridrome/Fractiona/PQHaven sorted) KASITLI FARK: AjanIslem.kanonik()
    sirayi sabitler (JS'de contentHash {site, product_id, ...}
    destructure sirasi). bool int'ten ONCE (bool int'in atasi)."""
    assert _stringify({"b": 2, "a": 1}) == '{"b":2,"a":1}'


def test_day_key_amaci():
    """ORTAM-OGRENDI: Delilix dayKey ile ayni — ISO-8601 -> UTC
    YYYY-MM-DD; saat-dilimsiz ts'ler UTC kabul (JS new Date(...).getUTC*
    ile ayni); tz-aware offset UTC'ye cevrilir (gun kaymasi!);
    gecersiz -> (None, False) (fail-soft; day_key ValueError atar)."""
    assert _day_key_or_none("2026-01-02T20:00:00-05:00") == ("2026-01-03", True)


def test_yaklasik_esit_amaci():
    """ORTAM-OGRENDI: Delilix esit() yardimcisi — null karsilastirmasi
    (ikisi None True, biri None False) + 1e-9 MUTLAK tolerans (goreceli
    DEGIL — buyuk sayilarda cok kucuk)."""
    assert _yaklasik_esit(1.0, 1.0 + 1e-10) is True
    assert _yaklasik_esit(1.0, 1.0 + 1e-9) is False
