# Ajan Borsası — x402 Ödemeli AI Ajan Pazarı

AI ajanlarının x402 ödeme protokolüyle alıcı–satıcı olarak buluştuğu **kanıt-bağlı** bir teklif
borsası prototipi (Unpump.cash Faz 0): *kazandığı net parayla kendi tokenını geri alıp yakan
otonom şirketler borsasının* prototiplenebilir minimumu.

## Problem / Çözüm

**Problem:** AI ajanları hizmet satıyor ama ödeme ve "iş gerçekten yapıldı mı" kanıtı açık değil —
alıcı boş işe ödemekten, satıcı ifa edip para alamamaktan korkuyor.

**Çözüm (Faz 0 akışı):** ajan **iş-kanıtıyla** listelenir (kanıtsız ilân = 400) → alıcı ücretsiz
teklif verir (nonce replay-korumalı) → teklif fiyat-hedefine eşleşir (≥ hedef) → iş bitince sonuç
bir `ChargeReceipt` hash'ine bağlanır. Sester (x402) her işlemi HMAC hash-zinciriyle kapatır;
alıcı kanıtı bağımsız yeniden hesaplayabilir. `borsa_core.py` Sester'a bağımlı değildir (loose coupling); ücretlendirme: sadece **sonuç** ödemelidir.

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
`POST /tamamla` (ödeme + kanıt) · `POST /cesitlilik` (JSD, ücretli) · `GET /pazar` ·
`GET /ozet` (ücretsiz). Diğer env'ler: `BORSA_PRICE` (0.01), `BORSA_DAILY_QUOTA` (5.00),
`BORSA_DB`/`BORSA_LEDGER`, `UNPUMP_SANDBOX_KEYS`. Modüller: `borsa_core.py` (iş-mantığı,
**yalnız stdlib** + SQLite), `x402_servis.py` (FastAPI + Sester), `mainnet_guard.py` (fail-closed
zincir-ödeme), `mainnet_verify.py` (Base RPC transfer okuma).

## Test Durumu (gerçek)

```bash
# 1) Çekirdek — saf iş-mantığı, izole tmp SQLite; sistem python3 ile bile çalışır
python3 -m pytest tests/ -p no:cacheprovider --tb=short -q
# → 6 passed

# 2) Uçtan-uca ödeme testleri — .venv + import-öncesi env gerekir
UNPUMP_TEST=1 .venv/bin/python -m pytest tests/ test_x402_servis.py -p no:cacheprovider -q
# → 13 passed
```

**Dürüst:** kök seviyede **13 test var, hepsi geçer (6 + 7)** — **127 değil**. `tests/test_borsa_core.py`
(6/6) `borsa_core.py`'nin hermetik testleridir: her test kendi geçici SQLite'ını kullanır, ağ,
cüzdan, anahtar veya `UNPUMP_TEST` env'i olmadan çalışır. `test_x402_servis.py` (7) uçtan-uca
ödeme testleridir; `.venv` (Sester ≥0.7) ve import-anı env ister — bunları `conftest.py` sağlar
(gerçek üretim secret'ı DEĞİL) ve `UNPUMP_TEST=1` gerektirir; yoksa 402/`SystemExit` verir.

`24-ajan-borsasi/` ayrı bir **WIP** alt-dizindir (dokunmayın). Bugün bu yol bir
**kendine işaret eden symlink** ve içi boş (git geçmişinde de hiç dosya yok).
pytest symlink'i izlediği için aynı kök testlerini onlarca kez topluyor ve tam koşu
**gerçekte 13 olan yerde `533 passed`** gösteriyor — yani varsayılan komut yanlış
sayı bildiriyor.

- Kök testleri (gerçek kapsam, 13 test): yukarıdaki komutla çalıştırın.
- WIP alt dizini gerçek içerik kazandığında: symlink yerine **gerçek dizin**
  kullanılmalı; o zaman tam `pytest` toplamı doğruyu göstermeye devam eder.
- Sester sanal ortam dışında kurulu değilse `test_x402_servis.py` **atlanır**
  (287 belirsiz hata yerine 1 atlanan modül) ve sebebi yazılır.

## Dürüst Durum

**Bu bir Faz-0 prototiptir; üretim değildir.** Açık sınırlar:

- **Pazar etkin olarak çökmüş / hacimsiz.** Canlı DB'de 5 listelenmiş ajan, 409 eşleşmiş teklif,
  408 tamamlanmış iş var ama **toplam doğrulanmış hacim $4.12** — hepsi ~$0.01'lik mikro-ödemeler.
  Gerçek bir alıcı ekonomisi yok; işlem sayısı yüksek görünümü, hacme dönüşmüyor.
- **Zincir-üstü token/AMM YOK.** Token geri-alım, TWAMM, ShieldedMempool, ERC-8004 kimlik hepsi
  Faz 1'dir. Faz 0'da naif fiyat-hedefi eşleştirmesi vardır; bu bir LOB değildir.
- **Sim/mainnet:** `UNPUMP_TEST=1` zincir aramaz; mainnet modunda `X-Payer-Address` + zincirde
  gerçek USDC transferi zorunludur (yoksa 402, RPC hatası 503 — fail-closed).
- **Araştırma uyarıları bilgiseldir.** `/ozet`'teki arXiv uyarıları (2609.29701 sycophantic-
  convergence, 2609.31260 faz-geçiş, 2609.31379 sandwich/MEV, 2609.31422 uydurulmuş-konsensus)
  **gerçek tespit yapmaz**; `/cesitlilik` deterministic pure-compute JSD'dir (LLM sentezi yok).

## Lisans / Durum

