"""kanit_cekirdegi._js_dize dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory (dis cagri YOK).
Kural-5: TEST beklentileri PROBE ciktilarina gore uretildi (production DEGISmedi).

ORTAM-ANATOMI: _js_dize(s) == json.dumps(s, ensure_ascii=False) — JSON
dize-kacisi + dis tirnaklar. Tek satirlik bir wrapper; butun davranis
json.dumps'un ensure_ascii=False bayragindan gelir.

ORTAM-OGRENDILER:
  (1) ensure_ascii=False: non-ASCII karakterler LITERAL yazilir ('\\u0130'
      KULLANILMAZ) — 'İ' -> '"İ"'. Bu, JS JSON.stringify ile bire-bir
      kanit-sozlesmesidir; varsayilan json.dumps '"\\u0130"' verirdi.
  (2) Standart JSON kacislari: \" \\ \n \t \r \b \f — tek-tirnak ' ve
      eğik-cizgi / KAÇISIZ (JS ile aynı: "a'b" -> '"a\'b"' DEĞIL '"a\'b"'
      yani tirnak korumali; '/' escape EDILMEZ).
  (3) KONTROL KARAKTERLERI: \\u0000..\\u001f hepsi \\uXXXX formuna zorlanir
      ('a\\u0000b' -> '"a\\u0000b"').
  (4) Dis tirnaklar DAHIL: donus bir JSON dize-dir, tirnaklar parcadir
      (len('_js_dize("x")') == 3).
  (5) Idempotent-degil: cikti tekrar _js_dize'ye verilirse tirnaklar katlanir
      ('"a"' -> '"\\"a\\""').
"""
import json
import sys

import pytest

sys.path.insert(0, ".")
from kanit_cekirdegi import _js_dize  # noqa: E402


# == temel ===============================================================================

@pytest.mark.parametrize("s,beklenen", [
    ("", '""'),
    ("a", '"a"'),
    ("merhaba", '"merhaba"'),
    ("0", '"0"'),
])
def test_temel(s, beklenen):
    assert _js_dize(s) == beklenen


def test_bos_dize_tirnak_dahil():
    assert _js_dize("") == '""'
    assert len(_js_dize("")) == 2


def test_tirnaklar_parca():
    """ORTAM-OGRENDI (4): cikti tirnaklar DAHIL JSON dizedir."""
    out = _js_dize("x")
    assert out[0] == '"'
    assert out[-1] == '"'
    assert json.loads(out) == "x"


# == non-ASCII (ensure_ascii=False — kanit-sozlesmesi) ===================================

@pytest.mark.parametrize("s", [
    "İĞÜŞÇÖ", "ığüşçö", "é", "日本語", "中文", "😀", "𝄞",
    "a—b", "a–b", "a”b", "a´b",
])
def test_non_ascii_literal(s):
    """ORTAM-OGRENDI (1): non-ASCII LITERAL (\\u-escape YOK)."""
    assert _js_dize(s) == '"' + s + '"'


@pytest.mark.parametrize("s", ["İ", "Ğ", "Ü", "😀"])
def test_non_ascii_json_dumps_ensure_ascii_false_ile_ayni(s):
    assert _js_dize(s) == json.dumps(s, ensure_ascii=False)


def test_non_ascii_escaped_degil_karakterizasyonu():
    """ensure_ascii=False olmasaydi '\"\\u0130\"' olurdu."""
    assert "\\u0130" not in _js_dize("İ")
    assert _js_dize("İ") == '"İ"'


# == standart kacislar ====================================================================

@pytest.mark.parametrize("s,beklenen", [
    ("a\"b", '"a\\"b"'),
    ("a\\b", '"a\\\\b"'),
    ("a\nb", '"a\\nb"'),
    ("a\rb", '"a\\rb"'),
    ("a\tb", '"a\\tb"'),
    ("a\bb", '"a\\bb"'),
    ("a\fb", '"a\\fb"'),
])
def test_standart_kacislar(s, beklenen):
    assert _js_dize(s) == beklenen


@pytest.mark.parametrize("s,beklenen", [
    ("a'b", '"a\'b"'),
    ("a/b", '"a/b"'),
])
def test_tirnak_ve_slash_kacissiz(s, beklenen):
    """ORTAM-OGRENDI (2): ' ve / KAÇISIZ (JS JSON.stringify ile aynı)."""
    assert _js_dize(s) == beklenen


def test_kacis_kombinasyonu():
    assert _js_dize("a\"b\\c\n") == '"a\\"b\\\\c\\n"'


def test_coklu_kacis_ardisik():
    assert _js_dize("\n\t\r") == '"\\n\\t\\r"'


# == kontrol karakterleri (U+0000..U+001F) ================================================

@pytest.mark.parametrize("kod,beklenen", [
    (0x00, "\\u0000"),
    (0x01, "\\u0001"),
    (0x08, "\\b"),       # backspace -> \b (\uXXXX DEGIL — json.dumps short escape)
    (0x0B, "\\u000b"),
    (0x0C, "\\f"),       # form feed -> \f (\uXXXX DEGIL)
    (0x1F, "\\u001f"),
])
def test_kontrol_karakterleri_hex(kod, beklenen):
    """ORTAM-OGRENDI (3): kontrol karakterleri \\uXXXX formuna zorlanir
    (0x08 ve 0x0C istisna: json.dumps short-escape \\b/\\f kullanir)."""
    assert _js_dize("a" + chr(kod) + "b") == '"a' + beklenen + 'b"'


def test_kontrol_karakterleri_json_dumps_ile_ayni():
    for kod in range(0x20):
        s = chr(kod)
        assert _js_dize(s) == json.dumps(s, ensure_ascii=False)


# == unicode surrogatlar ==================================================================

@pytest.mark.parametrize("s", ["\ud800", "\udc00", "a\ud800b"])
def test_surrogate_gecerli_json_olmali(s):
    """json.dumps surrogatlari reddetMEZ (ensure_ascii=False)."""
    out = _js_dize(s)
    assert out[0] == '"' and out[-1] == '"'


# == json.dumps paritesi ==================================================================

@pytest.mark.parametrize("s", [
    "", "abc", "İĞÜŞÇÖ", "a\"b", "a\\b", "a\nb\t", "a\rb", "a\u0000b",
    "x/y", "a'b", "😀", "a—b", "\\n (literal)", "\t\n\r",
])
def test_json_dumps_ensure_ascii_false_paritesi(s):
    assert _js_dize(s) == json.dumps(s, ensure_ascii=False)


# == karakterizasyon quirk'leri ===========================================================

def test_idempotent_degil():
    """ORTAM-OGRENDI (5): cikti tekrar serialize -> tirnaklar katlanir."""
    once = _js_dize("a")
    iki = _js_dize(once)
    assert once == '"a"'
    assert iki == '"\\"a\\""'


def test_girdi_dize_olmali():
    """str disinda tip json.dumps kurallarina uyar (int -> tırnaksız '123')."""
    assert _js_dize(123) == '123'


def test_cikti_gecerli_json_roundtrip():
    for s in ["merhaba", "İĞÜŞÇÖ", "a\"b", "a\nb", "a\u0000b", "😀"]:
        assert json.loads(_js_dize(s)) == s


def test_uzun_dize():
    s = "x" * 10000
    out = _js_dize(s)
    assert out == '"' + "x" * 10000 + '"'
    assert len(out) == 10002
