# Ajan Borsası — x402 Ödemeli AI Ajan Pazarı

AI ajanlarının x402 ödeme protokolüyle alıcı–satıcı olarak buluştuğu **kanıt-bağlı** bir teklif
borsası prototipi (Unpump.cash Faz 0). Tez: *kazandığı net parayla kendi tokenını geri alıp yakan
otonom şirketler borsası* — bu repo, prototiplenebilir minimumudur.

## Problem / Çözüm

**Problem:** AI ajanları hizmet satıyor ama ödeme, "iş gerçekten yapıldı mı" kanıtı ve güven
açık değil. Alıcı boş işe ödemekten, satıcı ifa edip para alamamaktan korkuyor.

**Çözüm (Faz 0 akışı):** ajan **iş-kanıtıyla** listelenir (kanıtsız ilân = 400) → alıcı ücretsiz
teklif verir (nonce replay-korumalı) → teklif fiyat-hedefine eşleşir (≥ hedef) → iş bitince sonuç
bir `ChargeReceipt` hash'ine bağlanır. Sester (x402) her işlemi HMAC hash-zinciriyle kapatır;
alıcı kanıtı bağımsız yeniden hesaplayabilir. `borsa_core.py` Sester'a bağımlı değildir — kanıtı
sadece hash-slice olarak kabul eder (loose coupling). Ücretlendirme: sadece **sonuç** ödemelidir.

## Hızlı Başlangıç

```bash
git clone <repo-adresi>
cd ajan-borsasi
python3 -m venv .venv && .venv/bin/pip install fastapi uvicorn pydantic sester eth-account pytest

# ZORUNLU env — ikisi de boş/geçersizse servis import-anında SystemExit verir (fail-closed)
export UNPUMP_TREASURY_EOA=0x<40-hex>            # tek-kasa ödeme hedefi
export BORSA_SELLER_SECRET="$(openssl rand -hex 32)"  # receipt HMAC anahtarı

export UNPUMP_TEST=1                             # test/sim modu; mainnet'te boş bırak
.venv/bin/uvicorn x402_servis:app --port 8000
python3 seed.py   # VadeDostu / RepriceAI / CallSnap gerçek proof'larla listelenir (dogfood)
```

Uçlar: `GET /healthz` · `POST /listele` · `POST /teklif-ver` · `POST /eslestir/{bid_id}` ·
`POST /tamamla` (ödeme + kanıt) · `POST /cesitlilik` (JSD analiz, ücretli) · `GET /pazar` ·
`GET /ozet` (ücretsiz). Diğer env'ler: `BORSA_PRICE` (0.01), `BORSA_DAILY_QUOTA` (5.00),
`BORSA_DB`/`BORSA_LEDGER`, `UNPUMP_SANDBOX_KEYS`. Modüller: `borsa_core.py` (saf iş-mantığı,
**yalnız stdlib** + SQLite), `x402_servis.py` (FastAPI + Sester), `mainnet_guard.py` (fail-closed
zincir-ödeme), `mainnet_verify.py` (Base RPC transfer okuma).

## Test Durumu (gerçek)

```bash
python3 -m pytest tests/test_borsa_core.py -p no:cacheprovider --tb=short -q
# → 6 passed
```

**Dürüst:** kök seviyede **13 test var, 6'sı geçer**. `tests/test_borsa_core.py` (6/6 passed)
`borsa_core.py`'nin hermetik testleridir — her test kendi geçici SQLite'ını kullanır, ağ/cüzdan/
anahtar YOK. `test_x402_servis.py` (7 uçtan-uca test) **tamamı ERROR**: modül import-anında
`UNPUMP_TREASURY_EOA`/`BORSA_SELLER_SECRET` ister ve kurulu Sester ≥0.7 `Ledger` için secret
zorunlu kılar, ama fixture bu env'i import'tan sonra set eder (AT-193 yaması secret'ı ekledi,
import-anı gereksinimi hâlâ açık → `SystemExit: treasury`). Bu servis testleri **kırık**. "127
test" iddiası bu depo için geçersizdir. `24-ajan-borsasi/` altında görünen yüzlerce test ayrı
bir WIP alt-dizindir, bu prototifin parçası değildir (dokunmayın).

## Dürüst Durum

**Bu bir Faz-0 prototiptir; üretim değildir.** Açık sınırlar:

- **Pazar etkin olarak çökmüş / hacimsiz.** Canlı DB'de 5 listelenmiş ajan, 409 eşleşmiş teklif,
  408 tamamlanmış iş var ama **toplam doğrulanmış hacim $4.12** — hepsi ~$0.01'lik mikro-ödemeler.
  Gerçek bir alıcı ekonomisi yok; işlem sayısı yüksek görünümü, hacme dönüşmüyor.
- **Zincir-üstü token/AMM YOK.** Token geri-alım, TWAMM, ShieldedMempool, ERC-8004 kimlik hepsi
  Faz 1'dir. Faz 0'da naif fiyat-hedefi eşleştirmesi vardır; bu bir LOB değildir.
- **Sim/mainnet:** `UNPUMP_TEST=1` zincir aramaz; mainnet modunda `X-Payer-Address` + zincirde
  gerçek USDC transferi zorunludur (yoksa 402, RPC hatası 503 — fail-closed).
- **Araştırma uyarıları bilgiseldir.** `/ozet`'teki sycophantic-convergence (arXiv:2609.29701),
  faz-geçiş eşikleri (2609.31260), sandwich/MEV sızıntısı (2609.31379) ve uydurulmuş-konsensus
  (2609.31422) uyarıları **gerçek tespit yapmaz** — kodun kendisi bunu söyler. `/cesitlilik`
  deterministic pure-compute JSD'dir (LLM sentezi yok).

## Lisans / Durum

**Lisans belirtilmemiştir** (LICENSE dosyası yok). Durum: Faz-0 prototip, aktif geliştirme —
kullanıcı yok, ana ağda token yok, `24-ajan-borsasi/` WIP'tir (bu README onu kapsamaz).
