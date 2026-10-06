"""Mainnet ödeme-doğrulama + matching-engine güvenlik testleri.

Bu dosya MEVCUT testlerin kapsamadığı, güvenlik/finans/ödeme/settlement
açısından EN KRİTİK 4 hedefi dal-kesen (laser-cut) şekilde test eder:

  1. mainnet_verify.find_transfer        (69L) — zincir-üstü USDC transfer
     arama = **settlement** çekirdeği (parçalı arama, limit-retry, eşleşme)
  2. mainnet_verify.verify_mainnet_payment (11L) — USD → minor (6 decimal)
     dönüşümü + settlement giriş noktası
  3. mainnet_guard.require_mainnet_payment (97L) — fail-closed ödeme kapısı
     (402/500/503), sandbox whitelist, X-Payer-Address sahiplenme saldırısı
  4. mainnet_guard.resolve_treasury (32L) / is_sandbox_payer — tek-kasa
     kuralı + sandbox whitelist (finans/konfigürasyon)

EK: borsa_core.match_bid — **matching engine**'in listeleme-durumu
guard'ları (suspended/delisted ajanın teklifi eşleşemez — pazarın dışından
eşleşme güvenliği).

İZOLASYON KURALLARI:
  - Hiçbir test gerçek RPC'ye gitmez (_rpc mock'lanır — kural 7).
  - Hiçbir test mevcut kodu/DB'yi değiştirmez; hepsi tmp_path + monkeypatch.
  - mainnet_verify.find_transfer kök conftest.py'de bir stub ile değiştirilmiş
    olabilir; bu yüzden find_transfer'in GERÇEK mantığını test etmek için
    modülün PRISTINE bir kopyası unique isimle yüklenir (paylaşılan modüle
    dokunulmaz, böylece test_x402_servis.py'nin stub'ı bozulmaz).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent

# --- pristine mainnet_verify kopyası (conftest stub'ından etkilenmez) --------
# sys.modules'e KAYDETMEK ZORUNLU: modüldeki @dataclass, __module__ üzerinden
# sys.modules'e bakar; kayıtlı değilse AttributeError verir.
_MV_NAME = "_mv_pristine_mainnet_verify"
_spec = importlib.util.spec_from_file_location(_MV_NAME, ROOT / "mainnet_verify.py")
_mv = importlib.util.module_from_spec(_spec)
sys.modules[_MV_NAME] = _mv
_spec.loader.exec_module(_mv)

import mainnet_guard  # noqa: E402
import mainnet_verify  # noqa: E402
from borsa_core import list_agent, match_bid, place_bid  # noqa: E402


# --------------------------------------------------------------- yardımcılar

def _hex_block(n: int) -> str:
    return hex(n)


def _log(block: int, value_minor: int, frm: str, to: str, tx="0xabc") -> dict:
    """USDC Transfer event log'u (data = 32-byte little-endian value)."""
    return {
        "blockNumber": _hex_block(block),
        "transactionHash": tx,
        "data": "0x" + format(value_minor, "064x"),
        "topics": ["0xddf2", "0x" + frm[2:].lower().rjust(64, "0"),
                   "0x" + to[2:].lower().rjust(64, "0")],
    }


class _FakeRPC:
    """mainnet_verify._rpc yerine — blok numarası + blok-aralığı logları.

    Hiçbir ağ çağrısı yapmaz; sadece fonksiyonun kendi mantığını test eder.
    fail_range(from, to) → True ise RPCError(error) fırlatır (limit-asımı
    senaryoları için); böylece test chunk aritmetiğine gömülmez.
    """

    def __init__(self, latest: int, logs=(), fail_range=None, error=""):
        self.latest = latest
        self.logs = list(logs)
        self.fail_range = fail_range
        self.error = error
        self.calls: list[tuple[str, list]] = []

    def __call__(self, method: str, params: list):
        self.calls.append((method, params))
        if method == "eth_blockNumber":
            return _hex_block(self.latest)
        if method == "eth_getLogs":
            f = int(params[0]["fromBlock"], 16)
            t = int(params[0]["toBlock"], 16)
            if self.fail_range is not None and self.fail_range(f, t):
                raise _mv.RPCError(self.error)
            return [lg for lg in self.logs
                    if f <= int(lg["blockNumber"], 16) <= t]
        raise AssertionError(f"beklenmeyen RPC method: {method}")


