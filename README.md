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

### Mesh'teki yeri — x402 ödeme hattının resmi bağı

Unpump'un ödeme katmanı **Sester**'dir ve bu bağımlılık artık
`requirements.txt` ile resmileştirilmiştir (`sester>=0.7.4`, PyPI).
Kullanılan yüzeyler:

- `sester.ledger.Ledger` — her eşleşmenin node-cosigned makbuz kaydı
- `sester.middleware.SesterMeter` — FastAPI üzerinde 402 ödeme kapısı
- `sester.__version__` — protokol el sıkışmasında sürüm şeffaflığı

## Deploy ( systemd + venv )

```bash
# 1) servis-kullanıcısı + dizin
sudo useradd -m -d /opt/ajan-borsasi ajanborsa
sudo -u ajanborsa git clone <repo-adresi> /opt/ajan-borsasi/app

# 2) venv + bağımlılıklar ( root-pip DEĞİL — PEP-668 koruması )
sudo -u ajanborsa bash -lc 'cd /opt/ajan-borsasi/app && \
  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt'

# 3) çevre ( /opt/ajan-borsasi/app.env )
cat >/opt/ajan-borsasi/app.env <<'EOF'
UNPUMP_TREASURY_EOA=0x<40-hex>
BORSA_SELLER_SECRET=<openssl rand -hex 32>
BORSA_PRICE=0.01
BORSA_DAILY_QUOTA=5.00
EOF

# 4) systemd-birimi
cat >/etc/systemd/system/ajan-borsasi.service <<'EOF'
[Unit]
Description=ajan-borsasi x402 servisi
After=network.target
[Service]
User=ajanborsa
WorkingDirectory=/opt/ajan-borsasi/app
EnvironmentFile=/opt/ajan-borsasi/app.env
ExecStart=/opt/ajan-borsasi/app/.venv/bin/uvicorn x402_servis:app --port 8000
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable --now ajan-borsasi
curl -fsS localhost:8000/healthz
```

**Canlılık-kontrolü:** `GET /healthz` 200 döner. **Ödeme-kontrolü:** ücretsiz
uçlar ( `/ozet`, `/pazar`) her zaman 200; ücretli uçlar ödeme-başarısızsa 402.

**Dürüst-sınır:** bu yapılandırma **gerçek-mainnet'te çalıştırılmadı** —
0 müşteri, 0 canlı-işlem. `UNPUMP_TEST=1` olmadan koşulursa
`mainnet_guard.py` zincirde transfer arar; bulamazsa 402 verir ( fail-closed).

## CLI ( günlük-operasyon )

```bash
# canlı sağlık
curl -fsS localhost:8000/healthz

# pazar-özeti ( ücretsiz uç )
curl -fsS localhost:8000/ozet | python3 -m json.tool

# zincir-ödeme-doğrulama ( mainnet-transfer-ara )
python3 mainnet_verify.py

# tam test-suiti
python3 -m pytest tests/ -q    # 861 passed rc=0 ( sester sys.path otomatik)
```

**Kanal listesi ( hepsi çalışır):**

| Eser | Komut | Durum |
|---|---|---|
| Servis | `uvicorn x402_servis:app` | ✅ 31 rota |
| Test | `python3 -m pytest tests/` | ✅ 861 rc=0 |
| Zincir-doğrulama | `python3 mainnet_verify.py` | ✅ PYTHONPATH gerekli |
| Canlılık | `curl /healthz` | ✅ 200 |


Bu, mesh'in ödeme omurgasıdır: Sester makbuzlarının `sha256(ts|event)`
kanıtı, **TamgaProtocol**'ün D5 defteriyle aynı hash-zincir modelini
paylaşır — yani bir Unpump ticareti, doğrulanabilir bir kanıt olarak
Tamga denetim hattına girebilir. Ayrıca **Delilix** ve **Tenderix** aynı
ajan-teklif/kanıt desenini kullanır.

## Akademik zemin

Unpump'un üç katmanı — kanıt-çekirdeği (`kanit_cekirdegi.py`), ödeme hattı
(`x402_servis.py` + Sester) ve ajan pazarı (`borsa_core.py`) — literatürde
kurulan desenlere dayanır (her referans canlı doğrulanmıştır):

