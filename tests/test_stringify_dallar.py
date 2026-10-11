"""kanit_cekirdegi._stringify dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory (dis cagri YOK).
Kural-5: TEST beklentileri PROBE ciktilarina gore uretildi (production DEGISmedi).

ORTAM-ANATOMI: _stringify Node.js JSON.stringify bire-bir portudur — 6 tip
dalina girer: None -> "null", bool -> "true"/"false", str -> _js_dize,
int -> str(v), float -> _js_sayi, list/tuple -> "[...]", Mapping -> "{...}",
bilinmeyen-tip -> _js_dize(str(v)).

ORTAM-OGRENDILER:
  (1) DAL-SIRASI: bool, int'in ATASIDIR (isinstance(True,int)==True) — bool
      dalı ONCE gelmelidir; yoksa True -> "1" olurdu. Bu kritik bir
      characterization quirk'tir: [True,False,0,1] -> '[true,false,0,1]'.
  (2) TUPLE -> array: JS tuple bilmez, (1,2) -> '[1,2]' (list ile ayni dal).
  (3) BIG-INT: Python int arbitrary-precision'dur — 2**256 TAM basamaklarla
      yazilir ('115792...639936'). GERCEK JS JSON.stringify '1.1579e+77'
      verirdi; bu port JS Number sinirini TAKLIT ETMEZ (kanit-sozlesmesi:
      buyuk tam-sayilar metin tasiyicida kayipsiz kalmalidir).
  (4) DICT-ANAHTAR: str(k) ile dizelestirilir — {None:1} -> '{"None":1}',
      {True:1} -> '{"True":1}', {1.5:"x"} -> '{"1.5":"x"}'.
  (5) DICT-SIRA: insertion-order korunur (JS ile ayni) — {'b':1,'a':2} ->
      '{"b":1,"a":2}' (alfabetik DEGIL).
  (6) BILINMEYEN-TIP: fall-through _js_dize(str(v)) — set -> '"{1, 2}"',
      bytes -> '"b\'ab\'"', custom-obj -> '"nesne"'.
  (7) NON-ASCII korunur (ensure_ascii=False): "İĞÜŞÇÖ"/"😀"/"𝄞" literal.
"""
import sys

import pytest

sys.path.insert(0, ".")
from kanit_cekirdegi import _stringify  # noqa: E402


# == None dalı ==========================================================================

def test_none():
    assert _stringify(None) == "null"


@pytest.mark.parametrize("v", [None])
def test_none_tek(v):
    assert _stringify(v) == "null"


def test_none_list_icinde():
    assert _stringify([None, None]) == "[null,null]"


def test_none_dict_degeri():
    assert _stringify({"a": None}) == '{"a":null}'


# == bool dalı (int'ten ONCE — kritik dal-sirasi) =======================================

@pytest.mark.parametrize("v,beklenen", [(True, "true"), (False, "false")])
def test_bool(v, beklenen):
    assert _stringify(v) == beklenen


def test_bool_int_atasi_karakterizasyonu():
    """ORTAM-OGRENDI (1): bool int'in atasidir; bool dali ONCE calismali."""
    assert isinstance(True, int) is True
    assert _stringify(True) == "true"
    assert _stringify(False) == "false"


def test_bool_list_ici_true_once():
    assert _stringify([True, False, 0, 1]) == "[true,false,0,1]"


def test_bool_dict_degeri():
    assert _stringify({"acik": True, "kapali": False}) == '{"acik":true,"kapali":false}'


def test_bool_nested():
    assert _stringify([{"x": [True]}]) == '[{"x":[true]}]'


# == str dalı (via _js_dize) ============================================================

@pytest.mark.parametrize("s,beklenen", [
    ("", '""'),
    ("merhaba", '"merhaba"'),
    ("a\"b", '"a\\"b"'),
    ("a\\b", '"a\\\\b"'),
    ("a\nb", '"a\\nb"'),
    ("a\tb", '"a\\tb"'),
    ("a\rb", '"a\\rb"'),
    ("a\rb\t", '"a\\rb\\t"'),
    ("a\u0000b", '"a\\u0000b"'),
    ("x/y", '"x/y"'),
])
def test_str(s, beklenen):
    assert _stringify(s) == beklenen


@pytest.mark.parametrize("s", ["İĞÜŞÇÖ", "é", "😀", "𝄞", "日本語"])
def test_str_unicode_korunur(s):
    """ORTAM-OGRENDI (7): non-ASCII literal (ensure_ascii=False)."""
    assert _stringify(s) == '"' + s + '"'


def test_str_escaping_delim_kombinasyonu():
    assert _stringify("a\"b\\c\n") == '"a\\"b\\\\c\\n"'


# == int dalı ===========================================================================

@pytest.mark.parametrize("v,beklenen", [
    (0, "0"),
    (42, "42"),
    (-7, "-7"),
    (1, "1"),
    (-1, "-1"),
    (10**6, "1000000"),
])
def test_int(v, beklenen):
    assert _stringify(v) == beklenen


@pytest.mark.parametrize("n", [2**64, 2**128, 2**256, 10**30])
def test_int_big_arbitrary_precision(n):
    """ORTAM-OGRENDI (3): buyuk tam-sayi TAM basamakla (JS exp DEGIL)."""
    assert _stringify(n) == str(n)


@pytest.mark.parametrize("n", [-(2**64), -(2**128)])
def test_int_big_negatif(n):
    assert _stringify(n) == str(n)


# == float dalı (via _js_sayi) ===========================================================

