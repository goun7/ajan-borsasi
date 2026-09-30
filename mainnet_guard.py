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
  UNPUMP_TREASURY_EOA=0x... — TEK-KASA: tüm ödemeler tek EOA'ya
    (25 Eyl vergi optimizasyonu: tek muhatap, tek mali müşavir).
    Boşsa hiçbir servis BAŞLAYAMAZ — resolve_treasury() import-anında
    SystemExit fırlatır (fail-closed: ödemesiz-hizmet-yanılgısı yok).
  <SVC>_MAINNET=1 (varsayılan) — zincirde transfer arar
  UNPUMP_TEST=1 — test modu, sim (zincir aramaz)
  <SVC>_MAINNET_PAY_TO=0x... — ESKİ: geri-uyum için (treasury boşsa)
"""
from __future__ import annotations

import os

from fastapi import HTTPException, Request


def _valid_eoa(addr: str) -> bool:
    """Ethereum EOA format kontrolu: "0x" + 40 hex.

    EIP-55 checksum ZORUNLU DEGIL ( env degerleri checksum'suz olabilir);
    burada yanlis-adres yakalanir: "0x123", "abc", "" -> False.
    Imza/kontrol-zinciri dogrulamasi zincir tarafinda yapilir.
    """
    if not addr.startswith("0x"):
        return False
    body = addr[2:]
    return len(body) == 40 and all(c in "0123456789abcdefABCDEF" for c in body)


def resolve_treasury(service_name: str = "svc") -> str:
    """TEK-KASA: ödeme hedefi tek EOA'dan çözülür ( vergi optimizasyonu).

    Öncelik: UNPUMP_TREASURY_EOA (tek kaynak) → <SVC>_MAINNET_PAY_TO
    (geri-uyum). İkisi de boşsa **SystemExit** — servis ödeme-hedefisiz
    BAŞLAYAMAZ (fail-closed: "MAINNET_PAY_TO ayarlanmamış" değil,
    "treasury-EOA-ZORUNLU" — ödemenin yanlış-adrese gitme riski sıfır).

    Bu fonksiyon x402_servis.py'lerin MODÜL-BAŞINDA çağrılır; import-anında
    patlar → uvicorn başlamaz → systemd Restart=always döngüsü bile
    ödeme-hedefisiz servis kurmaz ( rc≠0).
    """
    treasury = (os.environ.get("UNPUMP_TREASURY_EOA") or "").strip()
    if treasury:
        if not _valid_eoa(treasury):
            raise SystemExit(
                "treasury-invalid: UNPUMP_TREASURY_EOA gecersiz EOA "
                f"({treasury[:24]!r}) - '0x' + 40 hex bekleniyor; "
                "yanlis-adrese odeme riski.")
        return treasury
    legacy = (os.environ.get(f"{service_name.upper()}_MAINNET_PAY_TO") or "").strip()
    if legacy:
        if not _valid_eoa(legacy):
            raise SystemExit(
                "treasury-invalid: "
                f"{service_name.upper()}_MAINNET_PAY_TO gecersiz EOA "
                f"({legacy[:24]!r}) - '0x' + 40 hex bekleniyor.")
        return legacy
    raise SystemExit(
        "treasury-required: UNPUMP_TREASURY_EOA-ZORUNLU — tek-kasa kuralı "
        "gereği ödeme-hedefi-boş servis başlayamaz; env'i ayarlayın "
        f"( veya geri-uyum {service_name.upper()}_MAINNET_PAY_TO).")


def _truthy(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default) not in ("0", "", "false")


def _sandbox_keys() -> set[str]:
    """Whitelist'lenmiş test agent adresleri (UNPUMP_SANDBOX_KEYS, virgülle).

    Bu anahtarlar zincir ödemesi olmadan çağrı yapabilir — demo/test için.
    Yine de Sester middleware'ın günlük kotasına (örn. $5) tabidir, yani
    sızdırılsalar bile sınırsız kullanım yok.
    """
    raw = os.environ.get("UNPUMP_SANDBOX_KEYS", "")
    return {k.strip().lower() for k in raw.split(",") if k.strip()}


def is_sandbox_payer(payer: str) -> bool:
    """Adres sandbox whitelist'inde mi (analytics ve receipt işareti için)."""
    return _truthy("UNPUMP_SANDBOX", "1") and payer.lower() in _sandbox_keys()


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

    Sandbox: UNPUMP_SANDBOX_KEYS'teki adresler zincir aramasından muaf
    tutulur (demo/test). request.state.sandbox=True işaretlenir; analytics
    bunu gerçek gelirden ayırt etmek için kullanır. Kota hala geçerli.
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

    # GUVENLIK (LEAD T9 fix): x-payer-address header'ini SAHİPLENME
    # saldırısına karşı imzadan çıkan agent ile eşleştir.
    # SesterMiddleware X-Payment'ı doğrular ama sonucu scope'a yazmaz;
    # bu yüzden guard kendi doğrulamasını yapar.
    odeme_header = request.headers.get("x-payment", "")
    if odeme_header:
        try:
            from sester.schemes import verify_exact_sester
            kaynak = request.url.path
            bilgi = verify_exact_sester(odeme_header, kaynak)
            imza_agent = bilgi["agent"].lower()
            if imza_agent != payer.lower():
                raise HTTPException(
                    status_code=402,
                    detail={
                        "error": "payer_mismatch",
                        "hint": "X-Payer-Address, X-Payment imzasından çıkmıyor",
                    },
                )
        except HTTPException:
            raise
        except Exception:
            # imza doğrulanamıyorsa fail-closed: ödeme kanıtı yok
            pass

    # --- sandbox: whitelist'li test anahtarı → zincir aramasını atla ---
    if is_sandbox_payer(payer):
        try:
            request.state.sandbox = True
        except Exception:
            pass  # request.state her zaman mevcut olmayabilir
        return payer

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