class _FakeRequest:
    """Starlette Request'ın kullanılan yüzeyi: headers / url.path / state."""

    def __init__(self, headers: dict, path: str = "/ucretli"):
        self.headers = headers
        self.url = SimpleNamespace(path=path)
        self.state = SimpleNamespace()


PAYER = "0x" + "11" * 20
PAY_TO = "0x" + "22" * 20
GOOD_HEADERS = {"x-payer-address": PAYER}


def _hata_at(mesaj: str):
    """verify_mainnet_payment yerine — çağrılırsa test patlamalı (zincir aranmamış)."""
    def _boom(**kw):
        raise AssertionError(mesaj)
    return _boom


# ================================================ [1] find_transfer — SETTLEMENT

class TestFindTransfer:
    """Zincir-üstü USDC transfer arama — ödemenin 'gerçekten oldu' kanıtı."""

    def test_eslesen_transfer_bulunur(self, monkeypatch):
        """Eşleşen from+to+tutar → TransferFound(True) + tx_hash + blok."""
        rpc = _FakeRPC(latest=10_000, logs=[
            _log(9975, 1_000_000, PAYER, PAY_TO, tx="0xdeadbeef"),
        ])
        monkeypatch.setattr(_mv, "_rpc", rpc)

        sonuc = _mv.find_transfer(
            from_addr=PAYER, to_addr=PAY_TO, amount_minor=1_000_000)

        assert sonuc.found is True
        assert sonuc.tx_hash == "0xdeadbeef"
        assert sonuc.amount_minor == 1_000_000
        assert "9975" in sonuc.detail
        # CONFIRMED_BLOCKS=20 → arama latest-20'den başlar, latest'i dahil etmez
        blocks = rpc.calls[1][1][0]
        assert int(blocks["toBlock"], 16) == 10_000 - 20

    def test_tutar_uyusmazsa_bulunamaz(self, monkeypatch):
        """Doğru adres ama yanlış tutar → found=False, detaylı sebep."""
        rpc = _FakeRPC(latest=10_000, logs=[
            _log(9990, 999_999, PAYER, PAY_TO),   # yanlış tutar
        ])
        monkeypatch.setattr(_mv, "_rpc", rpc)

        sonuc = _mv.find_transfer(
            from_addr=PAYER, to_addr=PAY_TO, amount_minor=1_000_000)

        assert sonuc.found is False
        assert sonuc.tx_hash is None
        assert str(1_000_000) in sonuc.detail

    def test_eslesmeyen_adres_bulunamaz(self, monkeypatch):
        """Başka bir gönderenden gelen transfer eşleşmez."""
        other = "0x" + "33" * 20
        rpc = _FakeRPC(latest=10_000, logs=[
            _log(9990, 1_000_000, other, PAY_TO),
        ])
        monkeypatch.setattr(_mv, "_rpc", rpc)

        sonuc = _mv.find_transfer(
            from_addr=PAYER, to_addr=PAY_TO, amount_minor=1_000_000)

        assert sonuc.found is False

    def test_parcali_arama_ileriki_chunkta_bulur(self, monkeypatch):
        """2000-block chunk'lar halinde geriye tarar — 3. chunk'ta bulunur."""
        logs = [_log(10_000 - 20 - 4000, 500_000, PAYER, PAY_TO, tx="0xchunk3")]
        rpc = _FakeRPC(latest=10_000, logs=logs)
        monkeypatch.setattr(_mv, "_rpc", rpc)

        sonuc = _mv.find_transfer(
            from_addr=PAYER, to_addr=PAY_TO, amount_minor=500_000,
            max_blocks=10_000)

        assert sonuc.found is True
        assert sonuc.tx_hash == "0xchunk3"
        # eth_blockNumber + en az 3 eth_getLogs chunk'ı yapıldı
        methods = [c[0] for c in rpc.calls]
        assert methods.count("eth_getLogs") >= 3
        # her chunk 2000 bloğu aşmaz (CHUNK_BLOCKS)
        for _, params in rpc.calls[1:]:
            f = int(params[0]["fromBlock"], 16)
            t = int(params[0]["toBlock"], 16)
            assert t - f + 1 <= 2000

    def test_limit_asimi_halinde_chunk_daraltilir(self, monkeypatch):
        """RPC 'max results' hatası → chunk 200 bloğa daraltılıp retry."""
        rpc = _FakeRPC(
            latest=10_000,
            logs=[_log(9975, 250_000, PAYER, PAY_TO, tx="0xnarrow")],
            # geniş chunk'larda limit-asımı hatası, dar retry'da yok
            fail_range=lambda f, t: t - f + 1 > 1000,
            error="query exceeded max results (10000 limit)",
        )
        monkeypatch.setattr(_mv, "_rpc", rpc)

        sonuc = _mv.find_transfer(
            from_addr=PAYER, to_addr=PAY_TO, amount_minor=250_000)

        assert sonuc.found is True
        assert sonuc.tx_hash == "0xnarrow"
        # retry chunk'ı tam 201 blok (hi-200 .. hi)
        son = [p for m, p in rpc.calls if m == "eth_getLogs"][-1]
        f, t = int(son[0]["fromBlock"], 16), int(son[0]["toBlock"], 16)
        assert t - f == 200

    def test_limit_asimi_alt_siniri_asarsa_bulunamaz(self, monkeypatch):
        """Daraltma lo'nun altına düşerse found=False döner (hata detayı)."""
        rpc = _FakeRPC(
            latest=210,            # hi=190, lo=0 → daraltma 190-200 = -10 < lo
            fail_range=lambda f, t: True,
            error="max results exceeded",
        )
        monkeypatch.setattr(_mv, "_rpc", rpc)

        sonuc = _mv.find_transfer(
            from_addr=PAYER, to_addr=PAY_TO, amount_minor=1, max_blocks=210)

        assert sonuc.found is False
        assert "max results" in sonuc.detail

    def test_genel_rpc_hatasi_fail_closed_yayilir(self, monkeypatch):
        """Limit-dışı RPC hatası susturulmaz — fail-closed olarak yayılır."""
        def boom(method, params):
            raise _mv.RPCError("connection refused")

        monkeypatch.setattr(_mv, "_rpc", boom)

        with pytest.raises(_mv.RPCError, match="connection refused"):
            _mv.find_transfer(
                from_addr=PAYER, to_addr=PAY_TO, amount_minor=1)

    def test_max_blocks_arama_penceresini_sinirlar(self, monkeypatch):
        """max_blocks, lo alt sınırını belirler — daha eski log aranmaz."""
        # eski log arama penceresinin dışında
        rpc = _FakeRPC(latest=10_000, logs=[
            _log(10_000 - 20 - 600, 750_000, PAYER, PAY_TO),
        ])
        monkeypatch.setattr(_mv, "_rpc", rpc)

        sonuc = _mv.find_transfer(
            from_addr=PAYER, to_addr=PAY_TO, amount_minor=750_000,
            max_blocks=500)

        assert sonuc.found is False
        for _, params in rpc.calls[1:]:
            lo = int(params[0]["fromBlock"], 16)
            assert lo >= 10_000 - 500


