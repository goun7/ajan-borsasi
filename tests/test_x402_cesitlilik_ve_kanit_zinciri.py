"""Ajan Borsası — kalan EN KRİTİK test açıkları (sadece YENI dosya).

Kapsam (borsa_core'un eşleştirme motoru zaten tam testli; bu dosya
x402 servisinin test-dışı kalan katmanını + kanıt-zinciri kalıcılığını
kapatır):

  1. x402_servis.cesitlilik — ajan oy-çeşitliliği JSD analizi
     (arXiv:2609.29701); 82 satırlık saf-hesap mantığı tam test-dışıydı.
  2. x402_servis.teklif_ver — alıcı emri (orderbook) gönderme katmanı:
     doğrulama, üretim, replay koruması, orderbook'a yansıma.
  3. kanit_cekirdegi.KanitZinciri.yukle/kaydet — settlement kanıt-zinciri
     kalıcılığı + fail-closed bütünlük denetimi.

KURALLAR: mevcut testleri/kodu DEĞİŞTİRMEZ; her test kendi tmp_path
üzerinde izole SQLite/JSON kullanır; gerçek üretim DB'sine veya zincire
ASLA dokunmaz. Ödeme kapısı test-modunda (UNPUMP_TEST=1) simüle edilir.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# sester kardes proje; sanal ortamda kurulu degilse bu dosya atlanir
# (test_x402_servis.py ile ayni koruma kalibi).
# CI-2026-10-22: eth_account da ayni kaliba alindi. Oncesi-tasarimda bu
# dosyanin 17 testi _odeme()'nin gomulu import'unda patliyordu (requirements'
# de olmayinca) -> importorskip'i gecersiz kilan gizli-bagimlilik. Sistemde
# kurulu degilse dosyanin TAMAMI atlanir, yarim-kalmaz.
pytest.importorskip("eth_account")
pytest.importorskip(
    "sester",
    reason="sester kardes projesi sanal ortamda kurulu; "
           "tam kosu: UNPUMP_TEST=1 .venv/bin/python -m pytest tests/ -q",
)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

# =====================================================================
# fixtures
# =====================================================================

_TEST_SECRET = "test-only-secret-32bytes-min-len"


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    """İzole geçici DB + ledger ile TestClient (üretim dosyalarına dokunmaz)."""
    import os

    import x402_servis

    os.environ["BORSA_SELLER_SECRET"] = _TEST_SECRET
    os.environ["UNPUMP_TREASURY_EOA"] = "0x" + "ab" * 20
    os.environ["UNPUMP_TEST"] = "1"
    db = str(tmp_path / "borsa.sqlite")
    ldb = str(tmp_path / "receipts.sqlite")
    new_ledger = x402_servis.Ledger(ldb, secret=_TEST_SECRET)
    x402_servis.DB_PATH = db
    x402_servis.LEDGER_PATH = ldb
    x402_servis.ledger = new_ledger
    x402_servis.app.middleware_stack = None
    x402_servis.app.user_middleware[-1].kwargs["ledger"] = new_ledger
    return TestClient(x402_servis.app)


def _odeme(client: TestClient, resource: str, nonce: str,
           amount: str = "0.01") -> dict:
    """Geçerli Sester ödeme başlığı (exact-sester imzası).

    /cesitlilik ücretli bir uçtur; burada imza üreterek ödeme-akışını
    test ederiz — dış zincir aramadan (UNPUMP_TEST=1).
    """
    from eth_account import Account
    from sester.schemes import sign_exact_sester

    sk = "0x" + "11" * 32
    agent = Account.from_key(sk).address.lower()
    return {"X-Payment": sign_exact_sester(sk, agent, nonce, amount, resource)}


# =====================================================================
# 1) cesitlilik — JSD çeşitlilik analizi (arXiv:2609.29701)
# =====================================================================

def test_cesitlilik_odemesiz_402(client: TestClient) -> None:
    """Ücretli uç: ödemesiz çağrı reddedilir (fail-closed)."""
    r = client.post("/cesitlilik", json={"ajan_dagilimlari": [[1, 0], [0, 1]]})
    assert r.status_code == 402
    accepts = {a["scheme"] for a in r.json().get("accepts", [])}
    assert "exact-sester" in accepts


def test_cesitlilik_ayni_dagilim_sycophantic_convergence(client: TestClient) -> None:
    """Tam aynı dağılımlar → JSD 0 → SYCOPHANTIC-CONVERGENCY (başarı-dışı mod)."""
    r = client.post(
        "/cesitlilik", json={"ajan_dagilimlari": [[1, 0], [1, 0]]},
        headers=_odeme(client, "/cesitlilik", "cv-1"))
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d["ajan_sayisi"] == 2
    assert d["tercih_sayisi"] == 2
    assert d["ortalama_jsd"] == 0.0
    assert d["min_jsd"] == 0.0
    assert d["max_jsd"] == 0.0
    assert d["karar"] == "SYCOPHANTIC-CONVERGENCE"
    assert "arXiv:2609.29701" in d["kaynak"]


def test_cesitlilik_duzgun_ayni_dagilim_jsd_sifir(client: TestClient) -> None:
    """[0.5,0.5] iki kez → normalize edilse de JSD yine 0."""
    r = client.post(
        "/cesitlilik", json={"ajan_dagilimlari": [[0.5, 0.5], [0.5, 0.5]]},
        headers=_odeme(client, "/cesitlilik", "cv-2"))
    assert r.status_code == 200
    assert r.json()["ortalama_jsd"] == 0.0
    assert r.json()["karar"] == "SYCOPHANTIC-CONVERGENCE"


def test_cesitlilik_tam_zit_dagilim_jsd_bir(client: TestClient) -> None:
    """[1,0] vs [0,1] → maksimum JSD = 1.0 (log2 tabanlı tam ayrışma)."""
    r = client.post(
        "/cesitlilik", json={"ajan_dagilimlari": [[1, 0], [0, 1]]},
        headers=_odeme(client, "/cesitlilik", "cv-3"))
    assert r.status_code == 200
    d = r.json()
    assert d["ortalama_jsd"] == pytest.approx(1.0)
    assert d["max_jsd"] == pytest.approx(1.0)
    assert d["karar"] == "SAGLIKLI-CECESITLILIK"


def test_cesitlilik_dusuk_cesitlilik_esigi(client: TestClient) -> None:
    """0.02 ≤ JSD < 0.10 → DUSUK-CECESITLILIK (ajanlar birbirine benziyor)."""
    r = client.post(
        "/cesitlilik", json={"ajan_dagilimlari": [[1, 0], [0.95, 0.05]]},
        headers=_odeme(client, "/cesitlilik", "cv-4"))
    assert r.status_code == 200
    d = r.json()
    # [1,0] vs [0.95,0.05] JSD ≈ 0.0254624
    assert d["ortalama_jsd"] == pytest.approx(0.025462, abs=1e-5)
    assert d["karar"] == "DUSUK-CECESITLILIK"


def test_cesitlilik_esik_siniri_02_alti_sycophantic(client: TestClient) -> None:
    """JSD tam 0.02 eşiğinin altı → hâlâ SYCOPHANTIC (eşik < 0.02)."""
    r = client.post(
        "/cesitlilik", json={"ajan_dagilimlari": [[1, 0], [0.98, 0.02]]},
        headers=_odeme(client, "/cesitlilik", "cv-5"))
    assert r.status_code == 200
    d = r.json()
    assert d["ortalama_jsd"] < 0.02
    assert d["karar"] == "SYCOPHANTIC-CONVERGENCE"


def test_cesitlilik_uc_ajan_istatistikler(client: TestClient) -> None:
    """3 ajan: ortalama/min/max ikili JSD'lerden hesaplanır."""
    # çiftler: (0,1)=1.0, (0,2)≈0.0254624, (1,2)≈0.8549974
    r = client.post(
        "/cesitlilik",
        json={"ajan_dagilimlari": [[1, 0], [0, 1], [0.95, 0.05]]},
        headers=_odeme(client, "/cesitlilik", "cv-6"))
    assert r.status_code == 200
    d = r.json()
    assert d["ajan_sayisi"] == 3
    assert d["tercih_sayisi"] == 2
    assert d["min_jsd"] == pytest.approx(0.025462, abs=1e-5)
    assert d["max_jsd"] == pytest.approx(1.0)
    # (1.0 + 0.0254624 + 0.8549974) / 3 ≈ 0.62682
    assert d["ortalama_jsd"] == pytest.approx(0.62682, abs=1e-4)
    assert d["karar"] == "SAGLIKLI-CECESITLILIK"