@pytest.mark.parametrize("v,beklenen", [
    (0.0, "0"),
    (-0.0, "0"),
    (15.0, "15"),
    (3.0, "3"),
    (-4.0, "-4"),
    (3.5, "3.5"),
    (1350.5, "1350.5"),
    (1e21, "1e+21"),
    (1e22, "1e+22"),
    (1e-7, "1e-7"),
    (5e-324, "5e-324"),
    (1.7976931348623157e308, "1.7976931348623157e+308"),
])
def test_float(v, beklenen):
    assert _stringify(v) == beklenen


@pytest.mark.parametrize("v", [float("nan"), float("inf"), float("-inf")])
def test_float_nan_inf_null(v):
    """JSON.stringify(NaN|Infinity) -> null (kanit-sozlesmesi)."""
    assert _stringify(v) == "null"


def test_float_neg_sifir():
    assert _stringify(-0.0) == "0"


def test_float_list_ici():
    assert _stringify([1.5, 2.0, float("nan")]) == "[1.5,2,null]"


# == list dalı ===========================================================================

def test_list_bos():
    assert _stringify([]) == "[]"


def test_list_homojen():
    assert _stringify([1, 2, 3]) == "[1,2,3]"


def test_list_karisik():
    assert _stringify([1, "a", None, True]) == '[1,"a",null,true]'


def test_list_nested():
    assert _stringify([[1, 2], [3]]) == "[[1,2],[3]]"


def test_list_bosluk_yok_seperator():
    assert "," in _stringify([1, 2])
    assert " " not in _stringify([1, 2])


# == tuple dalı (list ile ayni) ==========================================================

@pytest.mark.parametrize("v,beklenen", [
    ((), "[]"),
    ((1,), "[1]"),
    ((1, 2), "[1,2]"),
    ((1, (2, 3)), "[1,[2,3]]"),
    (("a", 1, None), '["a",1,null]'),
])
def test_tuple_array_olarak(v, beklenen):
    """ORTAM-OGRENDI (2): tuple -> array (JS tuple bilmez)."""
    assert _stringify(v) == beklenen


def test_tuple_list_ayni_cikti():
    assert _stringify((1, 2, 3)) == _stringify([1, 2, 3])


# == Mapping dalı ========================================================================

@pytest.mark.parametrize("v,beklenen", [
    ({}, "{}"),
    ({"a": 1}, '{"a":1}'),
    ({"b": 1, "a": 2}, '{"b":1,"a":2}'),
    ({"k": [1, {"x": None}]}, '{"k":[1,{"x":null}]}'),
])
def test_dict(v, beklenen):
    assert _stringify(v) == beklenen


def test_dict_sira_insertion_korunur():
    """ORTAM-OGRENDI (5): insertion-order (alfabetik DEGIL)."""
    out = _stringify({"z": 1, "a": 2, "m": 3})
    assert out == '{"z":1,"a":2,"m":3}'


@pytest.mark.parametrize("v,beklenen", [
    ({1: "x", 2: "y"}, '{"1":"x","2":"y"}'),
    ({None: 1}, '{"None":1}'),
    ({True: 1}, '{"True":1}'),
    ({1.5: "x"}, '{"1.5":"x"}'),
])
def test_dict_anahtar_dizelesir(v, beklenen):
    """ORTAM-OGRENDI (4): anahtarlar str(k) ile dizelestirilir."""
    assert _stringify(v) == beklenen


def test_dict_list_of_dicts():
    assert _stringify([{"k": 1}, {"k": 2}]) == '[{"k":1},{"k":2}]'


# == bilinmeyen-tip dalı (fall-through) ==================================================

class _Nesne:
    def __str__(self):
        return "nesne"


def test_bilinmeyen_tip_custom_obj():
    """ORTAM-OGRENDI (6): fall-through _js_dize(str(v))."""
    assert _stringify(_Nesne()) == '"nesne"'


def test_bilinmeyen_tip_bytes():
    assert _stringify(b"ab") == '"b\'ab\'"'


def test_bilinmeyen_tip_set():
    assert _stringify({1, 2}) == '"{1, 2}"'


# == derin yuvalama / entegrasyon ========================================================

def test_derin_yuvalama():
    assert _stringify([{"a": [None, (1, {"b": 2.5})]}]) == '[{"a":[null,[1,{"b":2.5}]]}]'


def test_karisik_yapi_tam():
    out = _stringify({
        "agent_id": "0x" + "ab" * 20,
        "operation": "listele",
        "amount": 15.0,
        "ref": None,
        "ts": "2026-10-08T00:00:00Z",
        "source": "İĞÜŞÇÖ",
    })
    assert out == (
        '{"agent_id":"0x' + "ab" * 20 + '",'
        '"operation":"listele",'
        '"amount":15,'
        '"ref":null,'
        '"ts":"2026-10-08T00:00:00Z",'
        '"source":"İĞÜŞÇÖ"}'
    )


def test_idempotent_metin():
    """Ayni deger tekrar serialize -> ayni metin (kanonik-sabit)."""
    v = {"a": [1, 2.5, "x", None, True], "b": {"c": (1, 2)}}
    assert _stringify(v) == _stringify(v)


@pytest.mark.parametrize("v,beklenen", [
    (None, "null"),
    (True, "true"),
    ("x", '"x"'),
    (5, "5"),
    (2.5, "2.5"),
    ([], "[]"),
    ({}, "{}"),
])
def test_tip_dallari_tek(v, beklenen):
    assert _stringify(v) == beklenen