# ======================================= [2] verify_mainnet_payment — GİRİŞ NOKTASI

class TestVerifyMainnetPayment:
    """USD → on-chain minor dönüşümü ve find_transfer'e delegasyon."""

    def test_usd_minor_donusturur_ve_delege_eder(self, monkeypatch):
        captured = {}

        def fake_find(**kw):
            captured.update(kw)
            return _mv.TransferFound(True, tx_hash="0xtx")

        monkeypatch.setattr(_mv, "find_transfer", fake_find)

        sonuc = _mv.verify_mainnet_payment(
            from_addr=PAYER, to_addr=PAY_TO, amount_usd=2.5)

        assert sonuc.found is True
        assert captured["amount_minor"] == 2_500_000   # 6 decimal
        assert captured["from_addr"] == PAYER
        assert captured["to_addr"] == PAY_TO

    def test_usd_kurus_yuvarlamasi_minor_tamsayi_yapar(self, monkeypatch):
        seen = []
        monkeypatch.setattr(
            _mv, "find_transfer",
            lambda **kw: seen.append(kw) or _mv.TransferFound(False))

        _mv.verify_mainnet_payment(
            from_addr=PAYER, to_addr=PAY_TO, amount_usd=0.015)

        # 0.015 * 1e6 = 15000.0 → tamsayı minor
        assert seen[0]["amount_minor"] == 15_000


