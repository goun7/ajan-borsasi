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

from fastapi import FastAPI, HTTPException, Request
from mainnet_guard import require_mainnet_payment, resolve_treasury
from pydantic import BaseModel, Field

from sester import __version__ as SESTER_VERSION
from sester.ledger import Ledger
from sester.middleware import SesterMeter

from borsa_core import (
    AgentListing, Bid, Match, list_agent, place_bid, match_bid,
    complete_work, market_summary,
)

PRICE = float(os.environ.get("BORSA_PRICE", "0.01"))
# mainnet: gerçek zincir USDC transferi zorunlu (sıfır-ödeme bypass kapanır)
MAINNET_PAY_TO = resolve_treasury("borsa")  # tek-kasa: UNPUMP_TREASURY_EOA (fail-closed)
DAILY_QUOTA = float(os.environ.get("BORSA_DAILY_QUOTA", "5.00"))
# GUVENLIK: zayif default YOK — bos secret receipt HMAC zincirini
# baska anahtarla yazar ( verify_chain False). fail-closed.
_raw_secret = os.environ.get("BORSA_SELLER_SECRET", "")
if not _raw_secret:
    raise SystemExit(
        "secret-required: BORSA_SELLER_SECRET-ZORUNLU — bos/zayif-secret "
        "receipt HMAC zincirini baska anahtarla yazar.")
SELLER_SECRET = _raw_secret
PAY_TO = os.environ.get("BORSA_PAY_TO", "sester:ajan-borsasi")
DB_PATH = os.environ.get(
    "BORSA_DB", str(Path.home() / ".workspace" / "ajan-borsasi" / "borsa.sqlite")
)
LEDGER_PATH = os.environ.get(
    "BORSA_LEDGER", str(Path.home() / ".workspace" / "ajan-borsasi" / "receipts.sqlite")
)

Path(LEDGER_PATH).parent.mkdir(parents=True, exist_ok=True)
ledger = Ledger(LEDGER_PATH, secret=SELLER_SECRET)

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
        "/cesitlilik",
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


class CesitlilikGirdisi(BaseModel):
    """arXiv:2609.29701: ajan tercih-dagilimlari ( olasilik vektoru)."""
    ajan_dagilimlari: list[list[float]] = Field(
        ..., description="her ajanin tercih-dagilimi ( >=2 ajan, >=2 tercih)")


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
def eslestir(bid_id: str, request: Request) -> dict:
    """Teklifi ajanın fiyat-hedefiyle eşleştir.
    GÜVENLİK: zincirde gerçek USDC transferi zorunlu (mainnet modu)."""
    # mainnet ödeme doğrulama (test modunda atlanır)
    require_mainnet_payment(
        request, price=PRICE, pay_to=MAINNET_PAY_TO,
        service_name="borsa",
    )
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


@app.post("/cesitlilik")
def cesitlilik(request: Request, girdi: CesitlilikGirdisi) -> dict:
    """Ajan oy-çeşitliliği analizi ( ucretli: $PRICE).

    ARASTIRMA: arXiv:2609.29701 ( Huang et al., 2026) 'Multi-Agent Debate
    for Explainable Trading' — ajanlarin 'sycophantic convergence'
    basari-disi-modunu Jensen-Shannon divergence ile OLCTEK;
    anlasmazligi korumak Sharpe +0.14 ( p=0.028) artirdi.

    Girdi: her ajanin tercih-dagilimi ( olasilik vektoru).
    Cikti: ortalama ikili JSD + ceşitlilik karari.
    """
    require_mainnet_payment(
        request, price=PRICE, pay_to=MAINNET_PAY_TO,
        service_name="borsa",
    )
    daglar = girdi.ajan_dagilimlari
    if len(daglar) < 2:
        raise HTTPException(status_code=400, detail="en az 2 ajan gerekli")
    if len(daglar) > 50:
        raise HTTPException(status_code=400, detail="en fazla 50 ajan")
    boyut = len(daglar[0])
    if boyut < 2:
        raise HTTPException(status_code=400, detail="en az 2 tercih")
    for d in daglar:
        if len(d) != boyut:
            raise HTTPException(status_code=400,
                                detail="tüm dağılımlar aynı boyutta olmalı")
        if not all(v >= 0 for v in d):
            raise HTTPException(status_code=400, detail="negatif olasılık")

    import math

    def _jsd(p, q):
        p = [max(v, 0.0) for v in p]
        q = [max(v, 0.0) for v in q]
        sp, sq = sum(p), sum(q)
        if sp <= 0 or sq <= 0:
            return 1.0
        p = [v / sp for v in p]
        q = [v / sq for v in q]
        m = [(a + b) / 2.0 for a, b in zip(p, q)]

        def _kl(x, y):
            return sum(xi * math.log2(xi / yi) for xi, yi in zip(x, y)
                       if xi > 0 and yi > 0) or 0.0
        return 0.5 * _kl(p, m) + 0.5 * _kl(q, m)

    ikili = []
    for i in range(len(daglar)):
        for j in range(i + 1, len(daglar)):
            ikili.append(_jsd(daglar[i], daglar[j]))
    ortalama = sum(ikili) / len(ikili)
    # JSD [0,1]; 0 = TAM AYNI ( sycophantic convergence), ln(2)~0.693 = tam
    # farkli; 0.1+ makul cesitlilik
    if ortalama < 0.02:
        karar = "SYCOPHANTIC-CONVERGENCE"
        aciklama = ("ajanlar_bagimsiz-pozisyonlarini_birakmis — arXiv:2609.29701"
                    " basari-disi-modu; anlasmazligi korumak Sharpe +0.14")
    elif ortalama < 0.10:
        karar = "DUSUK-CECESITLILIK"
        aciklama = "ajanlar birbirine benziyor; daha fazla bagimsiz gorus"
    else:
        karar = "SAGLIKLI-CECESITLILIK"
        aciklama = "ajanlar bagimsiz dusunuyor — karar kalitesi yuksek"

    sonuc = {
        "ajan_sayisi": len(daglar),
        "tercih_sayisi": boyut,
        "ortalama_jsd": round(ortalama, 6),
        "min_jsd": round(min(ikili), 6),
        "max_jsd": round(max(ikili), 6),
        "karar": karar,
        "aciklama": aciklama,
        "kaynak": "arXiv:2609.29701 ( Huang et al., 2026)",
        "paid": PRICE,
    }
    seq = ledger.append("charge_receipt", "buyer", "/cesitlilik", PRICE,
                        payload=sonuc)
    out = dict(sonuc)
    out["ledger_seq"] = seq.get("seq", -1) if isinstance(seq, dict) else -1
    out["receipt_chain_valid"] = ledger.verify_chain()
    return out


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
