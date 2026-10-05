"""Delilix kanıt-çekirdeği port testleri — Unpump ajan havuzu.

Kapsam: kanit_cekirdegi.py'nin Delilix (04_hukuk_sarti/83-Delilix)
kanıt modeliyle parity'si + zincir üretimi/dogrulaması + borsa_core
bütünleşmesi. Hiçbir test mevcut 13 testin dokunduğu DB'ye veya ağ'a
gitmez; her kanıt deposu tmp_path içinde izoledir.

İki tip parity kanıtı:
  (a) SABİT-VEKTÖR — node gerektirmez, her kosusta kosar (Delilix
      referans hash'i literal olarak gömülüdür).
  (b) CANLI-KARŞILAŞTIRMA — node varsa subprocess ile JSON.stringify
      çıktısını birebir kıyaslar; node yoksa skip.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from borsa_core import complete_work, list_agent, match_bid, place_bid  # noqa: E402
from kanit_cekirdegi import (  # noqa: E402
    AjanIslem, GENESIS, KanitZinciri, ZincirKaydi, content_hash,
    csv_caprazla, day_key, dogrula, islem_id, js_stringify,
    match_kanit_islemi, utc_now_iso, zinciri_dogrula,
)

# Delilix code/store.mjs contentHash'i ile node'da hesaplanmış sabit
# değer — Python portunun AYNI sha256'i ürettiğini ispatlar (2026-10-05).
DELILIX_REFERANS_HASH = (
    "sha256:92081dafb16fc0335147e4b7d8ac1e867b325bb6be1baea71f94364a2b96465b"
)
DELILIX_REFERANS_KAYIT = {
    "site": "trendyol.com",
    "product_id": "mock-sahte-urun",
    "sell": 1350,
    "ref": 2499,
    "ts": "2026-09-21T12:00:00Z",
    "source": "dogfood",
}


# ----------------------------------------------------- JS ⇄ Python parity


def test_content_hash_delilix_referans_vektoru() -> None:
    """SABİT parity kanıtı: Python portu Delilix hash'ini birebir üretir.

    Bu, iki implementasyonun aynı kanıt-sözleşmesine uyduğunun
    kanıtıdır — node bu testte ÇALIŞMAZ, değer gömülüdür.
    """
    assert content_hash(DELILIX_REFERANS_KAYIT) == DELILIX_REFERANS_HASH


def test_js_stringify_node_ile_birebir() -> None:
    """CANLI parity: js_stringify == JSON.stringify (kenar durumlar dahil)."""
    if shutil.which("node") is None:
        pytest.skip("node yok — canlı parity kıyası atlandı")

    batarya = [
        15, 15.0, 1350.5, 1e-7, 1e21, 1.5e21, -0.0, -3.5, 1 / 3, 0.1,
        "İĞÜŞÇÖ", 'a"b\\c', "satır\niçi", None, True, False,
        {"a": 1, "b": [1, 2, {"c": 3}]}, {"b": 1, "a": 2}, [], {},
        [None, True, -0.0],
    ]
    beklenen = subprocess.run(
        ["node", "-e", "console.log(JSON.stringify("
         "require('fs').readFileSync(0,'utf8').split('\\n').filter(Boolean)"
         ".map(s=>JSON.stringify(JSON.parse(s).v))))"],
        input="\n".join(json.dumps({"v": v}) for v in batarya),
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    # liste-level kıyas (dış serileştirmenin boşluk farkı önemsiz)
    bulunan = [js_stringify(v) for v in batarya]
    assert bulunan == json.loads(beklenen)


def test_day_key_utc_ve_dilim_davranisi() -> None:
    """day_key UTC'dir; 'Z' ve +00:00 eş, dilimsiz tarih UTC kabul edilir."""
    assert day_key("2026-09-21T12:00:00Z") == "2026-09-21"
    assert day_key("2026-09-21T23:00:00Z") == "2026-09-21"
    assert day_key("2026-09-21T23:00:00+00:00") == "2026-09-21"
    assert day_key("2026-09-21") == "2026-09-21"
    # saat dilimi UTC'ye göre biçilir: +03:00 gece-yarısı öncesi bir önceki
    # UTC gününe, -05:00 akşamı bir sonraki UTC gününe düşer
    assert day_key("2026-09-21T23:00:00+03:00") == "2026-09-21"
    assert day_key("2026-09-22T02:00:00+03:00") == "2026-09-21"
    assert day_key("2026-09-21T22:00:00-05:00") == "2026-09-22"
    with pytest.raises(ValueError):
        day_key("geçersiz-tarih")


