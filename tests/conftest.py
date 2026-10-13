"""Test conftest — sester kardes projeyi sys.path'e ekle.

Bazi testler `import sester.schemes` ile `verify_exact_sester` fonksiyonunu
monkeypatch etmek ister. sester ayri bir projedir (63-Sester) ve bu repoda
pip ile kurulmus degildir. Bu conftest, gercek sester paketi bulunamazsa
kardes proje dizinini sys.path'e ekler. Bulunursa hicbir sey yapilmaz.

Saf in-memory: disk/ag erisimi YOK, sadece sys.path uzerine dizin ekleme.
"""

import importlib.util
import os
import sys


def _ensure_sester_on_path() -> None:
    if importlib.util.find_spec("sester") is not None:
        return  # gercek paket kurulu — dokunma

    here = os.path.dirname(os.path.abspath(__file__))
    candidates = (
        os.path.join(here, "..", "..", "01_unicorn", "63-Sester"),
        os.path.join(here, "..", "..", "sester"),
        "/home/gokun/projects/00_TAMGA-MESH/sester",
    )
    for c in candidates:
        c = os.path.normpath(c)
        if os.path.isdir(os.path.join(c, "sester")):
            sys.path.insert(0, c)
            if importlib.util.find_spec("sester") is not None:
                return  # gercek paket bulundu


_ensure_sester_on_path()
