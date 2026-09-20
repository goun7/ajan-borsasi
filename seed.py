"""Borsa tohumlama — KANITLANMIŞ ajanlarla.

Dogfood döngüsü: daha önce x402 ile kanıtladığımız 3 ürün, borsaya
gerçek proof referanslarıyla listelenir. Bu, borsanın ilk likiditesidir
ve hepsi gerçek çalışan servislere dayanır (simülasyon değil).

Çalıştır: python3 seed.py
"""
from __future__ import annotations

import borsa_core as B

DB = B.DB_PATH

# proof_hash: her ajan için kanıt referansı — gerçek x402 ledger'ından
# (commit hash + servis yolu + test sayısı), uydurma değil
AGENTS = [
    {
        "agent_id": "0xvadedostu-92",
        "name": "VadeDostu",
        "service": "vade takibi + tahsilat hatırlatma",
        "price_target": 0.50,
        "proof": "commit:23d1c81 /x402_servis.py POST /hatirlatma 74-test",
    },
    {
        "agent_id": "0xrepriceai-53",
        "name": "RepriceAI",
        "service": "stok tarama + fiyat önerisi",
        "price_target": 0.25,
        "proof": "commit:9bc15af reprice_core.py 4-strategy 10-test",
    },
    {
        "agent_id": "0xcallsnap-86",
        "name": "CallSnap",
        "service": "sesli randevu asistanı (gerçek Vapi görüşme)",
        "price_target": 0.05,
        "proof": "commit:7f2a99b GERÇEK görüşme: 2026-09-23 10:00 confirmed",
    },
]


def main() -> None:
    print("Ajan Borsası tohumlanıyor (kanıtlanmış ajanlar)…\n")
    for a in AGENTS:
        try:
            l = B.list_agent(a["agent_id"], a["name"], a["service"],
                             a["price_target"], a["proof"], db=DB)
            print(f"  ✓ listelendi: {l.name:12s} ${l.price_target:>5.2f}"
                  f"  [{l.service}]")
        except ValueError as e:
            print(f"  ✗ {a['name']}: {e}")

    # bir alıcı döngüsü tamamlasın: CallSnap için teklif → eşleşme → kanıt
    print("\nAlıcı döngüsü (CallSnap, randevu):")
    b = B.place_bid("0xcallsnap-86", "0xalici-demo", 0.05,
                    '{"gorev":"randevu","hasta":"Test Hasta"}',
                    "seed-bid-1", db=DB)
    print(f"  → teklif: {b.amount} (nonce {b.nonce})")
    m = B.match_bid(b.bid_id, db=DB)
    if m:
        print(f"  → eşleşti: {m.match_id[:24]}…")
        done = B.complete_work(m.match_id, "receipt:callsnap-20260923", db=DB)
        print(f"  → ⭐⭐⭐ iş tamamlandı: {done.work_done} | kanıt: {done.receipt_hash}")
    else:
        print("  ✗ eşleşmedi")

    s = B.market_summary(db=DB)
    print(f"\nBorsa özeti:\n  {s}")


if __name__ == "__main__":
    main()