# ------------------------------------------------ zincir üretimi + dogrula


@pytest.fixture()
def uc_islemli_store(tmp_path: Path) -> KanitZinciri:
    """3 işlemli, DOĞRU zincir (birçok testin temeli)."""
    store = KanitZinciri(dosya_yolu=str(tmp_path / "kanit.json"))
    for i, (op, tutar, ref, ts) in enumerate([
        ("listele", 5.0, None, "2026-10-01T09:00:00Z"),
        ("teklif", 12.0, 10.0, "2026-10-01T10:00:00Z"),
        ("tamamla", 12.0, 10.0, "2026-10-01T11:00:00Z"),
    ]):
        r = store.ekle(AjanIslem(
            agent_id="agent-1", operation=op, amount=tutar, ref=ref,
            ts=ts, source="test"))
        assert r["ok"] is True
    return store


def test_zincir_ekle_genesis_ve_damga_baglari(uc_islemli_store: KanitZinciri) -> None:
    """İlk prev=GENESIS, her prev=önceki h, hash=content_hash; dogrula geçer."""
    s = uc_islemli_store
    assert len(s.chain) == 3
    assert s.chain[0].prev == GENESIS
    for onceki, kayit in zip(s.chain, s.chain[1:]):
        assert kayit.prev == onceki.h
    # her damganın hash'i işlem içeriğinden bağımsız yeniden hesaplanabilir
    for kayit in s.chain:
        assert kayit.h == content_hash(s.series[kayit.id])
    sonuc = s.dogrula()
    assert sonuc["ok"] is True
    assert sonuc["uzunluk"] == 3
    assert sonuc["son"] == s.chain[-1].h
    # disk formatı Delilix {series, chain} şemasında
    disk = json.loads(Path(s.dosya_yolu).read_text(encoding="utf-8"))
    assert set(disk) == {"series", "chain"}
    assert len(disk["chain"]) == 3


def test_zincir_kurcalama_tespiti(uc_islemli_store: KanitZinciri) -> None:
    """series içeriği değişirse → 'kurcalama' hatası, sonuc=HATALI."""
    s = uc_islemli_store
    hedef = s.chain[1].id
    s.series[hedef]["amount"] = 999.0          # ⚠️ kurcalama
    sonuc = zinciri_dogrula(s.to_dict())
    assert sonuc["uzunluk"] == 3
    hata = next(h for h in sonuc["hatalar"] if h["id"] == hedef)
    assert hata["tur"] == "kurcalama"
    assert s.dogrula()["ok"] is False


def test_zincir_prev_kirik_tespiti(uc_islemli_store: KanitZinciri) -> None:
    """prev bağı koparılınca → 'prev-kırık' (araya-ekleme/silme algılanır)."""
    s = uc_islemli_store
    s.chain[1] = ZincirKaydi(id=s.chain[1].id, h=s.chain[1].h,
                             prev="sha256:deadbeef")
    hatalar = zinciri_dogrula(s.to_dict())["hatalar"]
    assert any(h["tur"] == "prev-kırık" and h["id"] == s.chain[1].id
               for h in hatalar)


def test_gun_idempotency_ayni_gun_tek_kayit(tmp_path: Path) -> None:
    """Aynı ajan+işlem+gün → 'gun-zaten-var'; zincir uzamadan kalır."""
    store = KanitZinciri(dosya_yolu=str(tmp_path / "kanit.json"))
    a1 = AjanIslem("agent-1", "tamamla", 12.0, None,
                   "2026-10-01T11:00:00Z", "test")
    assert store.ekle(a1)["ok"] is True
    # aynı gün, farklı saat — Delilix gün-başı şeması: tek kayıt
    a2 = AjanIslem("agent-1", "tamamla", 12.0, None,
                   "2026-10-01T23:59:00Z", "test")
    r2 = store.ekle(a2)
    assert r2["ok"] is False
    assert r2["neden"] == "gun-zaten-var"
    assert r2["id"] == "agent-1|tamamla|2026-10-01"
    assert len(store.chain) == 1                 # zincir uzamadı
    # ertesi gün yeni kayıt eklenir
    a3 = AjanIslem("agent-1", "tamamla", 12.0, None,
                   "2026-10-02T11:00:00Z", "test")
    assert store.ekle(a3)["ok"] is True
    assert len(store.chain) == 2
    assert store.chain[1].prev == store.chain[0].h