def test_cesitlilik_normalize_edilmemis_dagilim(client: TestClient) -> None:
    """Olasılık vektörü 1'e normalize edilir: [2,0]/[0,2] → JSD 1.0."""
    r = client.post(
        "/cesitlilik", json={"ajan_dagilimlari": [[2, 0], [0, 2]]},
        headers=_odeme(client, "/cesitlilik", "cv-7"))
    assert r.status_code == 200
    assert r.json()["ortalama_jsd"] == pytest.approx(1.0)


def test_cesitlilik_sifir_toplu_dagilim_jsd_bir(client: TestClient) -> None:
    """Toplamı 0 olan dağılım → belirsiz → fail-safe JSD 1.0."""
    r = client.post(
        "/cesitlilik", json={"ajan_dagilimlari": [[0, 0], [1, 0]]},
        headers=_odeme(client, "/cesitlilik", "cv-8"))
    assert r.status_code == 200
    assert r.json()["ortalama_jsd"] == pytest.approx(1.0)


def test_cesitlilik_ikiden_ikiden_fazla_tercih_destegi(client: TestClient) -> None:
    """3 tercihli dağılımlar da çalışır; JSD [0,1] aralığında kalır."""
    r = client.post(
        "/cesitlilik",
        json={"ajan_dagilimlari": [[1, 0, 0], [0, 0, 1]]},
        headers=_odeme(client, "/cesitlilik", "cv-9"))
    assert r.status_code == 200
    d = r.json()
    assert d["tercih_sayisi"] == 3
    assert 0.0 <= d["ortalama_jsd"] <= 1.0


