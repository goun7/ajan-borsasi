# -*- coding: utf-8 -*-
"""ajan-borsasi ek dal-kesen testleri — ast_scan'in buldugu son 2 kapsanmamis fonksiyon.

  ast_scan.py mesh-geneli taramasinda ajan-borsasi icin SADECE 2 public
  fonksiyon test-edilmemis-buldu:
    1. x402_servis.py::asdict_safe(o)  (3 satir — ama hata-yolu guvenlik-relevant)
    2. seed.py::main()                 (72 satirlik tohumlama-dongusu)
  Diger tum public fonksiyonlar mevcut test-dosyalarinda REFERANS geciyor.

Fonksiyon basina dal listesi:

asdict_safe(o):
    basari: dataclass -> dict (alan-adlari ile)
    basari: ic-ice dataclass -> ic-dict (recursive)
    basari: dataclass + dict/list alani -> derin-kopya
    sinir: bos dataclass -> {}
    hata:  int -> TypeError (dataclass degil; karsi-taraf sesli)
    hata:  str -> TypeError
    hata:  dict -> TypeError (asdict Mapping degil dataclass bekler)
    hata:  None -> TypeError
    hata:  list -> TypeError

main() (seed.py):
    basari: tum AGENTS listelenir — cikti "listelendi" her ajan icin
    hata:  list_agent ValueError -> cikti "✗ {name}: {e}" (sessiz-gec, devam)
    basari: alici-dongusu match -> complete_work -> "is tamamlandi"
    hata:  match_bid None -> "eslesmedi" yolu (if/else else-dali)
    sinir: AGENTS bos -> dongu-icine-girmez, sadece baslik
    sinir: DB_PATH asla ev-dizinine yazilmaz (tmp_path veya stub; Kural-4)
    dal:   borsa_core fonksiyonlari monkeypatch-stub (GERCEK-sqlite YOK)

Kurallar: Kural-1 (yeni-dosya), Kural-4 (saf-in-memory; hicbir gercek
sqlite/ev-dizini/subprocess YOK — borsa_core monkeypatch ile stub).
"""
from __future__ import annotations

import dataclasses
import io
import sys
import types

import pytest


# ───────────── asdict_safe ─────────────
class TestAsdictSafe:
    def test_basaria_dataclass_dict(self):
        from x402_servis import asdict_safe

        @dataclasses.dataclass
        class U:
            id: str
            ucret: float

        o = U(id="x1", ucret=0.25)
        assert asdict_safe(o) == {"id": "x1", "ucret": 0.25}

    def test_basaria_ic_ice_dataclass(self):
        from x402_servis import asdict_safe

        @dataclasses.dataclass
        class Ic:
            deger: int

        @dataclasses.dataclass
        class Dis:
            ad: str
            ic: Ic

        o = Dis(ad="d", ic=Ic(deger=5))
        assert asdict_safe(o) == {"ad": "d", "ic": {"deger": 5}}

    def test_basaria_dict_ve_list_alani(self):
        from x402_servis import asdict_safe

        @dataclasses.dataclass
        class S:
            etiketler: list
            meta: dict

        o = S(etiketler=["a", "b"], meta={"k": 1})
        out = asdict_safe(o)
        assert out["etiketler"] == ["a", "b"]
        assert out["meta"] == {"k": 1}
        # derin-kopya: orijinali degistirince cikti degismemeli
        o.etiketler.append("c")
        assert "c" not in out["etiketler"]

    def test_sinir_bos_dataclass(self):
        from x402_servis import asdict_safe

        @dataclasses.dataclass
        class Bos:
            pass

        assert asdict_safe(Bos()) == {}

    @pytest.mark.parametrize("deger", [42, "metin", None, [1, 2], {"a": 1}])
    def test_hata_dataclass_degil_type_error(self, deger):
        from x402_servis import asdict_safe

        with pytest.raises(TypeError):
            asdict_safe(deger)

    def test_hata_frozen_dataclass(self):
        from x402_servis import asdict_safe

        @dataclasses.dataclass(frozen=True)
        class Dondurulmus:
            x: int

        # frozen dataclass yine de asdict ile dict'e cevrilir (hata DEGIL)
        assert asdict_safe(Dondurulmus(x=7)) == {"x": 7}


