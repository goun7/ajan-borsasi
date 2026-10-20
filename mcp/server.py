#!/usr/bin/env python3
"""ajan-borsasi MCP sunucusu - Model Context Protocol 2025-06-18 over stdio.

Ajan Borsasi ( Unpump.cash Faz-0 prototipi) cekirdegini AI ajanlarina
MCP araclari olarak sunar. Tamga/sester/pacta MCP sunucularinin ayni
deseni ( stdio JSON-RPC, uc-sonuc kaniti, exception-YOK).

Tasarim-ilkesi:
  - SAF STDLIB - borsa_core hicbir pip bagimliligi gerektirmez.
  - UC-SONUC - her arac GREEN/RED/INDETERMINE JSON kaniti dondurur;
    ASLA exception firlatmaz.
  - Izole-DB - sunucu OZEL-bir gecici-SQLite kullanir ( varsayilan
    ~/.workspace DB'sine YAZMAZ). args.db ile hedef-DB-overide-edilebilir.

Araclar:
  market_summary     borsa-ozeti ( listaj, teklif, kanitli-hacim)
  kanit_zinciri_dogrula  JSON-kanit-zincirinin bütünlük-dogrulaması

Calistirma:
  python3 mcp/server.py                    # stdio JSON-RPC
  (istemci tarafi: "command": "python", "args": ["<repo>/mcp/server.py"])
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "ajan-borsasi"
SERVER_VERSION = "0.1.0"
ROOT = Path(__file__).resolve().parents[1]
MAX_TIMEOUT = 120  # saniye


def _e(msg: str) -> dict:
    return {"jsonrpc": "2.0", "error": {"code": -32602, "message": msg}}


def _result(req_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _text(payload: dict) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}


def _db_for(args: dict) -> str:
    """Ozel-gecici-DB ( uretim-DB'sine-yazma). args.db veya temp-dizin."""
    db = args.get("db")
    if isinstance(db, str) and db:
        return db
    return str(Path(tempfile.mkdtemp(prefix="ajanborsa-mcp-")) / "borsa.sqlite3")


def _run_py(code: str) -> dict:
    """borsa_core'u SUBPROCESS icinde calistir ( import-kirli-degil).

    Fail-closed: her hata ( zaman-asimi, exception) RED kanitidir.
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=MAX_TIMEOUT, cwd=str(ROOT))
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "zaman-asimi: %ds" % MAX_TIMEOUT}
    except Exception as e:  # cephedeki her hata JSON kaniti olmali
        return {"ok": False, "reason": "calistirma-hatasi: %s" % e}
    out = (proc.stdout or "").strip()
    rec = None
    if out:
        try:
            r = json.loads(out.splitlines()[-1])
            if isinstance(r, dict):
                rec = r
        except json.JSONDecodeError:
            rec = None
    if rec is not None:
        rec.setdefault("ok", proc.returncode == 0)
        rec.setdefault("rc", proc.returncode)
        return rec
    return {
        "ok": False,
        "rc": proc.returncode,
        "reason": "cekis-json-uretmedi" + (": %s" % out[:120] if out else ""),
        "stderr": (proc.stderr or "").strip()[:300],
    }


def _tool_market_summary(args: dict) -> dict:
    """Borsa-ozeti - kanit-bagli-hacim-dahil."""
    db = _db_for(args)
    code = (
        "import sys, json, os; sys.path.insert(0, '.');\n"
        "import borsa_core;\n"
        "print(json.dumps(borsa_core.market_summary(%r), default=str))\n" % db
    )
    return _run_py(code)


def _tool_kanit_zinciri_dogrula(args: dict) -> dict:
    """Kanit-zinciri bütünlük-dogrulaması - args.kayitlar zorunlu.

    args.kayitlar: list-of-kayit-dict ( zincir-verisi). Bos-liste gecerli
    bir-sonsuz-zincirdir ( uzunluk=0, hata-yok).
    """
    kayitlar = args.get("kayitlar")
    if not isinstance(kayitlar, list):
        return {"ok": False, "reason": "kayitlar-zorunlu ( args.kayitlar-list-of-dict)"}
    code = (
        "import sys, json; sys.path.insert(0, '.');\n"
        "import kanit_cekirdegi as kc;\n"
        "print(json.dumps(kc.zinciri_dogrula({'kayitlar': json.loads(%r)}), default=str))\n"
        % json.dumps(kayitlar)
    )
    return _run_py(code)


TOOL_IMPLS = {
    "market_summary": _tool_market_summary,
    "kanit_zinciri_dogrula": _tool_kanit_zinciri_dogrula,
}

TOOLS_LIST = [
    {
        "name": "market_summary",
        "description": (
            "Ajan Borsasi ozetini doner: listeli-ajan-sayisi, teklifler-"
            "duruma-gore, kanit-bagli-tamamlanan-is-hacmi. Izole-gecici-DB "
            "kullanir ( uretim-DB'sine-yazmaz). args.db opsiyonel."),
        "inputSchema": {
            "type": "object",
            "properties": {"db": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "kanit_zinciri_dogrula",
        "description": (
            "Bir kanit-zincirinin ( hash-chain) butunlugunu dogrular. "
            "args.kayitlar zorunlu ( list-of-dict). Bos-liste gecerlidir. "
            "JSON kanit doner, asla exception firlatmaz."),
        "inputSchema": {
            "type": "object",
            "properties": {"kayitlar": {"type": "array"}},
            "required": ["kayitlar"],
            "additionalProperties": False,
        },
    },
]


def _tools_list_result() -> dict:
    return {"tools": TOOLS_LIST}


def _handle_call(req_id, params: dict) -> dict | None:
    name = params.get("name")
    if not isinstance(name, str) or not name:
        return _result(req_id, _e("arac-adi-zorunlu"))
    impl = TOOL_IMPLS.get(name)
    if impl is None:
        return {
            "jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32601, "message": "bilinmeyen-arac: %s" % name},
        }
    args = params.get("arguments") or {}
    if not isinstance(args, dict):
        return _result(req_id, _e("arguments-bir-nesne-olmali"))
    try:
        payload = impl(args)
    except Exception as e:  # fail-closed: traceback degil JSON kaniti
        payload = {"ok": False, "reason": "arac-hatasi: %s" % e}
    return _result(req_id, _text(payload))


def main() -> int:
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            req = json.loads(raw)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps(_e("gecersiz-json")) + "\n")
            sys.stdout.flush()
            continue
        if not isinstance(req, dict):
            sys.stdout.write(json.dumps(_e("istek-bir-nesne-degil")) + "\n")
            sys.stdout.flush()
            continue
        method = req.get("method")
        req_id = req.get("id")
        if method == "initialize":
            sys.stdout.write(json.dumps(_result(req_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": SERVER_VERSION,
                    "instructions": (
                        "Ajan Borsasi ( Unpump Faz-0) sunucusu. "
                        "market_summary -> borsa-ozeti ( izole-DB); "
                        "kanit_zinciri_dogrula -> zincir-dogrulama. "
                        "Her arac JSON kaniti doner, asla exception firlatmaz."),
                }})) + "\n")
        elif method == "notifications/initialized":
            continue  # bildirim - yanit yok
        elif method == "tools/list":
            sys.stdout.write(json.dumps(_result(req_id, _tools_list_result())) + "\n")
        elif method == "tools/call":
            resp = _handle_call(req_id, req.get("params") or {})
            if resp is not None:
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        elif method == "ping":
            sys.stdout.write(json.dumps(_result(req_id, {})) + "\n")
        elif req_id is not None:
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32601, "message": "bilinmeyen-method: %s" % method}
            }) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
