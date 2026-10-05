"""Unpump · Ajan Havuzu — Delilix Kanıt-Çekirdeği (Python portu)

Mesh haritası: 'Unpump ajanına: AGENT_HAVUZU'nun kanıt-çekirdeğini kopyala
— Delilix'in kanıt formatını Unpump ajanlarına ekle.'

Kaynak model: 04_hukuk_sarti/83-Delilix/code/{store,dogrula}.mjs
(KAGIT §7.2-7.3 kanıt-sözleşmesi). Bu modül JS kodunu KOPYALAMAZ — aynı
kanıtı modelini Python'da yeniden yazar ve AYNI girdi için AYNI SHA-256
çıktısı üretir (kanonik-serileştirme sözleşmesi, aşağıda).

KANIT MODELİ (Delilix ile ortak):
  1. content_hash — sadece veri alanlarının kanonik serileştirmesi üzerinden
     SHA-256 → "sha256:<hex>". Zincir-meta (prev) HARİÇ: kurcalama zincire
     eklendikten sonra gizlenemez (S6 kabul, §11).
  2. id — "<agent_id>|<operation>|<UTC-gün>"; aynı ajan+işlem+gün tek kayıt
     (gün-başı idempotency şeması — Delilix site|product_id|gün ile aynı).
  3. zincir kaydı {id, h, prev}: ilk prev = GENESIS, her prev = önceki
     kaydın h'si → silme / değiştirme / araya-ekleme KIRIK raporu verir.
  4. dogrula — hash'leri BAŞTAN hesaplar; store'a bağımlı DEĞİL (dogrula.mjs'in
     store.mjs'ten bağımsız olmasıyla aynı ilke: üçüncü taraf bu modülü
     çalıştırmadan kendi koduyla doğrulayabilir).

ALAN EŞLEMESİ (Delilix fiyat-gözlemi → Unpump ajan-işlemi):
     site       → agent_id     (ajan cüzdan-adresi)
     product_id → operation    (listele / teklif / eslestir / tamamla)
     sell       → amount       (USD tutar)
     ref        → ref          (referans tutar — fiyat-hedefi vb.)
     ts         → ts           (ISO-8601, değişmedi)
     source     → source       (gözlem kaynağı)

KANONİK-SERİLEŞTİRME SÖZLEŞMESİ (JS ⇄ Python bire-bir):
  Node.js JSON.stringify ile AYNI bayt dizisi üretilmeli:
    * anahtar sırası korunur (AjanIslem.kanonik() sırayı sabitler —
      JS'deki {a,b,c} literalinin alan sırasını kilitlemesi gibi),
    * tam-sayılaşan float ondalıksız: 15.0 → "15" (Python "15.0" DEĞİL),
    * üslar sıfırsız + işaretli: 1e-7 → "1e-7" (Python "1e-07" DEĞİL),
      1e21 → "1e+21",
    * -0.0 → "0", NaN/Infinity → null,
    * UTF-8 korunur (ensure_ascii=False — "İĞÜŞÇÖ" olduğu gibi yazılır),

Sıfır bağımlılık (stdlib) — borsa_core.py'nin Faz-0 ilkesiyle uyumlu.
Kullanım:
  python kanit_cekirdegi.py <store.json> [islem-log.csv] [--json]
  çıkış-kodu: 0 = DOĞRULANDI · 1 = HATALI (dogrula.mjs ile aynı)
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

GENESIS = "GENESIS"
VERSION = "0.1.0"

# Kanonik alan sırası — JS'deki destructure sırasının Python karşılığı.
# content_hash bu sıraya göre hesaplanır; değişirse eski kanıtlar bozulur.
CANONICAL_ALANLAR: tuple[str, ...] = (
    "agent_id", "operation", "amount", "ref", "ts", "source",
)


# ------------------------------------------------- JS ⇄ Python serileştirme

def _norm_uslu(gosterim: str) -> str:
    """Python float repr üssünü JS Number::toString biçimine getir.

    repr(1e-7) == "1e-07" → JS "1e-7"; repr(1e21) == "1e+21" → JS "1e+21".
    Kurall: işaret korunur, üs rakamlarından öndeki sıfırlar atılır.
    """
    mantis, sep, us = gosterim.partition("e")
    if not sep:
        return gosterim
    isaret = ""
    if us[:1] in ("+", "-"):
        isaret, us = us[0], us[1:]
    us = us.lstrip("0") or "0"
    return f"{mantis}e{isaret}{us}"


def _js_sayi(x: float) -> str:
    """Bir float'ı Node.js ile AYNI biçimde yaz (kanıt sözleşmesi)."""
    if x != x or x in (float("inf"), float("-inf")):
        return "null"                       # JSON.stringify(NaN|Infinity) → null
    if x == 0:
        return "0"                          # -0 → "0" (JS ile aynı)
    if x == int(x):
        if abs(x) < 1e21:
            return str(int(x))              # 15.0 → "15"; JS üsluya 1e21'de geçer
        return _norm_uslu(repr(x))          # 1e21 → "1e+21"
    return _norm_uslu(repr(x))              # 1350.5 → "1350.5", 1e-7 → "1e-7"


