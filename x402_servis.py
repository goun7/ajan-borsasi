"""Ajan Borsası x402 ödemeli servis — Unpump.cash prototipi.

Borsa tezinin Faz 0 prototipi: listeleme (satış ilanı), teklif (alış
emri), kanıt-bağlı tamamlama. Sester ödeme-katmanı; her başarılı iş bir
ChargeReceipt hash'i ile kapatılır — machine-checkable kanıt.

Dogfood: borsaya listelenen ajanlar, daha önce kanıtladığımız ürünlerdir
(VadeDostu, RepriceAI, CallSnap) — gerçek proof_hash'lerle listelenirler.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from sester import __version__ as SESTER_VERSION
from sester.ledger import Ledger
from sester.middleware import SesterMeter

from borsa_core import (
    AgentListing, Bid, Match, list_agent, place_bid, match_bid,
    complete_work, market_summary,
)

PRICE = float(os.environ.get("BORSA_PRICE", "0.01"))
DAILY_QUOTA = float(os.environ.get("BORSA_DAILY_QUOTA", "5.00"))
SELLER_SECRET = os.environ.get("BORSA_SELLER_SECRET", "borsa-demo-secret-v0")
PAY_TO = os.environ.get("BORSA_PAY_TO", "sester:ajan-borsasi")
DB_PATH = os.environ.get(
    "BORSA_DB", str(Path.home() / ".workspace" / "ajan-borsasi" / "borsa.sqlite")
)
LEDGER_PATH = os.environ.get(
    "BORSA_LEDGER", str(Path.home() / ".workspace" / "ajan-borsasi" / "receipts.sqlite")
)

Path(LEDGER_PATH).parent.mkdir(parents=True, exist_ok=True)
ledger = Ledger(LEDGER_PATH)

app = FastAPI(
    title="Ajan Borsası ödemeli servis",
    version="0.1.0",
    description="Unpump.cash prototipi — iş-kanıtlı ajan teklif borsası",
)
app.add_middleware(
    SesterMeter,
    ledger=ledger,
    price=PRICE,
    daily_quota=DAILY_QUOTA,
    secret=SELLER_SECRET,
    pay_to=PAY_TO,
    # Ücretlendirme modeli: sadece /tamamla ödemeli (iş bittiğinde).
    # Listeleme/teklif/eşleştirme ücretsiz — alıcı için giriş engeli yok;
    # ödeme KANITLANMIŞ iş sonucunda alınır (değer-transferi modeli).
    exempt_prefixes=(
        "/healthz", "/ozet", "/pazar", "/docs", "/openapi.json", "/redoc",
        "/favicon.ico", "/listele", "/teklif-ver", "/eslestir",
    ),
)


# ---------------------------------------------------------------- modeller


class ListingGirdisi(BaseModel):
    agent_id: str = Field(..., description="ajan cüzdan-adresi")
    name: str
    service: str
    price_target: float = Field(..., gt=0)
    proof_hash: str = Field(..., description="iş-kanıtı hash'i — zorunlu")


class BidGirdisi(BaseModel):
    agent_id: str
    amount: float = Field(..., gt=0)
    work_spec: str
    nonce: str


class TamamlamaGirdisi(BaseModel):
    match_id: str
    receipt_hash: str = Field(..., description="ChargeReceipt hash — zorunlu")


# ---------------------------------------------------------------- uçlar


@app.get("/healthz")
def healthz() -> dict:
    return {
        "status": "ok",
        "sester": SESTER_VERSION,
        "ledger_chain_valid": ledger.verify_chain(),
        "price": f"${PRICE} (işlem başına)",
        "protocol": "Unpump.cash Faz-0 prototipi",
    }


@app.post("/listele", response_model=dict)
def listele(girdi: ListingGirdisi) -> dict:
    """Ajanı borsaya listele — kanıtsız listelenmez (fail-closed)."""
    try:
        l = list_agent(girdi.agent_id, girdi.name, girdi.service,
                       girdi.price_target, girdi.proof_hash, db=DB_PATH)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return asdict_safe(l)


@app.post("/teklif-ver", response_model=dict)
def teklif_ver(girdi: BidGirdisi) -> dict:
    """Alıcı teklif emri. nonce replay-korumalı."""
    buyer = "buyer"  # middleware agent'ı X-Payment'tan çıkarır; Faz 0'da basit
    try:
        b = place_bid(girdi.agent_id, buyer, girdi.amount, girdi.work_spec,
                      girdi.nonce, db=DB_PATH)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return asdict_safe(b)


@app.post("/eslestir/{bid_id}", response_model=dict)
def eslestir(bid_id: str) -> dict:
    """Teklifi ajanın fiyat-hedefiyle eşleştir."""
    m = match_bid(bid_id, db=DB_PATH)
    if m is None:
        raise HTTPException(
            status_code=404,
            detail="teklif eşleşmedi (yok / düşük / zaten işlenmiş)",
        )
    return asdict_safe(m)


@app.post("/tamamla", response_model=dict)
def tamamla(girdi: TamamlamaGirdisi) -> dict:
    """İş bitti — kanıt bağla. ⭐⭐⭐ iş-tamamlandı boolean'ı."""
    try:
        m = complete_work(girdi.match_id, girdi.receipt_hash, db=DB_PATH)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # ödeme kanıtını Sester ledger'ına yaz (machine-checkable)
    seq = ledger.append(
        "charge_receipt", "buyer", "/tamamla", PRICE,
        payload={"match_id": m.match_id, "work_done": True,
                 "agent": m.agent_id, "amount": m.amount},
    )
    d = asdict_safe(m)
    d["ledger_seq"] = seq.get("seq", -1) if isinstance(seq, dict) else -1
    return d


@app.get("/pazar")
def pazar() -> dict:
    """Ücretsiz: borsa güven tablosu."""
    return market_summary(db=DB_PATH)


@app.get("/ozet")
def ozet() -> dict:
    per_agent = ledger.per_agent_summary() if hasattr(
        ledger, "per_agent_summary") else {}
    return {
        "price_per_settlement": f"${PRICE}",
        "chain_valid": ledger.verify_chain(),
        "per_agent": per_agent,
        "market": market_summary(db=DB_PATH),
        "thesis": "iş-kanıtlı ajan borsası — kanıtsız listeleme/tamamlama yok",
    }


def asdict_safe(o) -> dict:
    from dataclasses import asdict
    return asdict(o)