def test_cesitlilik_ledger_seq_ve_zincir_gecerli(client: TestClient) -> None:
    """Ücretli çağrı makbuzu ledger'a yazar; zincir geçerli kalır."""
    r = client.post(
        "/cesitlilik", json={"ajan_dagilimlari": [[1, 0], [0, 1]]},
        headers=_odeme(client, "/cesitlilik", "cv-10"))
    assert r.status_code == 200
    d = r.json()
    assert d["ledger_seq"] >= 0
    assert d["receipt_chain_valid"] is True
    assert d["paid"] > 0


@pytest.mark.parametrize("daglar, beklenen", [
    ([[1, 0]], "en az 2 ajan gerekli"),
    ([[1, 0]] * 51, "en fazla 50 ajan"),
    ([[1], [0]], "en az 2 tercih"),
    ([[1, 0], [1, 0, 0]], "tüm dağılımlar aynı boyutta olmalı"),
    ([[1, 0], [-1, 1]], "negatif olasılık"),
])
def test_cesitlilik_giris_dogrulamasi_400(client: TestClient, daglar, beklenen) -> None:
    """Giriş doğrulama: <2 ajan, >50 ajan, <2 tercih, uyumsuz boyut, negatif."""
    r = client.post(
        "/cesitlilik", json={"ajan_dagilimlari": daglar},
        headers=_odeme(client, "/cesitlilik", "cv-val"))
    assert r.status_code == 400
    assert r.json()["detail"] == beklenen


def test_cesitlilik_50_ajan_siniri_tam_sinirda_gecer(client: TestClient) -> None:
    """Tam 50 ajan sınırı kabul edilir (sınır değeri dahil)."""
    r = client.post(
        "/cesitlilik", json={"ajan_dagilimlari": [[1, 0]] * 50},
        headers=_odeme(client, "/cesitlilik", "cv-50"))
    assert r.status_code == 200
    assert r.json()["ajan_sayisi"] == 50


# =====================================================================
# 2) teklif_ver — alıcı emri (orderbook) gönderme katmanı
# =====================================================================

def test_teklif_ver_sifir_ve_negatif_tutar_422(client: TestClient) -> None:
    """BidGirdisi.amount > 0 — pydantic katmanı 0/negatifi 422 ile reddeder."""
    r = client.post("/teklif-ver", json={
        "agent_id": "0xT1", "amount": 0.0, "work_spec": "{}", "nonce": "z1"})
    assert r.status_code == 422
    r = client.post("/teklif-ver", json={
        "agent_id": "0xT1", "amount": -1.0, "work_spec": "{}", "nonce": "z2"})
    assert r.status_code == 422


