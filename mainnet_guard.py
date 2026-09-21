"""Ortak mainnet ödeme doğrulama yardımcısı — tüm x402 ajanları için.

GÜVENLİK: v1 sester imzası "ben ödedim" der ama zincirde transfer
olmayabilir. Bu modül imzaya EK olarak gerçek USDC transferini
zincirde arar — bulunamazsa 402 (fail-closed).

Kullanım (herhangi bir x402 servisinin ücretli endpoint'inde):

    from mainnet_guard import require_mainnet_payment

    @app.post("/tara")
    async def tara(girdi, request: Request):
        payer = require_mainnet_payment(request, price=PRICE,
                                        pay_to=MAINNET_PAY_TO,
                                        service_name="pqhaven",
                                        ledger=ledger)
        # ... iş ...

Çevre:
  <SVC>_MAINNET=1 (varsayılan) — zincirde transfer arar
  UNPUMP_TEST=1 — test modu, sim (zincir aramaz)
  <SVC>_MAINNET_PAY_TO=0x... — ödeme alma cüzdanı
"""
from __future__ import annotations

import os

from fastapi import HTTPException, Request


def _truthy(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default) not in ("0", "", "false")


def require_mainnet_payment(
    request: Request,
    *,
    price: float,
    pay_to: str,
    service_name: str,
    test_mode_var: str | None = None,
) -> str | None:
    """Ücretli endpoint'te gerçek zincir ödemesi gerektir.

    Döndürür: payer adresi (doğrulandı) veya test modunda None.
    Hata: 402 (ödeme yok / eksik), 500 (yapılandırma), 503 (RPC).
    """
    svc = test_mode_var or f"{service_name.upper()}_MAINNET"
    test = _truthy("UNPUMP_TEST", "0")
    if test or not _truthy(svc, "1"):
        # test/sim modu — zincir arama
        return None

    if not pay_to:
        raise HTTPException(
            status_code=500,
            detail=f"{service_name}: MAINNET_PAY_TO ayarlanmamış",
        )

    payer = request.headers.get("x-payer-address", "").strip()
    if not payer.startswith("0x") or len(payer) != 42:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "payment_required",
                "hint": "mainnet modu: X-Payer-Address header gerekli (0x...)",
                "contract": "USDC (Base mainnet)",
            },
        )

    try:
        import mainnet_verify as mv
        tr = mv.verify_mainnet_payment(
            from_addr=payer, to_addr=pay_to, amount_usd=price,
        )
    except Exception as e:
        # fail-closed: RPC hatası → sonuç yok
        raise HTTPException(
            status_code=503,
            detail=f"mainnet RPC hatası (fail-closed): {e}",
        )

    if not tr.found:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "payment_required",
                "hint": f"{payer} → {pay_to} adresine ${price} USDC "
                        f"transferi bulunamadı",
                "detail": tr.detail,
                "network": "base-mainnet",
            },
        )
    return payer