def _js_dize(s: str) -> str:
    """JSON dize-kaçışı + tırnaklar — json.dumps(ensure_ascii=False) ile
    JS JSON.stringify aynı çıktıyı verir (kontrol karakterleri dahil)."""
    return json.dumps(s, ensure_ascii=False)


def js_stringify(deger: Any) -> str:
    """Node.js JSON.stringify ile bire-bir aynı metni üret.

    Bu fonksiyon kanıt-hash'lerinin JS ⇄ Python taşınabilirliğidir;
    değiştirilirse Delilix ile olan sözleşme kırılır.
    """
    return _stringify(deger)


def _stringify(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):                 # bool, int'in atası — ÖNCE ele al
        return "true" if v else "false"
    if isinstance(v, str):
        return _js_dize(v)
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return _js_sayi(v)
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(_stringify(x) for x in v) + "]"
    if isinstance(v, Mapping):
        parcalar = [f"{_js_dize(str(k))}:{_stringify(x)}" for k, x in v.items()]
        return "{" + ",".join(parcalar) + "}"
    return _js_dize(str(v))                 # bilinmeyen tip → dize (JS gibi)


# ------------------------------------------------------------------ model

def day_key(ts: str) -> str:
    """ISO-8601 zaman → UTC YYYY-MM-DD (Delilix dayKey ile aynı).

    Saat dilimsiz ts'ler UTC kabul edilir (JS new Date(…).getUTC* ile aynı).
    Geçersiz ts → ValueError (dogrulayıcı bunu 'gün-uyumsuz' raporlar).
    """
    gun, _ = _day_key_or_none(ts)
    if gun is None:
        raise ValueError(f"geçersiz ts: {ts!r}")
    return gun


def _day_key_or_none(ts: Any) -> tuple[str | None, bool]:
    """Başarısız-da-çok-değil yardımcı: (gün-anahtarı, geçerli-mi)."""
    if not isinstance(ts, str) or not ts.strip():
        return None, False
    try:
        d = datetime.fromisoformat(ts.strip().replace("Z", "+00:00"))
    except ValueError:
        return None, False
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    d = d.astimezone(timezone.utc)
    return f"{d.year:04d}-{d.month:02d}-{d.day:02d}", True


def content_hash(kayit: Mapping[str, Any]) -> str:
    """§7.2 kanonik serileştirme → SHA-256 (sadece veri alanları, prev HARİÇ).

    Gönderenin anahtar sırası korunur — AjanIslem.kanonik() sırayı sabitler
    (JS'de contentHash'in {site, product_id, …} destructure sırası gibi).
    """
    govde = js_stringify(kayit).encode("utf-8")
    return "sha256:" + hashlib.sha256(govde).hexdigest()


def islem_id(agent_id: str, operation: str, ts: str) -> str:
    """Delilix 'site|product_id|gün' şemasının Unpump karşılığı."""
    return f"{agent_id}|{operation}|{day_key(ts)}"


@dataclass
class AjanIslem:
    """Bir ajan işlemi — Delilix fiyat-gözleminin Unpump karşılığı.

    Aynı 6-alan kanonik şema; alan eşlemesi modül docstring'inde.
    """

    agent_id: str               # ajan cüzdan-adresi (Delilix: site)
    operation: str              # listele/teklif/eslestir/tamamla (product_id)
    amount: float | None        # USD tutar (sell)
    ref: float | None           # referans tutar — fiyat-hedefi vb. (ref)
    ts: str                     # ISO-8601 (ts)
    source: str                 # gözlem kaynağı (source)

    def kanonik(self) -> dict[str, Any]:
        """Kanonik sıralı sözlük — hash'in kararlılığı bununla sağlanır."""
        return {a: getattr(self, a) for a in CANONICAL_ALANLAR}

    def icerik_hash(self) -> str:
        """İçerik-hash'i (zincire damga olarak yazılır)."""
        return content_hash(self.kanonik())

    def kimlik(self) -> str:
        """İşlem kimliği — gün-başı idempotency anahtarı."""
        return islem_id(self.agent_id, self.operation, self.ts)