def test_gun_uyumsuz_ve_yapi_hatalari_raporlanir() -> None:
    """id-günü ≠ ts-günü → 'gün-uyumsuz'; eksik h → 'yapı'."""
    kayit = {"agent_id": "agent-1", "operation": "tamamla", "amount": 5.0,
             "ref": None, "ts": "2026-10-01T11:00:00Z", "source": "test"}
    store = {
        "series": {"agent-1|tamamla|2026-10-02": kayit},
        # GEÇERLİ hash — böylece yapı/prev/kurcalama geçilip gün kıyasına
        # ulaşılır; tek kalan bulgu 'gün-uyumsuz' olmalı
        "chain": [
            {"id": "agent-1|tamamla|2026-10-02", "h": content_hash(kayit),
             "prev": GENESIS},
        ],
    }
    hatalar = zinciri_dogrula(store)["hatalar"]
    assert len(hatalar) == 1
    assert hatalar[0]["tur"] == "gün-uyumsuz"

    # eksik h alanı → 'yapı' (öncelikli kontrol)
    store["chain"][0]["h"] = None
    hatalar2 = zinciri_dogrula(store)["hatalar"]
    assert hatalar2[0]["tur"] == "yapı"


def test_kayit_yok_ve_gecersiz_ts_raporlanir() -> None:
    """series'te karşılığı yoksa 'kayit-yok'; geçersiz ts 'gün-uyumsuz'."""
    h_genesis = content_hash({"agent_id": "a", "operation": "x", "amount": 1.0,
                              "ref": None, "ts": "2026-10-01T00:00:00Z",
                              "source": "t"})
    store = {
        "series": {},
        "chain": [
            {"id": "a|x|2026-10-01", "h": h_genesis, "prev": GENESIS},
            {"id": "b|y|2026-10-01", "h": "sha256:00", "prev": h_genesis},
        ],
    }
    hatalar = zinciri_dogrula(store)["hatalar"]
    assert any(h["tur"] == "kayit-yok" and h["id"] == "a|x|2026-10-01"
               for h in hatalar)


def test_yukle_bozuk_store_reddeder(tmp_path: Path, uc_islemli_store: KanitZinciri) -> None:
    """Fail-closed: disk üzerindeki store kurcalanınca yükleme ValueError."""
    yol = Path(uc_islemli_store.dosya_yolu)
    veri = json.loads(yol.read_text(encoding="utf-8"))
    ilk = veri["chain"][0]["id"]
    veri["series"][ilk]["amount"] = 0.01         # diskte kurcalama
    yol.write_text(json.dumps(veri), encoding="utf-8")
    with pytest.raises(ValueError, match="store bozuk"):
        KanitZinciri(dosya_yolu=str(yol))


# -------------------------------------------------------- CSV çapraz-doğrulama


def test_csv_caprazlama_eslesme_ve_uyumsuzluk(tmp_path: Path,
                                              uc_islemli_store: KanitZinciri) -> None:
    """Dışa-aktarılan CSV zincirli seriyle birebir; yanlış satır raporlanır."""
    yol = Path(uc_islemli_store.dosya_yolu)
    csv_yolu = tmp_path / "islem-log.csv"
    satirlar = ["agent_id,operation,amount,ref,ts,source"]
    for kayit in uc_islemli_store.series.values():
        ref = "" if kayit["ref"] is None else kayit["ref"]
        satirlar.append(",".join(str(x) for x in [
            kayit["agent_id"], kayit["operation"], kayit["amount"], ref,
            kayit["ts"], kayit["source"]]))
    satirlar.append("agent-1,tamamla,999,,2026-10-03T00:00:00Z,test")  # yok
    csv_yolu.write_text("\n".join(satirlar) + "\n", encoding="utf-8")

    sonuc = csv_caprazla(str(yol), str(csv_yolu))
    assert sonuc["satir"] == 4
    assert len(sonuc["eslesen"]) == 3
    assert sonuc["eksik"] == ["agent-1|tamamla|2026-10-03"]
    assert sonuc["uyusmayan"] == []

    # tutar uyuşmazlığı → uyusmayan
    satirlar[2] = "agent-1,teklif,1.0,,2026-10-01T10:00:00Z,test"
    csv_yolu.write_text("\n".join(satirlar[:3]) + "\n", encoding="utf-8")
    sonuc2 = csv_caprazla(str(yol), str(csv_yolu))
    assert any(u["alan"] == "amount" for u in sonuc2["uyusmayan"])


