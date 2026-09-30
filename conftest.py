"""Pytest conftest — import-oncesi fail-closed ENV sabitleri.

x402_servis.py modul import aninda resolve_treasury() ve Ledger(secret=...)
calistirir; bu degerler test ortaminda bos olursa SystemExit/ValueError verir.
Burada SADECE test-ortami sabitleri set edilir (gercek uretim secret'i DEGIL).
"""
import os

os.environ.setdefault("BORSA_SELLER_SECRET", "test-only-secret-32bytes-min-len")
os.environ.setdefault("UNPUMP_TREASURY_EOA", "0x" + "ab" * 20)
