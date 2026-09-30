"""Ajan Borsası çekirdek testleri — saf iş mantığı, izole SQLite.

Kapsam: borsa_core.py'nin doğrulama + eşleştirme + kanıt-bağlı tamamlama
kuralları. Hiçbir test ağ, cüzdan, PRIVATE_KEY veya gerçek DB_PATH'e
dokunmaz — her test kendi geçici SQLite dosyasını (tmp_path) enjekte eder.
Anahtar olmayan modüller (mainnet_guard/mainnet_verify) bilinçli olarak
test dışıdır.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from borsa_core import (  # noqa: E402
    AgentListing, Bid, Match, complete_work, list_agent, match_bid,
    market_summary, place_bid,
)


@pytest.fixture()
def db(tmp_path: Path) -> str:
    """Her teste özel, yok-olduktan sonra silinen izole veritabanı."""
    return str(tmp_path / "borsa.sqlite")


# ------------------------------------------------------ list_agent doğrulama


def test_list_agent_eksik_alan_ve_sifir_fiyat_reddedilir(db: str) -> None:
    """proof_hash dahil tüm alanlar zorunlu; price_target > 0."""
    with pytest.raises(ValueError, match="eksik alan"):
        list_agent("agent-1", "isim", "servis", 10.0, "", db=db)
    with pytest.raises(ValueError, match="price_target > 0"):
        list_agent("agent-1", "isim", "servis", 0.0, "kanit-hash", db=db)


def test_list_agent_basariyla_listeler(db: str) -> None:
    listing = list_agent("agent-1", "Randezvu", "randevu", 5.0, "kanit-hash",
                         db=db)
    assert isinstance(listing, AgentListing)
    assert listing.status == "listed"
    assert listing.price_target == 5.0
    assert listing.proof_hash == "kanit-hash"
    # tekrar listeleme aynı ajan için replace eder, hata vermez
    again = list_agent("agent-1", "Randezvu", "randezu", 7.0, "kanit-2",
                       db=db)
    assert again.price_target == 7.0


# -------------------------------------------------------- place_bid replay


def test_place_bid_negatif_tutar_ve_nonce_replay_reddedilir(db: str) -> None:
    with pytest.raises(ValueError, match="tutarı > 0"):
        place_bid("agent-1", "buyer-1", -1.0, "{}", "n-1", db=db)
    list_agent("agent-1", "isim", "servis", 1.0, "kanit", db=db)
    bid = place_bid("agent-1", "buyer-1", 3.0, '{"isim": "x"}', "n-1", db=db)
    assert isinstance(bid, Bid)
    assert bid.status == "pending"
    with pytest.raises(ValueError, match="nonce zaten kullanılmış"):
        place_bid("agent-1", "buyer-1", 3.0, "{}", "n-1", db=db)


# -------------------------------------------------------- match_bid kuralı


def test_match_bid_fiyat_hedefi_karsilastirmasi(db: str) -> None:
    """Faz 0 kuralı: teklif >= fiyat-hedefi → eşleşir, aksi halde reddedilir."""
    list_agent("agent-1", "isim", "randevu", 10.0, "kanit", db=db)

    dusuk = place_bid("agent-1", "buyer-1", 9.99, "{}", "n-dusuk", db=db)
    assert match_bid(dusuk.bid_id, db=db) is None  # hedefin altı → reddet

    esik = place_bid("agent-1", "buyer-1", 10.0, "{}", "n-esik", db=db)
    m = match_bid(esik.bid_id, db=db)
    assert isinstance(m, Match)
    assert m.amount == 10.0
    assert m.work_done is False           # eşleşme henüz kanıtlanmadı
    assert m.receipt_hash is None
    assert match_bid(esik.bid_id, db=db) is None  # zaten matched → tekrar yok

    assert match_bid("bid-yok", db=db) is None    # bilinmeyen teklif → None


# ------------------------------------------------- complete_work kanıt zinciri


def test_complete_work_kanitsiz_ve_bilinmeyen_reddedilir(db: str) -> None:
    list_agent("agent-1", "isim", "randevu", 10.0, "kanit", db=db)
    bid = place_bid("agent-1", "buyer-1", 12.0, "{}", "n-1", db=db)
    m = match_bid(bid.bid_id, db=db)
    assert m is not None

    with pytest.raises(ValueError, match="receipt_hash zorunlu"):
        complete_work(m.match_id, "", db=db)       # kanıtsız tamamlama yok
    with pytest.raises(ValueError, match="eşleşme bulunamadı"):
        complete_work("match-yok", "kanit-hash", db=db)

    tamamlanan = complete_work(m.match_id, "receipt-abc", db=db)
    assert tamamlanan.work_done is True            # ⭐ boolean kanıt kapandı
    assert tamamlanan.receipt_hash == "receipt-abc"
    assert tamamlanan.completed_at is not None


# -------------------------------------------------------- market_summary


def test_market_summary_kanit_bagli_hacim_raporlar(db: str) -> None:
    list_agent("agent-1", "isim", "randevu", 10.0, "kanit", db=db)
    list_agent("agent-2", "isim-2", "repricing", 20.0, "kanit-2", db=db)
    bid = place_bid("agent-1", "buyer-1", 15.0, "{}", "n-1", db=db)
    m = match_bid(bid.bid_id, db=db)
    assert m is not None
    complete_work(m.match_id, "receipt-xyz", db=db)

    ozet = market_summary(db=db)
    assert ozet["listed_agents"] == 2
    assert ozet["total_listings"] == 2
    assert ozet["bids"].get("matched") == 1
    assert ozet["completed_work"] == 1
    assert ozet["verified_volume_usd"] == 15.0  # sadece kanıtlanan iş sayılır