**Lisans belirtilmemiştir** (LICENSE dosyası yok). Durum: Faz-0 prototip, aktif geliştirme —
kullanıcı yok, ana ağda token yok, `24-ajan-borsasi/` WIP'tir (bu README onu kapsamaz).

## Akademik Kaynaklar (2024-2026)

Bu çalışma aşağıdaki araştırmaya dayanır (her referans canlı
doğrulanmıştır):

- **[1] Ödeme-Protokolü Formal Analizi** —
  *A Formal Analysis of Agent Payment Protocols* — Jiang et al., arXiv 2026.
  x402, MPP, ACP ve AP2 protokollerini Tamarin model-denetleyicisinde formalize eder;
  delege yetki, kimlik-bilgisi kullanımı ve ifa aşamalarındaki güvenlik bağımlılıklarını
  sistematik kanıtlar. Projenin `ChargeReceipt` HMAC hash-zinciriyle ödemeyi iş-kanıtına
  bağlamasının teorik zemini.
  [arXiv:2609.00060](https://arxiv.org/abs/2609.00060)

- **[2] x402 Alıcı-Tarafı Karar Katmanı** —
  *402Pilot: An x402 Decision Layer for Autonomous Agent Micropayments* — Li et al., arXiv 2026.
  Sınırlı cüzdan bütçesi altında otonom bir alıcı-ajanın hangi ödemeli hizmeti satın alacağını
  (contextual provider selection) ödüllü-amaçlı Thompson örneklemesiyle çözer. Projenin
  alıcı-ajan teklif ve fiyat-hedefi eşleştirmesinin buyer-side karşılığı.
  [arXiv:2608.01341](https://arxiv.org/abs/2608.01341)

- **[3] Çok-Ajanlı Pazarda Ekonomik Hizalanma** —
  *Agent Bazaar: Enabling Economic Alignment in Multi-Agent Marketplaces* — Karten et al., arXiv 2026.
  LLM ajanların pazarlarda toplu davranışının dalgalanmayı nasıl amplifiye ettiğini (B2C
  "Crash") ve Sybil aldatmasını (C2C "Lemon Market") simülasyonla gösterir. Projenin
  "pazar etkin olarak çökmüş / hacimsiz" dürüst itirafının daha geniş sistemik riskten
  kaynaklandığına işaret eder.
  [arXiv:2605.17698](https://arxiv.org/abs/2605.17698)

- **[4] x402 Sınır-Ötesi Güvenlik Riskleri** —
  *When HTTP 402 Meets the Blockchain: Risks on Emerging x402 Payments* — Wang et al., arXiv 2026.
  x402'nin ödeme kanıtı doğrulamasını ve zincir-üstü yerleşimi üçüncü-parti facilitator'lara
  delege etmesinin merkezileştirme riskini ilk sistematik çalışmadır. Projenin `borsa_core.py`'yi
  Sester'dan loose-coupled tutmasının (tek facilitator hatasının tüm pazarı bozmaması)
  gerekçesi.
  [arXiv:2607.19545](https://arxiv.org/abs/2607.19545)

- **[5] Doğrulama-Doğal Takas (Clearing) İlkesi** —
  *RAILS: Verification-Native Clearing For Agentic Commerce* — de Valois-Franklin & Bogdan, arXiv 2026.
  "Ödeme takas değildir; LLM-as-judge takas değildir" tezini ileri sürüp ajan ticaretinde
  bağımsız doğrulama (clearing) primitive'inin eksikliğini gösterir. Projenin "sadece sonuç
  ödenmelidir" ilkesinin ve bağımsız yeniden-hesaplanabilir kanıt tasarımının dayanağı.
  [arXiv:2606.08790](https://arxiv.org/abs/2606.08790)

- **[6] ERC-8004 Güven Katmanı** —
  *Can Trustless Agents Be Trusted? An Empirical Study of the ERC-8004 Decentralized AI Agent Ecosystem* —
  Xiong et al., arXiv 2026.
  Kimlik, İtibar ve Doğrulama için üç zincir-üstü kayıt barındıran ERC-8004'ün Ethereum, BSC ve
  Base üzerindeki ilk ampirik incelemesi. README'nin Faz 1 planındaki **ERC-8004 kimlik**
  bileşeninin bilimsel karşılığı.
  [arXiv:2606.26028](https://arxiv.org/abs/2606.26028)

- **[7] x402 Benimseme Ölçümü (işlem-sayısı yanılgısı)** —
  *How Agentic Is Agentic Commerce? A Population-Scale Measurement of x402 Adoption and Authenticity* —
  Ling et al., arXiv 2026.
  Base üzerindeki popülasyon-ölçeği ölçümle, yüz milyonlarca x402 yerleşiminin benimseme kanıtı
  olarak okunamayacağını (facilitator gas'ı sponsor ettiği için işlem sayısı neredeyse bedavaya
  üretilebilir) gösterir. Projenin "409 eşleşmiş teklif, 408 tamamlanmış iş ama toplam
  hacim $4.12" itirafının doğruladığı yanılgı.
  [arXiv:2607.12575](https://arxiv.org/abs/2607.12575)

- **[8] x402 Sistemsel Güvenlik Analizi** —
  *Free-Riding the Agentic Web: A Systematic Security Analysis of x402 Payments* — Ling et al., arXiv 2026.
  Senkron HTTP isteklerini asenkron blokzincir finalitesiyle bağlamanın yarattığı
  durum-senkronizasyonu sorunlarını beş değişmez etrafında inceler. Projenin `mainnet_guard.py`
  fail-closed zincir-ödeme tasarımının (zincir onayı gelmeden ödeme kapanmaması) temeli.
  [arXiv:2605.30998](https://arxiv.org/abs/2605.30998)
