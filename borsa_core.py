"""Ajan Borsası çekirdeği — Unpump.cash prototipi (Faz 0).

Tez (PROJE_KAGIDI §2.2): "kazandığı net parayla kendi tokenını geri alıp
yakan otonom şirketler borsası." Faz 0'da zincir-üstü token/AMM YOK —
bunlar Faz 1. Faz 0'ın prototiplenebilir minimumu:

  1. AJAN LİSTELEME — ajan, doğrulanmış iş-kanıtıyla listelenir
     (ChargeReceipt = machine-checkable kanıt, Sester'dan)
  2. TEKLİF — alıcı, bir iş için fiyat teklif eder (emir)
  3. EŞLEŞME — teklif, ajanın fiyat-hedefiyle karşılaştırılır
  4. KANIT-BAĞLI SONUÇ — iş bittiğinde ChargeReceipt bağlanır;
     randevu-boolean gibi ⭐⭐⭐ "iş tamamlandı mı" kanıtı

Sıfır bağımlılık (stdlib). Kalıcılık: SQLite. Üzerindeki katmanlar
(Faz 1): ERC-8004 kimlik, TWAMM geri-alım, ShieldedMempool — hepsi
Faz 0'da prototiplenmez; sadece arayüzleri sabitlenir.

Konsolide tez: Sester'ın ChargeIntent/ChargeReceipt'i, Ajan Borsası'nın
"emir kanıtı" olur. Bu modül Sester'a bağımlı DEĞİL — kanıt sadece
hash-chain slice olarak kabul eder (loose coupling).
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, asdict
from pathlib import Path

VERSION = "0.1.0"

DB_PATH = str(Path.home() / ".workspace" / "ajan-borsasi" / "borsa.sqlite")

# ---------------------------------------------------------------- modeller


@dataclass
class AgentListing:
    """Borsaya listelenmiş otonom ajan (bir 'şirket')."""
    agent_id: str               # cüzdan-adresi (non-custodial tez)
    name: str
    service: str                # ne iş yaptığı (örn "randevu", "repricing")
    price_target: float         # hedef fiyat (USD); teklifler bununla kıyaslanır
    proof_hash: str             # iş-kanıtı hash'i (ChargeReceipt zincirinden)
    listed_at: float
    status: str = "listed"      # listed | suspended | delisted


@dataclass
class Bid:
    """Alıcı teklifi (emir)."""
    bid_id: str
    agent_id: str
    buyer_id: str               # alıcı cüzdan-adresi
    amount: float               # teklif tutarı (USD)
    work_spec: str              # iş tanımı (JSON stringi)
    nonce: str                  # replay koruması
    created_at: float
    status: str = "pending"     # pending | matched | rejected | expired


@dataclass
class Match:
    """Eşleşen teklif + kanıt."""
    match_id: str
    bid_id: str
    agent_id: str
    amount: float
    work_done: bool             # ⭐⭐⭐ iş tamamlandı mı (boolean kanıt)
    receipt_hash: str | None    # ChargeReceipt hash (machine-checkable)
    completed_at: float | None


# ------------------------------------------------------------------ depo


def _connect(db: str = DB_PATH) -> sqlite3.Connection:
    Path(db).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("""CREATE TABLE IF NOT EXISTS listings (
        agent_id TEXT PRIMARY KEY, name TEXT, service TEXT,
        price_target REAL, proof_hash TEXT, listed_at REAL, status TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS bids (
        bid_id TEXT PRIMARY KEY, agent_id TEXT, buyer_id TEXT, amount REAL,
        work_spec TEXT, nonce TEXT UNIQUE, created_at REAL, status TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS matches (
        match_id TEXT PRIMARY KEY, bid_id TEXT, agent_id TEXT, amount REAL,
        work_done INTEGER, receipt_hash TEXT, completed_at REAL)""")
    c.commit()
    return c


# ------------------------------------------------------------------ işlemler


def list_agent(agent_id: str, name: str, service: str, price_target: float,
               proof_hash: str, db: str = DB_PATH) -> AgentListing:
    """Ajanı borsaya listele — proof_hash zorunlu (iş-kanıtsız listelenme yok)."""
    if not all([agent_id, name, service, proof_hash]):
        raise ValueError("eksik alan — proof_hash dahil hepsi zorunlu")
    if price_target <= 0:
        raise ValueError("price_target > 0 olmalı")
    c = _connect(db)
    now = time.time()
    c.execute(
        "INSERT OR REPLACE INTO listings VALUES (?,?,?,?,?,?,?)",
        (agent_id, name, service, price_target, proof_hash, now, "listed"))
    c.commit()
    c.close()
    return AgentListing(agent_id, name, service, price_target, proof_hash,
                        now, "listed")


def place_bid(agent_id: str, buyer_id: str, amount: float, work_spec: str,
              nonce: str, db: str = DB_PATH) -> Bid:
    """Alıcı teklifi (emir). nonce first-writer-wins — replay koruması."""
    if amount <= 0:
        raise ValueError("teklif tutarı > 0 olmalı")
    c = _connect(db)
    now = time.time()
    try:
        c.execute(
            "INSERT INTO bids VALUES (?,?,?,?,?,?,?,?)",
            (f"bid-{int(now)}-{hash(nonce)&0xffffffff:08x}", agent_id,
             buyer_id, amount, work_spec, nonce, now, "pending"))
        c.commit()
        bid_id = c.execute(
            "SELECT bid_id FROM bids WHERE nonce=?", (nonce,)).fetchone()[0]
    except sqlite3.IntegrityError:
        c.close()
        raise ValueError("nonce zaten kullanılmış (replay reddedildi)")
    c.close()
    return Bid(bid_id, agent_id, buyer_id, amount, work_spec, nonce, now,
               "pending")


def match_bid(bid_id: str, db: str = DB_PATH) -> Match | None:
    """Teklifi ajanın fiyat-hedefiyle eşleştir.

    Basit kural (Faz 0): teklif ≥ fiyat-hedefi → eşleşir.
    TWAMM/MEV-koruma Faz 1'de; Faz 0'da naif eşleştirme yeterli
    (prototip kanıtı için).
    """
    c = _connect(db)
    bid = c.execute("SELECT * FROM bids WHERE bid_id=?", (bid_id,)).fetchone()
    if not bid or bid["status"] != "pending":
        c.close()
        return None
    listing = c.execute(
        "SELECT * FROM listings WHERE agent_id=?", (bid["agent_id"],)
    ).fetchone()
    if not listing or listing["status"] != "listed":
        c.close()
        return None

    if bid["amount"] >= listing["price_target"]:
        match_id = f"match-{int(time.time())}-{hash(bid_id)&0xffffffff:08x}"
        c.execute(
            "UPDATE bids SET status='matched' WHERE bid_id=?", (bid_id,))
        c.execute(
            "INSERT INTO matches VALUES (?,?,?,?,?,?,?)",
            (match_id, bid_id, bid["agent_id"], bid["amount"], 0, None, None))
        c.commit()
        m = Match(match_id, bid_id, bid["agent_id"], bid["amount"], False,
                  None, None)
        c.close()
        return m
    c.execute("UPDATE bids SET status='rejected' WHERE bid_id=?", (bid_id,))
    c.commit()
    c.close()
    return None


def complete_work(match_id: str, receipt_hash: str,
                  db: str = DB_PATH) -> Match:
    """İş bitti — ChargeReceipt bağla ve ⭐⭐⭐ boolean'ı kapat.

    receipt_hash = Sester ledger'ından bir kanıt-slice hash'i
    (machine-checkable; alıcı bağımsız olarak yeniden hesaplayabilir).
    """
    if not receipt_hash:
        raise ValueError("receipt_hash zorunlu — kanıtsız tamamlama reddedilir")
    c = _connect(db)
    m = c.execute("SELECT * FROM matches WHERE match_id=?",
                  (match_id,)).fetchone()
    if not m:
        c.close()
        raise ValueError("eşleşme bulunamadı")
    now = time.time()
    c.execute(
        "UPDATE matches SET work_done=1, receipt_hash=?, completed_at=? "
        "WHERE match_id=?",
        (receipt_hash, now, match_id))
    c.commit()
    out = Match(match_id, m["bid_id"], m["agent_id"], m["amount"], True,
                receipt_hash, now)
    c.close()
    return out


def market_summary(db: str = DB_PATH) -> dict:
    """Borsa özeti — alıcı/satıcı güven tablosu."""
    c = _connect(db)
    listings = c.execute(
        "SELECT COUNT(*) n, SUM(CASE WHEN status='listed' THEN 1 ELSE 0 END) "
        "active FROM listings").fetchone()
    bids = c.execute(
        "SELECT status, COUNT(*) n FROM bids GROUP BY status").fetchall()
    done = c.execute(
        "SELECT COUNT(*) n, SUM(amount) volume FROM matches WHERE work_done=1"
    ).fetchone()
    c.close()
    return {
        "listed_agents": listings["active"],
        "total_listings": listings["n"],
        "bids": {r["status"]: r["n"] for r in bids},
        "completed_work": done["n"] or 0,
        "verified_volume_usd": round(done["volume"] or 0, 2),
        "note": "kanıt-bağlı: her tamamlanan iş ChargeReceipt hash taşır",
    }
