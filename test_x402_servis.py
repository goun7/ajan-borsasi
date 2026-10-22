"""Ajan Borsası x402 servisi — uçtan-uca ödeme testleri (dogfood kalıbı)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# CI-2026-10-22: `eth_account` ve `sester` kardes-paketleri dogal ortamda
# kurulu olabilir ama CI'da degil. Oncesi-tasarimda `eth_account` import'u
# buradan ONCE yapiliyordu -> importorskip asla ulasilamayan bir kuskor
# oluyordu ( gizli-skip-deseni: korumasi gereken import'u kendisi patlatiyor).
# Duzeltme: butun kardes-paket importlari importorskip'lerin SONRASINA.
pytest.importorskip("eth_account")
pytest.importorskip(
    "sester",
    reason="sester kardes projesi sanal ortamda kurulu; "
           "tam kosu: UNPUMP_TEST=1 .venv/bin/python -m pytest tests/ test_x402_servis.py -q",
)

from eth_account import Account  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def _evm_header(resource: str, nonce: str, amount: str = "0.01",
                key_hex: str = "11") -> str:
    from sester.schemes import sign_exact_sester

    sk = "0x" + key_hex * 32
    agent = Account.from_key(sk).address.lower()
    return sign_exact_sester(sk, agent, nonce, amount, resource)


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    import x402_servis

    db = tmp_path / "borsa.sqlite"
    ldb = tmp_path / "receipts.sqlite"
    # AT-193: sester 0.7.x Ledger icin secret ZORUNLU kilar —
    # tests-only sabit secret (gercek uretim secret'i DEGIL).
    import os
    os.environ["BORSA_SELLER_SECRET"] = "test-only-secret-32bytes-min-len"
    os.environ["UNPUMP_TREASURY_EOA"] = "0x" + "ab" * 20
    new_ledger = x402_servis.Ledger(str(ldb), secret=os.environ["BORSA_SELLER_SECRET"])
    x402_servis.DB_PATH = str(db)
    x402_servis.LEDGER_PATH = str(ldb)
    x402_servis.ledger = new_ledger
    x402_servis.app.middleware_stack = None
    x402_servis.app.user_middleware[-1].kwargs["ledger"] = new_ledger
    return TestClient(x402_servis.app)


def test_kanitsiz_listeleme_400(client: TestClient) -> None:
    """Fail-closed: proof_hash olmadan ajan listelenemez."""
    r = client.post("/listele", json={
        "agent_id": "0xA1", "name": "Test", "service": "x",
        "price_target": 1.0, "proof_hash": ""})
    assert r.status_code == 400


def test_odemesiz_tamamla_402(client: TestClient) -> None:
    """Tamamlama ödemeli — kanıt ücretsiz üretilmez."""
    r = client.post("/tamamla", json={"match_id": "yok", "receipt_hash": "x"})
    assert r.status_code == 402
    accepts = {a["scheme"] for a in r.json().get("accepts", [])}
    assert "exact-sester" in accepts


def test_tam_akis_listele_teklif_eslestir_tamamla(client: TestClient) -> None:
    # 1) listele (ücretsiz — kanıt anahtardır)
    r = client.post("/listele", json={
        "agent_id": "0xAGENT1", "name": "VadeDostu", "service": "tahsilat",
        "price_target": 0.50, "proof_hash": "sha256:proof1"})
    assert r.status_code == 200, r.text[:300]

    # 2) teklif ücretsiz (giriş engeli yok)
    r1 = client.post("/teklif-ver", json={
        "agent_id": "0xAGENT1", "amount": 0.50,
        "work_spec": '{"is":"hatirlatma"}', "nonce": "t1"})
    assert r1.status_code == 200, r1.text[:300]
    bid_id = r1.json()["bid_id"]

    # 4) eşleştir
    r2 = client.post(f"/eslestir/{bid_id}")
    assert r2.status_code == 200
    assert r2.json()["work_done"] is False
    match_id = r2.json()["match_id"]

    # 5) ⭐⭐⭐ kanıtsız tamamlama → 400 (ödeme ile gelir, ama kanıt boş)
    r3 = client.post("/tamamla",
                     json={"match_id": match_id, "receipt_hash": ""},
                     headers={"X-Payment": _evm_header("/tamamla", "c0")})
    assert r3.status_code == 400, f"kanıtsız tamamlama kabul edildi: {r3.text}"

    # 6) kanırlı tamamlama
    r4 = client.post("/tamamla", json={"match_id": match_id,
                                       "receipt_hash": "sha256:receipt1"},
                     headers={"X-Payment": _evm_header("/tamamla", "c1")})
    assert r4.status_code == 200, r4.text[:300]
    d = r4.json()
    assert d["work_done"] is True
    assert d["receipt_hash"] == "sha256:receipt1"
    assert d["ledger_seq"] >= 0


def test_dusuk_teklif_eslesmez(client: TestClient) -> None:
    client.post("/listele", json={
        "agent_id": "0xA2", "name": "RepriceAI", "service": "repricing",
        "price_target": 0.25, "proof_hash": "sha256:p2"})
    r = client.post("/teklif-ver", json={
        "agent_id": "0xA2", "amount": 0.10, "work_spec": "{}", "nonce": "d1"})
    bid_id = r.json()["bid_id"]
    r2 = client.post(f"/eslestir/{bid_id}")
    assert r2.status_code == 404  # fiyat-hedefinin altı


def test_nonce_replay_reddedilir(client: TestClient) -> None:
    pay = _evm_header("/teklif-ver", "r1")
    client.post("/listele", json={
        "agent_id": "0xA3", "name": "CallSnap", "service": "randevu",
        "price_target": 0.05, "proof_hash": "sha256:p3"})
    client.post("/teklif-ver", json={
        "agent_id": "0xA3", "amount": 0.05, "work_spec": "{}", "nonce": "r1"},
        headers={"X-Payment": pay})
    # nonce DB'de UNIQUE → 400 (DB replay koruması, ödeme bağımsız)
    client.post("/teklif-ver", json={
        "agent_id": "0xA3", "amount": 0.05, "work_spec": "{}", "nonce": "r1"})
    r2 = client.post("/teklif-ver", json={
        "agent_id": "0xA3", "amount": 0.05, "work_spec": "{}", "nonce": "r1"})
    assert r2.status_code == 400


def test_pazar_ve_healthz_ucretsiz(client: TestClient) -> None:
    h = client.get("/healthz")
    assert h.status_code == 200
    assert h.json()["status"] == "ok"

    p = client.get("/pazar")
    assert p.status_code == 200
    assert "listed_agents" in p.json()


def test_ledger_chain_dogru(client: TestClient) -> None:
    import x402_servis

    client.post("/listele", json={
        "agent_id": "0xA4", "name": "X", "service": "y",
        "price_target": 0.05, "proof_hash": "sha256:p4"})
    r = client.post("/teklif-ver", json={
        "agent_id": "0xA4", "amount": 0.05, "work_spec": "{}", "nonce": "l1"})
    bid_id = r.json()["bid_id"]
    m = client.post(f"/eslestir/{bid_id}").json()
    client.post("/tamamla", json={"match_id": m["match_id"],
                                  "receipt_hash": "sha256:r"},
                headers={"X-Payment": _evm_header("/tamamla", "l2")})
    assert x402_servis.ledger.verify_chain() is True