def test_teklif_ver_eksik_alan_422(client: TestClient) -> None:
    """Zorunlu alan eksikse pydantic 422 verir (amount yok)."""
    r = client.post("/teklif-ver", json={
        "agent_id": "0xT1", "work_spec": "{}", "nonce": "z3"})
    assert r.status_code == 422
    assert any(err["loc"] == ["body", "amount"] for err in r.json()["detail"])


def test_teklif_ver_basariyla_pending_emir_uretir(client: TestClient) -> None:
    """Geçerli emir → pending bid kaydı döner ve orderbook'a (pazar) yansır."""
    client.post("/listele", json={
        "agent_id": "0xT2", "name": "TestAjan", "service": "randevu",
        "price_target": 1.0, "proof_hash": "sha256:pt"})
    r = client.post("/teklif-ver", json={
        "agent_id": "0xT2", "amount": 1.0,
        "work_spec": '{"is": "randevu"}', "nonce": "tk-1"})
    assert r.status_code == 200, r.text[:300]
    b = r.json()
    assert b["agent_id"] == "0xT2"
    assert b["amount"] == 1.0
    assert b["status"] == "pending"
    assert b["nonce"] == "tk-1"
    assert b["bid_id"]

    # orderbook özetinde pending olarak görünmeli
    pazar = client.get("/pazar").json()
    assert pazar["bids"].get("pending") == 1


def test_teklif_ver_nonce_replay_400(client: TestClient) -> None:
    """Aynı nonce ikinci gönderimde reddedilir (DB UNIQUE replay koruması)."""
    client.post("/listele", json={
        "agent_id": "0xT3", "name": "TestAjan3", "service": "repricing",
        "price_target": 0.5, "proof_hash": "sha256:pt3"})
    payload = {"agent_id": "0xT3", "amount": 0.5, "work_spec": "{}",
               "nonce": "replay-1"}
    ilk = client.post("/teklif-ver", json=payload)
    assert ilk.status_code == 200
    tekrar = client.post("/teklif-ver", json=payload)
    assert tekrar.status_code == 400
    assert "nonce" in tekrar.json()["detail"]


def test_teklif_ver_bilinmeyen_ajana_emir_gecerli(client: TestClient) -> None:
    """Teklif gönderimi listeleme gerektirmez (giriş engeli yok);

    eşleştirme sırasında ajan yoksa reddedilir (o ayrı uçtur).
    """
    r = client.post("/teklif-ver", json={
        "agent_id": "0xBILINMEYEN", "amount": 2.0,
        "work_spec": "{}", "nonce": "tk-yeni"})
    assert r.status_code == 200
    assert r.json()["status"] == "pending"
    # ama eşleşme olmaz (ajan listede değil)
    esles = client.post(f"/eslestir/{r.json()['bid_id']}")
    assert esles.status_code == 404


# =====================================================================
# 3) KanitZinciri.yukle/kaydet — settlement kanıt-zinciri kalıcılığı
# =====================================================================

def _islem(agent: str = "0xA1", op: str = "tamamla", amount: float = 5.0):
    from kanit_cekirdegi import AjanIslem, utc_now_iso

    return AjanIslem(agent, op, amount, None, utc_now_iso(), "test-kaynak")


def test_kanit_zinciri_kaydet_yukle_roundtrip(tmp_path: Path) -> None:
    """kaydet → yukle round-trip: series + chain ve hash'ler korunur."""
    from kanit_cekirdegi import KanitZinciri

    yol = str(tmp_path / "kanit.json")
    z = KanitZinciri(yol)
    sonuc = z.ekle(_islem())
    assert sonuc["ok"] is True
    z.kaydet()

    # yeniden yükle (kurucu dosyayı otomatik yükler + doğrular)
    z2 = KanitZinciri(yol)
    assert list(z2.series.keys()) == list(z.series.keys())
    assert len(z2.chain) == 1
    assert z2.chain[0].h == z.chain[0].h
    assert z2.chain[0].prev == z.chain[0].prev
    assert z2.dogrula()["ok"] is True