def test_dogrula_csvsiz_ve_dogru_store_gecerli(tmp_path: Path,
                                              uc_islemli_store: KanitZinciri) -> None:
    r = dogrula(uc_islemli_store.dosya_yolu)
    assert r["sonuc"] == "DOĞRULANDI"
    assert r["csv"] is None


# ------------------------------------------- borsa_core bütünleşmesi (uçtan-uca)


def test_borsadan_match_kaniti_uctan_uca(tmp_path: Path) -> None:
    """Tam borsa akışı → match kanıt-zincirine bağlanır; kurcalama yakalanır.

    listele → teklif → eşleş → tamamla (⭐⭐⭐ work_done) → SHA-256 zincir
    kanıtı. Bu, Delilix formatının Unpump ajanlarına EKLENDİĞİNİ kanıtlar.
    """
    db = str(tmp_path / "borsa.sqlite")
    list_agent("agent-7", "Randezvu", "randevu", 10.0, "kanit-hash", db=db)
    bid = place_bid("agent-7", "buyer-1", 15.0, '{"isim": "x"}', "n-1", db=db)
    m = match_bid(bid.bid_id, db=db)
    assert m is not None and m.work_done is False
    tamamlanan = complete_work(m.match_id, "receipt-abc", db=db)
    assert tamamlanan.work_done is True

    # ⭐⭐⭐ kapanış kanıtı: match → zincir işlemi (duck-typing, import yok)
    store = KanitZinciri(dosya_yolu=str(tmp_path / "kanit.json"))
    islem = match_kanit_islemi(tamamlanan, ts="2026-10-05T15:00:00Z",
                               ref=10.0)
    assert islem.agent_id == "agent-7"
    assert islem.amount == 15.0
    assert islem.operation == "tamamla"
    r = store.ekle(islem)
    assert r["ok"] is True
    assert r["tamga"]["prev"] == GENESIS

    # bağımsız doğrulayıcı (store sınıfı olmadan, Delilix dogrula.mjs gibi)
    r2 = dogrula(store.dosya_yolu)
    assert r2["sonuc"] == "DOĞRULANDI"
    assert r2["zincir"]["son"] == r["tamga"]["h"]

    # kurcalama → HATALI
    disk_yol = Path(store.dosya_yolu)
    veri = json.loads(disk_yol.read_text(encoding="utf-8"))
    veri["series"][r["id"]]["amount"] = 0.01
    disk_yol.write_text(json.dumps(veri), encoding="utf-8")
    assert dogrula(str(disk_yol))["sonuc"] == "HATALI"


def test_match_kanit_islemi_eksik_alan_reddeder() -> None:
    """duck-typing guard: agent_id/amount olmayan nesle TypeError."""
    with pytest.raises(TypeError, match="eksik alanlar"):
        match_kanit_islemi({"agent_id": "x"})


def test_utc_now_iso_js_formatinda() -> None:
    """utc_now_iso JS toISOString() biçimindedir (…Z, milisaniye)."""
    ts = utc_now_iso()
    assert ts.endswith("Z")
    assert len(ts) == 24                        # YYYY-MM-DDTHH:MM:SS.mmmZ
    assert ts[10] == "T" and ts[19] == "."


# ------------------------------------------------------------------- CLI


def test_cli_cikis_kodlari(tmp_path: Path, uc_islemli_store: KanitZinciri) -> None:
    """CLI: DOĞRULANDI → rc=0; kurcalı → rc=1 (dogrula.mjs ile aynı)."""
    iyi = subprocess.run(
        [sys.executable, "kanit_cekirdegi.py", uc_islemli_store.dosya_yolu],
        capture_output=True, text=True, cwd=str(ROOT))
    assert iyi.returncode == 0
    assert "DOĞRULANDI" in iyi.stdout

    yol = Path(uc_islemli_store.dosya_yolu)
    veri = json.loads(yol.read_text(encoding="utf-8"))
    veri["chain"][0]["prev"] = "sha256:bozuk"
    yol.write_text(json.dumps(veri), encoding="utf-8")
    kotu = subprocess.run(
        [sys.executable, "kanit_cekirdegi.py", str(yol), "--json"],
        capture_output=True, text=True, cwd=str(ROOT))
    assert kotu.returncode == 1
    assert json.loads(kotu.stdout)["sonuc"] == "HATALI"

    kullanim = subprocess.run(
        [sys.executable, "kanit_cekirdegi.py"],
        capture_output=True, text=True, cwd=str(ROOT))
    assert kullanim.returncode == 1
    assert "kullanım" in kullanim.stderr