# ───────────── seed.main ─────────────
class TestSeedMain:
    """borsa_core monkeypatch-stub ile — GERCEK sqlite YOK (Kural-4)."""

    def _stub_borsa(self, monkeypatch, *,
                    list_ajan_hata=None,
                    match_sonuc=None,
                    complete_sonuc=None,
                    kayit_sirasi=None):
        """seed.py'nin import ettigi borsa_core'u sahte-modul ile degistir."""
        cagri = {"list": [], "bid": [], "match": [], "complete": []}

        @dataclasses.dataclass
        class Ajan:
            name: str
            price_target: float
            service: str

        @dataclasses.dataclass
        class Bid:
            bid_id: str
            amount: float
            nonce: int

        @dataclasses.dataclass
        class Match:
            match_id: str

        @dataclasses.dataclass
        class Is:
            work_done: bool
            receipt_hash: str

        def _list_agent(agent_id, name, service, price_target, proof, db):
            cagri["list"].append((agent_id, name, db))
            if list_ajan_hata is not None:
                raise ValueError(list_ajan_hata)
            return Ajan(name=name, price_target=price_target, service=service)

        def _place_bid(agent_id, buyer_id, amount, work_spec, nonce, db):
            cagri["bid"].append((agent_id, buyer_id, amount))
            return Bid(bid_id="bid-1", amount=amount, nonce=1)

        def _match_bid(bid_id, db):
            cagri["match"].append(bid_id)
            return match_sonuc

        def _complete_work(match_id, receipt_hash, db):
            cagri["complete"].append((match_id, receipt_hash))
            return Is(work_done=True, receipt_hash=receipt_hash)

        def _market_summary(db):
            return "3 ajan | 1 is | dogrulandi"

        sahte = types.ModuleType("borsa_core")
        sahte.DB_PATH = "/tmp/STUB-ASLA-YAZILMAZ"
        sahte.list_agent = _list_agent
        sahte.place_bid = _place_bid
        sahte.match_bid = _match_bid
        sahte.complete_work = _complete_work
        sahte.market_summary = _market_summary
        monkeypatch.setitem(sys.modules, "borsa_core", sahte)
        return cagri

    def _kos(self, monkeypatch):
        import contextlib
        import importlib
        import seed
        importlib.reload(seed)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            seed.main()
        return buf.getvalue()

    def test_basaria_tum_ajanlar_listelenir(self, monkeypatch):
        cagri = self._stub_borsa(monkeypatch)
        out = self._kos(monkeypatch)
        # 3 sabit-ajan seed.AGENTS'te tanimli
        assert len(cagri["list"]) == 3
        for ad in ("VadeDostu", "RepriceAI", "CallSnap"):
            assert ad in out
        assert "listelendi" in out

    def test_hata_list_agent_value_error_sessiz_gec(self, monkeypatch):
        self._stub_borsa(monkeypatch, list_ajan_hata="gecersiz agent_id")
        out = self._kos(monkeypatch)
        assert "✗" in out
        # hataya ragmen dongu devam eder — sonraki ajanlar denenir
        assert out.count("✗") >= 1
        # alici-dongusu yine de kosar
        assert "Alıcı döngüsü" in out

    def test_basaria_alici_dongusu_match_tamamlanir(self, monkeypatch):
        @dataclasses.dataclass
        class Match:
            match_id: str

        self._stub_borsa(monkeypatch,
                         match_sonuc=Match(match_id="m-1" * 10))
        out = self._kos(monkeypatch)
        assert "iş tamamlandı" in out
        assert "receipt:callsnap" in out

    def test_hata_match_bid_none_eslesmedi(self, monkeypatch):
        self._stub_borsa(monkeypatch, match_sonuc=None)
        out = self._kos(monkeypatch)
        # else-dali: match None -> eslesmedi-mesaji (✗ isareti ile)
        assert "eşleşmedi" in out
        assert "iş tamamlandı" not in out

    def test_sinir_db_path_stub_tmp_degil_ev(self, monkeypatch):
        cagri = self._stub_borsa(monkeypatch)
        self._kos(monkeypatch)
        # Kural-4: hicbir cagri ev-dizinindeki DB_PATH'a gitmemeli
        for entry in cagri["list"]:
            db = entry[2]
            assert db == "/tmp/STUB-ASLA-YAZILMAZ", "gercek DB_PATH kullanildi!"

    def test_sinir_ajanlar_sabit_liste(self, monkeypatch):
        import seed
        assert len(seed.AGENTS) == 3
        for a in seed.AGENTS:
            assert set(a) == {"agent_id", "name", "service",
                              "price_target", "proof"}
            assert a["proof"].startswith(("commit:", "GERÇEK"))