def test_kanit_zinciri_kaydet_dosya_yolu_yoksa_hata(tmp_path: Path) -> None:
    """dosya_yolu verilmeden kaydet → ValueError (fail-closed)."""
    from kanit_cekirdegi import KanitZinciri

    with pytest.raises(ValueError, match="dosya_yolu yok"):
        KanitZinciri().kaydet()


def test_kanit_zinciri_kaydet_ust_dizin_olusturur(tmp_path: Path) -> None:
    """Olmayan üst dizine kaydet → dizin otomatik oluşturulur, hata yok."""
    from kanit_cekirdegi import KanitZinciri

    yol = str(tmp_path / "a" / "b" / "kanit.json")
    z = KanitZinciri()
    z.dosya_yolu = yol
    z.ekle(_islem("0xK1", "listele", 1.0))
    z.kaydet()
    assert Path(yol).exists()


def test_kanit_zinciri_yukle_kirik_prev_baglantisi(tmp_path: Path) -> None:
    """prev bağı kırık store → ValueError (fail-closed, yüklenmez)."""
    import json

    from kanit_cekirdegi import KanitZinciri

    yol = tmp_path / "kirik.json"
    z = KanitZinciri(str(yol))
    z.ekle(_islem("0xK2", "teklif", 2.0))
    z.kaydet()
    veri = json.loads(yol.read_text(encoding="utf-8"))
    veri["chain"][0]["prev"] = "sha256:deadbeef"
    yol.write_text(json.dumps(veri), encoding="utf-8")

    with pytest.raises(ValueError, match="store bozuk"):
        KanitZinciri(str(yol))


def test_kanit_zinciri_yukle_kurcalanmis_icerik_hashi(tmp_path: Path) -> None:
    """İçerik-hash'i uyduruksa → 'kurcalama' hatası (bağımsız denetim)."""
    import json

    from kanit_cekirdegi import KanitZinciri

    yol = tmp_path / "kurcalanmis.json"
    z = KanitZinciri(str(yol))
    z.ekle(_islem("0xK3", "eslestir", 3.0))
    z.kaydet()
    veri = json.loads(yol.read_text(encoding="utf-8"))
    veri["chain"][0]["h"] = "sha256:wrongwrongwrong"
    yol.write_text(json.dumps(veri), encoding="utf-8")

    with pytest.raises(ValueError, match="store bozuk"):
        KanitZinciri(str(yol))


def test_kanit_zinciri_yukle_series_kaydi_yok(tmp_path: Path) -> None:
    """chain'de kayıt var ama series'te karşılığı yoksa → ValueError."""
    import json

    from kanit_cekirdegi import KanitZinciri, ZincirKaydi

    z = KanitZinciri()
    z.chain = [ZincirKaydi(id="ghost|op|2026-01-01", h="sha256:abc",
                           prev="GENESIS")]
    yol = tmp_path / "hayalet.json"
    z.dosya_yolu = str(yol)
    z.kaydet()

    with pytest.raises(ValueError, match="store bozuk"):
        KanitZinciri(str(yol))


def test_kanit_zinciri_bos_store_dogrulama(tmp_path: Path) -> None:
    """Boş zincir geçerlidir (uzunluk 0, son None)."""
    from kanit_cekirdegi import KanitZinciri

    z = KanitZinciri()
    z.dosya_yolu = str(tmp_path / "bos.json")
    z.kaydet()
    z2 = KanitZinciri(str(tmp_path / "bos.json"))
    assert z2.to_dict() == {"series": {}, "chain": []}
    d = z2.dogrula()
    assert d["ok"] is True
    assert d["uzunluk"] == 0
    assert d["son"] is None


def test_kanit_zinciri_kalıcılık_iki_islem_zinciri(tmp_path: Path) -> None:
    """İki işlemli zincir diskten yüklenince prev-bağı korunur."""
    from kanit_cekirdegi import KanitZinciri

    yol = str(tmp_path / "iki.json")
    z = KanitZinciri(yol)
    z.ekle(_islem("0xK4", "listele", 1.0), kaydet=False)
    z.ekle(_islem("0xK4", "tamamla", 9.0), kaydet=False)
    z.kaydet()

    z2 = KanitZinciri(yol)
    assert len(z2.chain) == 2
    # ikinci kaydın prev'i birincinin hash'i
    assert z2.chain[1].prev == z2.chain[0].h
    assert z2.dogrula()["ok"] is True