# ==================================== [3] require_mainnet_payment — ÖDEME KAPISI

class TestRequireMainnetPayment:
    """Fail-closed ödeme kapısı — 402/500/503 + sandbox + sahiplenme saldırısı."""

    @pytest.fixture(autouse=True)
    def _mainnet_modu(self, monkeypatch):
        """Her testte test-modu kapat + MAINNET açık (zincir arama aktif)."""
        monkeypatch.setenv("UNPUMP_TEST", "0")
        monkeypatch.setenv("SVC_MAINNET", "1")
        monkeypatch.delenv("UNPUMP_SANDBOX_KEYS", raising=False)

    def test_test_modunda_zincir_aranmaz(self, monkeypatch):
        monkeypatch.setenv("UNPUMP_TEST", "1")
        monkeypatch.setattr(mainnet_verify, "verify_mainnet_payment",
                            _hata_at("zincir aranmamalı"))

        assert mainnet_guard.require_mainnet_payment(
            _FakeRequest({}), price=1.0, pay_to=PAY_TO,
            service_name="svc") is None

    def test_mainnet_flag_kapaliysa_zincir_aranmaz(self, monkeypatch):
        monkeypatch.setenv("SVC_MAINNET", "0")
        monkeypatch.setattr(mainnet_verify, "verify_mainnet_payment",
                            _hata_at("zincir aranmamalı"))

        assert mainnet_guard.require_mainnet_payment(
            _FakeRequest( GOOD_HEADERS), price=1.0, pay_to=PAY_TO,
            service_name="svc") is None

    def test_pay_to_bos_500(self):
        with pytest.raises(Exception) as ei:
            mainnet_guard.require_mainnet_payment(
                _FakeRequest(GOOD_HEADERS), price=1.0, pay_to="",
                service_name="svc")
        assert getattr(ei.value, "status_code", None) == 500

    def test_payer_header_yoksa_402(self):
        with pytest.raises(Exception) as ei:
            mainnet_guard.require_mainnet_payment(
                _FakeRequest({}), price=1.0, pay_to=PAY_TO, service_name="svc")
        assert getattr(ei.value, "status_code", None) == 402

    def test_payer_header_format_disi_402(self):
        with pytest.raises(Exception) as ei:
            mainnet_guard.require_mainnet_payment(
                _FakeRequest({"x-payer-address": "0x123"}),
                price=1.0, pay_to=PAY_TO, service_name="svc")
        assert getattr(ei.value, "status_code", None) == 402

    def test_odeme_bulununca_payer_doner(self, monkeypatch):
        monkeypatch.setattr(
            mainnet_verify, "verify_mainnet_payment",
            lambda **kw: _mv.TransferFound(True, tx_hash="0xok"))

        payer = mainnet_guard.require_mainnet_payment(
            _FakeRequest(GOOD_HEADERS), price=1.0, pay_to=PAY_TO,
            service_name="svc")

        assert payer == PAYER

    def test_odeme_bulunamazsa_402(self, monkeypatch):
        monkeypatch.setattr(
            mainnet_verify, "verify_mainnet_payment",
            lambda **kw: _mv.TransferFound(False, detail="yok"))

        with pytest.raises(Exception) as ei:
            mainnet_guard.require_mainnet_payment(
                _FakeRequest(GOOD_HEADERS), price=1.0, pay_to=PAY_TO,
                service_name="svc")
        exc = ei.value
        assert getattr(exc, "status_code", None) == 402
        assert exc.detail["error"] == "payment_required"
        assert "base-mainnet" in str(exc.detail)

    def test_rpc_hatasi_fail_closed_503(self, monkeypatch):
        def boom(**kw):
            raise RuntimeError("RPC timeout")

        monkeypatch.setattr(mainnet_verify, "verify_mainnet_payment", boom)

        with pytest.raises(Exception) as ei:
            mainnet_guard.require_mainnet_payment(
                _FakeRequest(GOOD_HEADERS), price=1.0, pay_to=PAY_TO,
                service_name="svc")
        exc = ei.value
        assert getattr(exc, "status_code", None) == 503
        assert "fail-closed" in exc.detail

    def test_sandbox_whitelist_zinciri_atlar_ve_isaretler(self, monkeypatch):
        monkeypatch.setenv("UNPUMP_SANDBOX_KEYS", PAYER + ", 0xOTHER")
        monkeypatch.setattr(mainnet_verify, "verify_mainnet_payment",
                            _hata_at("sandbox adresi için zincir aranmamalı"))

        req = _FakeRequest(GOOD_HEADERS)
        payer = mainnet_guard.require_mainnet_payment(
            req, price=1.0, pay_to=PAY_TO, service_name="svc")

        assert payer == PAYER
        assert req.state.sandbox is True

    def test_sandbox_whitelist_disinda_zincir_arar(self, monkeypatch):
        monkeypatch.setenv("UNPUMP_SANDBOX_KEYS", "0x" + "99" * 20)
        called = {}
        monkeypatch.setattr(
            mainnet_verify, "verify_mainnet_payment",
            lambda **kw: called.update(kw) or _mv.TransferFound(True))

        mainnet_guard.require_mainnet_payment(
            _FakeRequest(GOOD_HEADERS), price=3.0, pay_to=PAY_TO,
            service_name="svc")

        assert called["from_addr"] == PAYER

    def test_sandbox_global_flag_kapaliysa_whitelist_islemez(self, monkeypatch):
        monkeypatch.setenv("UNPUMP_SANDBOX", "0")
        monkeypatch.setenv("UNPUMP_SANDBOX_KEYS", PAYER)
        called = {}
        monkeypatch.setattr(
            mainnet_verify, "verify_mainnet_payment",
            lambda **kw: called.update(kw) or _mv.TransferFound(True))

        mainnet_guard.require_mainnet_payment(
            _FakeRequest(GOOD_HEADERS), price=1.0, pay_to=PAY_TO,
            service_name="svc")

        assert called == {"from_addr": PAYER, "to_addr": PAY_TO,
                          "amount_usd": 1.0}

    def test_payer_imza_kaynagi_uyusmazsa_402(self, monkeypatch):
        """X-Payer-Address, X-Payment imzasından çıkmıyorsa sahiplenme → 402."""
        import sester.schemes  # modülü gerçek submodule yapıyoruz
        monkeypatch.setattr(
            sester.schemes, "verify_exact_sester",
            lambda payload, kaynak: {"agent": "0x" + "ff" * 20},
            raising=False)

        with pytest.raises(Exception) as ei:
            mainnet_guard.require_mainnet_payment(
                _FakeRequest({**GOOD_HEADERS, "x-payment": "sig"}),
                price=1.0, pay_to=PAY_TO, service_name="svc")
        exc = ei.value
        assert getattr(exc, "status_code", None) == 402
        assert exc.detail["error"] == "payer_mismatch"

    def test_imza_dogrulanamazsa_fail_closed_zincire_gider(self, monkeypatch):
        """verify_exact_sester exception → kanıt yok → zincir aramaya devam."""
        import sester.schemes

        def bad_sig(payload, kaynak):
            raise ValueError("gecersiz imza")

        monkeypatch.setattr(
            sester.schemes, "verify_exact_sester", bad_sig, raising=False)
        got = {}
        monkeypatch.setattr(
            mainnet_verify, "verify_mainnet_payment",
            lambda **kw: got.update(kw) or _mv.TransferFound(True))

        payer = mainnet_guard.require_mainnet_payment(
            _FakeRequest({**GOOD_HEADERS, "x-payment": "bad-sig"}),
            price=1.0, pay_to=PAY_TO, service_name="svc")

        assert payer == PAYER   # fail-closed: imza yok → zincir ile doğrula