@dataclass
class ZincirKaydi:
    """Zincir kaydı: {id, h, prev} — Delilix chain entry ile aynı biçim."""

    id: str
    h: str
    prev: str


def utc_now_iso() -> str:
    """Şu-an ISO-8601 (JS new Date().toISOString() ile aynı biçim, ms)."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z")


# --------------------------------------------------------------- kanıt deposu

class KanitZinciri:
    """Tamga-zincirli kanıt deposu — Delilix PriceStore'un Python karşılığı.

    Dosya-depolu JSON ({series, chain}); üretimde DB'ye değişir, arayüz aynı.
    Yüklemede bütünlük doğrulanır — bozuk store ValueError fırlatır
    (PriceStore._load'un verifyChain çağrısı ile aynı fail-closed davranış).
    """

    def __init__(self, dosya_yolu: str | None = None) -> None:
        self.dosya_yolu = dosya_yolu
        self.series: dict[str, dict[str, Any]] = {}
        self.chain: list[ZincirKaydi] = []
        if dosya_yolu and Path(dosya_yolu).exists():
            self.yukle()

    # -- kalıcılık --

    @staticmethod
    def _kaydi_dict(e: Any) -> dict[str, Any]:
        if isinstance(e, ZincirKaydi):
            return asdict(e)
        return dict(e)

    def yukle(self) -> "KanitZinciri":
        """Store'u yükle VE doğrula — bozuksa ValueError (fail-closed)."""
        veri = json.loads(Path(self.dosya_yolu).read_text(encoding="utf-8"))
        sonuc = zinciri_dogrula(veri)
        if sonuc["hatalar"]:
            sorun = sonuc["hatalar"][0]
            raise ValueError(
                f"store bozuk (yüklenmedi): [{sorun['tur']}] {sorun['id']}: "
                f"{sorun['detay']}")
        self.series = dict(veri.get("series") or {})
        self.chain = [
            ZincirKaydi(**{k: e[k] for k in ("id", "h", "prev")})
            for e in (veri.get("chain") or [])
        ]
        return self

    def kaydet(self) -> None:
        """Store'u JSON olarak yaz (series + chain, Delilix formatı)."""
        if not self.dosya_yolu:
            raise ValueError("dosya_yolu yok — kaydetilemedi")
        yol = Path(self.dosya_yolu)
        yol.parent.mkdir(parents=True, exist_ok=True)
        veri = {
            "series": self.series,
            "chain": [asdict(e) for e in self.chain],
        }
        yol.write_text(
            json.dumps(veri, ensure_ascii=False, indent=2), encoding="utf-8")

    def to_dict(self) -> dict[str, Any]:
        """Bellekteki store'un Delilix-format sözlük hali (dogrula için)."""
        return {
            "series": dict(self.series),
            "chain": [asdict(e) for e in self.chain],
        }

    # -- işlem --

    def ekle(self, islem: AjanIslem, kaydet: bool = True) -> dict[str, Any]:
        """İşlemi kanıt-zincirine ekle (idempotent) + damga.

        Delilix addObservation ile aynı sözleşme:
          {"ok": True, "id": …, "tamga": {id,h,prev}}   → yeni kayıt
          {"ok": False, "neden": "gun-zaten-var", "id": …}  → aynı gün
        """
        kid = islem.kimlik()
        if kid in self.series:
            return {"ok": False, "neden": "gun-zaten-var", "id": kid}
        onceki = self.chain[-1].h if self.chain else GENESIS
        tamga = ZincirKaydi(id=kid, h=islem.icerik_hash(), prev=onceki)
        self.series[kid] = islem.kanonik()
        self.chain.append(tamga)
        if kaydet and self.dosya_yolu:
            self.kaydet()
        return {"ok": True, "id": kid, "tamga": asdict(tamga)}

    def dogrula(self) -> dict[str, Any]:
        """Zincir teyidi (store'a bağımsız yeniden hesaplama)."""
        sonuc = zinciri_dogrula(self.to_dict())
        return {
            "ok": not sonuc["hatalar"],
            "uzunluk": sonuc["uzunluk"],
            "son": sonuc["son"],
            **({"hatalar": sonuc["hatalar"]} if sonuc["hatalar"] else {}),
        }


# ------------------------------------------------------ bağımsız doğrulayıcı

def zinciri_dogrula(veri: Mapping[str, Any]) -> dict[str, Any]:
    """Store'u BAŞTAN doğrula: prev-bağları + içerik-hash'leri + gün-sırası.

    dogrula.mjs'in zinciriDogrula portu — hash'leri BURADA yeniden hesaplar,
    KanitZinciri'ne bağımlı DEĞİL (üçüncü-taraf denetimi).
    """
    hatalar: list[dict[str, str]] = []
    prev = GENESIS
    zincir = list(veri.get("chain") or [])
    for i, e in enumerate(zincir):
        if not isinstance(e, Mapping) or not isinstance(e.get("id"), str) \
                or not isinstance(e.get("h"), str):
            hatalar.append({
                "id": (e.get("id") if isinstance(e, Mapping) else f"#{i}"),
                "tur": "yapı",
                "detay": "kayıt alanları eksik (id/h yok)",
            })
            continue
        if e.get("prev") != prev:
            hatalar.append({
                "id": e["id"],
                "tur": "prev-kırık",
                "detay": (f"beklenen {str(prev)[:16]}…, "
                          f"kayıtta {str(e.get('prev'))[:16]}…"),
            })
        og = (veri.get("series") or {}).get(e["id"])
        if og is None:
            hatalar.append({
                "id": e["id"], "tur": "kayit-yok",
                "detay": "series'te karşılığı yok",
            })
            prev = e["h"]
            continue
        hesap = content_hash(og)
        if hesap != e["h"]:
            hatalar.append({
                "id": e["id"],
                "tur": "kurcalama",
                "detay": (f"kayıt-içeriği değiştirilmiş "
                          f"(h={str(e['h'])[:16]}…, hesap={hesap[:16]}…)"),
            })
        gun, gecerli = _day_key_or_none(og.get("ts"))
        if not gecerli or not e["id"].endswith("|" + gun):
            hatalar.append({
                "id": e["id"],
                "tur": "gün-uyumsuz",
                "detay": f"id-günü ≠ ts-günü ({gun})",
            })
        prev = e["h"]
    return {
        "uzunluk": len(zincir),
        "son": zincir[-1]["h"] if zincir else None,
        "hatalar": hatalar,
        "seriesAdet": len(veri.get("series") or {}),
    }


def _yaklasik_esit(a: Any, b: Any) -> bool:
    """Delilix'in esit() yardımcısı — null-karşılaştırma + 1e-9 tolerans."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) < 1e-9


def csv_caprazla(store_yolu: str, csv_yolu: str) -> dict[str, Any]:
    """CSV ↔ store çapraz-doğrulama: her satır zincirli seride bire-bit bulunmalı.

    dogrula.mjs'in csvCaprazla portu. Unpump sütunları:
    agent_id, operation, amount, ts (zorunlu) · ref (opsiyonel) · source.
    """
    veri = json.loads(Path(store_yolu).read_text(encoding="utf-8"))
    eslesen, eksik, uyusmayan = [], [], []
    with open(csv_yolu, newline="", encoding="utf-8") as f:
        okuyucu = csv.DictReader(f)
        for satir_no, satir in enumerate(okuyucu, start=2):
            agent_id = (satir.get("agent_id") or "").strip()
            operation = (satir.get("operation") or "").strip()
            ts = (satir.get("ts") or "").strip()
            amount_ham = (satir.get("amount") or "").strip()
            ref_ham = (satir.get("ref") or "").strip()
            gun, gecerli = _day_key_or_none(ts)
            try:
                amount = float(amount_ham)
            except ValueError:
                amount = None
            if not agent_id or not operation or amount is None or not gecerli:
                uyusmayan.append({
                    "satir": satir_no,
                    "id": f"{agent_id or '?'}|{operation or '?'}|{gun or '?'}",
                    "alan": "geçersiz-alan",
                    "beklenen": "agent_id,operation,amount,ts",
                    "bulunan": ",".join(f"{k}={v}" for k, v in satir.items()
                                        if k in ("agent_id", "operation",
                                                 "amount", "ts"))[:60],
                })
                continue
            kid = f"{agent_id}|{operation}|{gun}"
            og = (veri.get("series") or {}).get(kid)
            if og is None:
                eksik.append(kid)
                continue
            ref_csv: float | None
            try:
                ref_csv = float(ref_ham) if ref_ham else None
            except ValueError:
                ref_csv = None
            if not _yaklasik_esit(og.get("amount"), amount):
                uyusmayan.append({
                    "satir": satir_no, "id": kid, "alan": "amount",
                    "beklenen": og.get("amount"), "bulunan": amount,
                })
            elif not _yaklasik_esit(og.get("ref"), ref_csv):
                uyusmayan.append({
                    "satir": satir_no, "id": kid, "alan": "ref",
                    "beklenen": og.get("ref"), "bulunan": ref_csv,
                })
            else:
                eslesen.append(kid)
    return {
        "satir": len(eslesen) + len(eksik) + len(uyusmayan),
        "eslesen": eslesen,
        "eksik": eksik,
        "uyusmayan": uyusmayan,
    }


def dogrula(store_yolu: str, csv_yolu: str | None = None) -> dict[str, Any]:
    """Tam denetim: zincir + (verilirse) CSV. sonuc = DOĞRULANDI | HATALI."""
    zincir = zinciri_dogrula(
        json.loads(Path(store_yolu).read_text(encoding="utf-8")))
    csv_sonuc = csv_caprazla(store_yolu, csv_yolu) if csv_yolu else None
    toplam_hata = len(zincir["hatalar"]) + (
        len(csv_sonuc["eksik"]) + len(csv_sonuc["uyusmayan"])
        if csv_sonuc else 0)
    return {
        "store": store_yolu,
        "csv": csv_yolu,
        "zincir": zincir,
        "csvSonuc": csv_sonuc,
        "sonuc": "DOĞRULANDI" if toplam_hata == 0 else "HATALI",
    }


# --------------------------------------------------- borsa_core bütünleşmesi

def match_kanit_islemi(
    match: Any,
    *,
    ts: str | None = None,
    source: str = "unpump-borsa",
    operation: str = "tamamla",
    ref: float | None = None,
) -> AjanIslem:
    """borsa_core.Match'i kanıt-işlemine çevir — ⭐⭐⭐ iş-tamamlandı kanıtı.

    Bir Match ancak complete_work() ile receipt_hash bağlandığında kapanır;
    bu fonksiyon o kapanışın SHA-256 zincir-kanıtıdır (machine-checkable).

    İÇİNDE DEĞİL: Match veri sınıfına import bağımlılığı YOK — duck-typing
    (agent_id / amount / receipt_hash). Delilix'te dogrula.mjs'in store.mjs'e
    bağımlı olmaması gibi: kanıt, kanıtlanan koddan ayrı doğrulanabilir.
    """
    eksik = [a for a in ("agent_id", "amount") if not hasattr(match, a)]
    if eksik:
        raise TypeError(
            f"match benzemiyor — eksik alanlar: {', '.join(eksik)}")
    return AjanIslem(
        agent_id=str(getattr(match, "agent_id")),
        operation=operation,
        amount=float(getattr(match, "amount")),
        ref=ref,
        ts=ts or utc_now_iso(),
        source=source,
    )


# -------------------------------------------------------------------- CLI

def _cli(argv: Sequence[str]) -> int:
    """Bağımsız doğrulayıcı CLI (dogrula.mjs ile aynı sözleşme)."""
    arglar = [a for a in argv[1:] if not a.startswith("--")]
    json_bayrak = "--json" in argv[1:]
    if not arglar:
        sys.stderr.write(
            "kullanım: python kanit_cekirdegi.py <store.json> "
            "[islem-log.csv] [--json]\n")
        return 1
    store_yolu = arglar[0]
    csv_yolu = arglar[1] if len(arglar) > 1 else None
    try:
        r = dogrula(store_yolu, csv_yolu)
    except Exception as e:                       # noqa: BLE001 — CLI yakalar
        sys.stderr.write(f"doğrulama-yürütülemedi: {e}\n")
        return 1
    if json_bayrak:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        z = r["zincir"]
        print("── Bağımsız doğrulama ──")
        print(f"store: {r['store']} · zincir: {z['uzunluk']} kayıt "
              f"· series: {z['seriesAdet']}")
        print(f"son-tamga: {z['son'] or '—'}")
        for h in z["hatalar"]:
            print(f"  ❌ [{h['tur']}] {h['id']}: {h['detay']}")
        if r["csvSonuc"]:
            c = r["csvSonuc"]
            print(f"csv: {r['csv']} · {c['satir']} satır · "
                  f"{len(c['eslesen'])} eşleşti · {len(c['eksik'])} eksik · "
                  f"{len(c['uyusmayan'])} uyumsuz")
            for e in c["eksik"]:
                print(f"  ❌ store'da yok: {e}")
            for u in c["uyusmayan"]:
                print(f"  ❌ satır {u['satir']} {u['id']} [{u['alan']}]: "
                      f"beklenen={u['beklenen']} bulunan={u['bulunan']}")
        if r["sonuc"] == "DOĞRULANDI":
            print("✅ DOĞRULANDI — zincir ve CSV bütünlüğü bağımsız "
                  "teyit edildi")
        else:
            print("🚨 HATALI — yukarıdaki bulgulara bak")
    return 0 if r["sonuc"] == "DOĞRULANDI" else 1


if __name__ == "__main__":                       # pragma: no cover
    sys.exit(_cli(sys.argv))
