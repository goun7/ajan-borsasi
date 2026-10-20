"""G42 README-pin: README'deki gecmis test-sayisi iddialari taze olcume karsilanir.

Bu repoda README'de TEMEL sayi `tests/` kapsamina (877) ve depo-genis kapsama
(884) ayri ayri belirtilmistir. Pin, `pytest tests/ --collect-only` sonucunu
olcer ve README'deki tests/-kapsami sayilarinin hicbirinin stale olmamasini
saglar. Depo-genisi 884 sayisi .venv ve UNPUMP_TEST=1 gerektirdiginden pin'in
olcum-uzerinden degil, README'de kapsami-acikca-etiketli olmasindan emin
olarak ayrilir.
"""
import io
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = os.path.join(ROOT, "README.md")


def _collected_total(res_stdout: str) -> int:
    m = re.search(r"(\d+)\s+tests?\s+collected", res_stdout)
    if m:
        return int(m.group(1))
    total = 0
    for mm in re.finditer(r"^tests/[\w./-]+\.py:\s*(\d+)\s*$", res_stdout, re.M):
        total += int(mm.group(1))
    return total


def test_readme_test_count_is_not_stale():
    readme = io.open(README, encoding="utf-8").read()
    # README'nin belgeledigi olcum-kapsami: tests/ + test_x402_servis.py (depo-genisi).
    res = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "test_x402_servis.py",
         "--collect-only", "-q"],
        cwd=ROOT, capture_output=True, text=True, timeout=900,
    )
    assert res.returncode == 0, "collect-only basarisiz: %s" % res.stderr[-400:]
    collected = _collected_total(res.stdout)
    stale = []
    for m in re.finditer(r"(\d[\d.,]*)\s*passed", readme):
        claimed = int(m.group(1).replace(".", "").replace(",", ""))
        if claimed != collected:
            stale.append(m.group(0))
    assert not stale, (
        "README passed-sayilari stale: %s (taze collect-only=%d)" % (stale, collected)
    )