# ============================= [4] resolve_treasury / is_sandbox_payer — FİNANS

class TestResolveTreasury:
    """Tek-kasa kuralı — ödemenin yanlış adrese gitme riskini sıfırlar."""

    def test_gecerli_treasury_doner(self, monkeypatch):
        addr = "0x" + "ab" * 20
        monkeypatch.setenv("UNPUMP_TREASURY_EOA", addr)
        assert mainnet_guard.resolve_treasury("svc") == addr

    def test_gectarssiz_treasury_fail_closed_systemexit(self, monkeypatch):
        monkeypatch.setenv("UNPUMP_TREASURY_EOA", "0x123")
        with pytest.raises(SystemExit, match="treasury-invalid"):
            mainnet_guard.resolve_treasury("svc")

    def test_legacy_pay_to_geri_uyum(self, monkeypatch):
        monkeypatch.delenv("UNPUMP_TREASURY_EOA", raising=False)
        legacy = "0x" + "cd" * 20
        monkeypatch.setenv("SVC_MAINNET_PAY_TO", legacy)
        assert mainnet_guard.resolve_treasury("svc") == legacy

    def test_iki_deger_bossa_systemexit(self, monkeypatch):
        monkeypatch.delenv("UNPUMP_TREASURY_EOA", raising=False)
        monkeypatch.delenv("SVC_MAINNET_PAY_TO", raising=False)
        with pytest.raises(SystemExit, match="treasury-required"):
            mainnet_guard.resolve_treasury("svc")

    def test_legacy_gectersiz_systemexit(self, monkeypatch):
        monkeypatch.delenv("UNPUMP_TREASURY_EOA", raising=False)
        monkeypatch.setenv("SVC_MAINNET_PAY_TO", "0xzzz")
        with pytest.raises(SystemExit, match="MAINNET_PAY_TO"):
            mainnet_guard.resolve_treasury("svc")


