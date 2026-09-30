"""Pytest conftest — import-oncesi fail-closed ENV + zincir-mock.

x402_servis.py modul import aninda resolve_treasury() ve Ledger(secret=...)
calistirir; bu degerler test ortaminda bos olursa SystemExit/ValueError verir.
Burada SADECE test-ortami sabitleri set edilir (gercek uretim secret'i DEGIL).

Ayrica mainnet_verify.find_transfer gercek RPC (base.publicnode.com) arar —
testler cevrimdisi olmali. Bu yuzden basarili bir TransferFound stub'u.
"""
import os

os.environ.setdefault("BORSA_SELLER_SECRET", "test-only-secret-32bytes-min-len")
os.environ.setdefault("UNPUMP_TREASURY_EOA", "0x" + "ab" * 20)
# UNPUMP_TEST=1 odeme-kapisini test-moduna alir (gercek zincir aramaz).
os.environ.setdefault("UNPUMP_TEST", "1")


def _install_chain_mock():
    """mainnet_verify.find_transfer'i basarili donen bir stub ile degistir.

    x402 odeme-kapisi test icin 'odeme bulundu' davranisini taklit eder.
    Gercek RPC'ye GITMEZ — bu sadece unit-test izolasyonu icindir.
    """
    try:
        import mainnet_verify
    except Exception:
        return

    class _TransferFound:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    def _stub_find_transfer(*, from_addr, to_addr, amount_minor):
        return _TransferFound(
            from_addr=from_addr,
            to_addr=to_addr,
            amount_minor=amount_minor,
            tx_hash="0x" + "00" * 32,
            block=1,
        )

    mainnet_verify.find_transfer = _stub_find_transfer
    # x402_servis de ayni fonksiyonu import etmis olabilir
    try:
        import x402_servis
        if hasattr(x402_servis, "verify_mainnet_payment"):
            x402_servis.verify_mainnet_payment = lambda **kw: _stub_find_transfer(
                from_addr=kw.get("from_addr", ""),
                to_addr=kw.get("to_addr", ""),
                amount_minor=kw.get("amount_minor", 0),
            )
    except Exception:
        pass
    # mainnet_guard.py 'mv' takma adi ile cagirir (L152)
    try:
        import mainnet_guard
        mainnet_guard.mv.verify_mainnet_payment = lambda **kw: _stub_find_transfer(
            from_addr=kw.get("from_addr", ""),
            to_addr=kw.get("to_addr", ""),
            amount_minor=kw.get("amount_minor", 0),
        )
    except Exception:
        pass


_install_chain_mock()