- **Agent Flight Recorder** (arXiv:2609.01931, Bindschaedler/Botha/
  Siebenbrunner, cs.CR, Eylül 2026, BCCA 2026) — ajan eylemlerini "structured,
  canonically serialized event" olarak yakalar; **hash chaining ve Merkle
  batching** ile tamper kanıtı üretir. Edit/delete/reorder/fork saldırılarını
  %100, sıfır false-positive ile tespit eder; epoch köklerini zincire
  anchoring yaparak önceden anlaşılan güvenilir-arabulucu olmadan bağımsız
  doğrulamaya izin verir. `kanit_cekirdegi.py`'nin birebir akrabası: kanonik
  serileştirme + SHA-256 hash-zinciri + `zinciri_dogrula`'nın store'a
  bağımlı olmayan bağımsız yeniden-hesaplaması aynı desendir. Aradaki
  fark: AFR Merkle batching + on-chain anchoring kullanır; Unpump'un lineer
  zinciri Sester makbuzlarının HMAC-zinciriyle kapanır (Merkle/anchoring
  Faz-1 için bir genişletme yönüdür).
- **Sovereign-by-Design** (arXiv:2602.05486, Esposito/Marchesi/Tonelli/
  Lenarduzzi, cs.SE, Şubat 2026) — dijital egemenliği birinci-sınıf mimari
  kalite olarak ele alan referans mimarisi; **"blockchain-based trust and
  auditability"**, self-sovereign kimlik ve veri yönetişimini birleştirir.
  Unpump'un ödeme/denetim hattının zemin mimarisi: güvenin tek bir
  facilitator'a emanet edilmeyip zincir-üstü denetlenebilir olması
  (`mainnet_guard.py`'nin fail-closed zincir-ödemesi, tek-kasa treasury).
  Aradaki fark: referans mimari tamken Unpump Faz-0'da yalnız trust +
  auditability yönünü kullanır; SSI/ERC-8004 kimlik katmanı Faz 1'dir.
- **CHRONOS** (arXiv:2605.23887, Chandra, cs.DB, Mayıs 2026) — evrimleşen
  **veri pazarları** için üç katmanlı mimari: temporal indeksleme,
  changepoint-koşullu **Shapley değerlemesi** ve EXP3-IX ile **DP bütçesi**
  altında çok-ajan koordinasyonu. `borsa_core.py`'nin pazar katmanının zemin
  deseni: paylaşılan bir pazarda çok-ajan koordinasyonu ve değer-transferi.
  Aradaki fark (dürüst): CHRONOS bir *veri* pazarıdır (Shapley fiyatlandırma
  + DP bütçesi); Unpump Faz-0'da naif fiyat-hedefi eşleştirmesi kullanır —
  Shapley/DP katmanı mevcut koda girmez, Faz-1 değerlendirme hattı için
  bir genişletme yönüdür.

Daha geniş kaynak listesi (ödeme-protokolü formal analizi, x402 güvenliği,
ERC-8004 ekosistemi, benimseme ölçümü) için aşağıdaki "Akademik Kaynaklar"
bölümüne bakın.

## Test Durumu (gerçek)

```bash
# tam suit — tests/ gerçek-dizin, sester conftest tarafından sys.path'e-eklenir
python3 -m pytest tests/ -q
# → 861 passed, 0 failed rc=0 ( 2026-10-13 LEED-ölçümü)
```

**Yapı:** `tests/` gerçek-bir-dizindir ( self-symlink-DEĞİL). Toplam **861 test**
tek-komutla doğru toplanır. `conftest.py`, kardeş-proje `sester`'i
( 63-Sester) `sys.path`'e-ekler; kurulu-değilse ilgili çapraz-testler
temiz-bir-atlamayla geçer, import-patlamasıyla-DEĞİL.

- `tests/test_borsa_core.py` — saf iş-mantığı; her test kendi geçici SQLite'ını
  kullanır, ağ/cüzdan/anahtar/`UNPUMP_TEST` olmadan çalışır.
- `tests/test_x402_servis.py` — uçtan-uca ödeme; `.venv` ( Sester ≥0.7) ve
  `UNPUMP_TEST=1` ister, yoksa 402/`SystemExit` ( fail-closed-by-design).
- `tests/test_mainnet_odeme_ve_eslestirme.py` — imza/doğrulama çapraz-testleri
  ( sester.schemes üzerinden monkeypatch).

**Dürüst-sınırlar:**
- 861 testin tamamı **saf in-memory**; dış-ağ veya zincir- işlem YOK.
- `UNPUMP_TEST=1` olmadan servis, ödeme-doğrulanmazsa 402 verir — bu
  üre-tasarımdır, hata-DEĞİL.
- Test sayısı 0 müşteri/0 canlı-işlem gerçeğini DEĞİŞTİRMEZ: kod-yolları
  çalışıyor, iş-algısı henüz kanıtlanmadı.

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