class TestSandboxPayer:
    """Sandbox whitelist — demo/test anahtarlarının zincir-dışı erişimi."""

    def test_whitelist_addr_eslesir(self, monkeypatch):
        monkeypatch.setenv("UNPUMP_SANDBOX_KEYS", f"{PAYER},0xOther")
        assert mainnet_guard.is_sandbox_payer(PAYER) is True
        assert mainnet_guard.is_sandbox_payer("0x" + "44" * 20) is False

    def test_bos_whitelist_hicbir_adres_gecerli_degil(self, monkeypatch):
        monkeypatch.delenv("UNPUMP_SANDBOX_KEYS", raising=False)
        assert mainnet_guard.is_sandbox_payer(PAYER) is False


# ================================ [EK] match_bid — MATCHING ENGINE GUARD'LARI

class TestMatchBidListelemeGuardi:
    """Askıya alınmış / listeden çıkarılmış ajanın teklifi eşleşemez.

    Bu bir pazar-güvenliği invariant'ı: fiyat-hedefini karşılasa bile,
    durumu 'listed' olmayan bir ajan için matching engine devreye girmez.
    """

    @pytest.fixture()
    def db(self, tmp_path: Path) -> str:
        return str(tmp_path / "borsa.sqlite")

    def test_askiya_alinmis_ajan_eslesmez(self, db: str):
        list_agent("agent-1", "isim", "randevu", 10.0, "kanit", db=db)
        # listing'i doğrudan pazar-dışı durumuna getir (mevcut API dışı,
        # DB seviyesi — yalnızca okuma amaçlı bir UPDATE ile)
        import sqlite3
        con = sqlite3.connect(db)
        con.execute("UPDATE listings SET status='suspended' WHERE agent_id=?",
                    ("agent-1",))
        con.commit()
        con.close()

        bid = place_bid("agent-1", "buyer-1", 50.0, "{}", "n-1", db=db)
        assert match_bid(bid.bid_id, db=db) is None

    def test_delisted_ajan_eslesmez(self, db: str):
        list_agent("agent-1", "isim", "randevu", 10.0, "kanit", db=db)
        import sqlite3
        con = sqlite3.connect(db)
        con.execute("UPDATE listings SET status='delisted' WHERE agent_id=?",
                    ("agent-1",))
        con.commit()
        con.close()

        bid = place_bid("agent-1", "buyer-1", 50.0, "{}", "n-2", db=db)
        assert match_bid(bid.bid_id, db=db) is None

    def test_listelenmemis_ajan_eslesmez(self, db: str):
        """Hiç listelenmemiş ajana teklif → matching engine None döner."""
        bid = place_bid("agent-ghost", "buyer-1", 999.0, "{}", "n-3", db=db)
        assert match_bid(bid.bid_id, db=db) is None
