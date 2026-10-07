# LEÇVE — Akademik zemin eki (2026-10-07): ödeme kanalları

> **README'ye eklenecek literatür ekidir.** Mevcut `README.md` içeriğine
> **dokunulmamıştır**; bu dosya `docs/` altında YENİ dosya olarak teslim
> edilmiştir (goal: doc bağlarını genişlet).
>
> **FP0:** aşağıdaki her alıntı `web_fetch` ile **HTTP-200 + tam başlık birebir
> eşleşmesi** ile doğrulanmıştır. Uydurma alıntı yoktur. Kanıt:
> [`orkestrasyon/docs/fp0_arxiv_manifest_2026-10-07.json`](../../00_TAMGA-MESH/orkestrasyon/docs/fp0_arxiv_manifest_2026-10-07.json).

---

## Akademik zemin — 2026-09-22..2026-10-07 penceresi (payment-channels)

Unpump'un x402 ödeme yolu, havuzlanmış likiditenin nasıl yönetileceği sorusunu
ortaya koyar; ödeme-kanalı literatürünün son penceresi bu soruya net bir çerçeve
veriyor:

- **Sluice: Global Invariant, Local Enforcement for Pooled Payment-Channel
  Liquidity** ([arXiv:2609.29975](https://arxiv.org/abs/2609.29975),
  Wu/Sun/Guo/Zhu/Chen, cs.CR, 24 Eyl 2026) — Lightning Network'te yönlendirme
  düğümleri likiditeyi kanallar arasında dağıtır; makale bunu **küresel
  değişmezlik (global invariant) + yerel zorunluluk (local enforcement)** olarak
  yeniden çerçeveleyerek her düğümün kendi kural setini küresel güvenliği
  bozmadan uygulamasını sağlar. Unpump'un x402 entegrasyonu aynı deseni takip
  eder: ödeme doğrulaması (`mainnet_guard.py`) **küresel** zincir kurallarına
  bakarken, harcama politikası **yerel** ve sahip-kilitlidir. **Fark:** Sluice
  bir ödeme-kanalı **ağını** yönetir (likidite denklemleri, yönlendirme);
  Unpump ödeme kanalı yönetmez — onun yerine bu "küresel/yerel" ayrımı,
  ajanın **harcanabilirlik kararı** ile **kanıtlanabilir ödeme** arasındaki
  sınıra uygulanır: ajan ne zaman ödeyeceğine yerelden karar verir, ama
  "ödendi" gerçeği küresel olarak doğrulanabilir (Sester makbuzu →
  `charge_receipt` → `verify_chain()` yeşil).

---

*Bu ek, `README.md`'nin akademik zemin bölümüne eklenmek üzere hazırlanmıştır.*
