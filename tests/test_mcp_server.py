"""G44: ajan-borsasi MCP-sunucusu testleri ( stdio-JSON-RPC-protokol).

Pacta/gateway/tenderix/syntropion/yieldix MCP-testlerinin deseni: sunucu
gercek bir SUBPROCESS olarak kosulur. Sunucu hicbir zaman exception
firlatmamali - her hata bir JSON kanitidir.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "mcp", "server.py")
MAX_TIMEOUT = 300


def _rpc(lines, timeout=MAX_TIMEOUT):
    """Sunucuyu SUBPROCESS olarak kotur ve JSON-RPC satirlarini gonder."""
    env = dict(os.environ)
    reqs = list(lines or [])
    proc = subprocess.run(
        [sys.executable, SERVER],
        input="\n".join(json.dumps(r) for r in reqs) + "\n",
        capture_output=True, text=True, env=env, timeout=timeout,
        cwd=str(ROOT), check=False)
    return proc


def _parse_resp(resp_line):
    """Bir JSON-RPC yanit satirini coz."""
    assert resp_line.strip(), "sunucudan-bos-yanit"
    return json.loads(resp_line)


def test_initialize_el_sikismasi():
    proc = _rpc([{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}])
    assert proc.returncode == 0, proc.stderr[-300:]
    d = _parse_resp(proc.stdout.strip().split("\n")[0])
    assert d["jsonrpc"] == "2.0"
    assert d["id"] == 1
    res = d["result"]
    assert res["protocolVersion"] == "2025-06-18"
    assert res["serverInfo"]["name"] == "ajan-borsasi"
    assert res["capabilities"]["tools"]["listChanged"] is False


def test_tools_list():
    proc = _rpc([{"jsonrpc": "2.0", "id": 2, "method": "tools/list"}])
    d = _parse_resp(proc.stdout.strip().split("\n")[0])
    tools = d["result"]["tools"]
    names = {t["name"] for t in tools}
    assert "market_summary" in names
    assert "kanit_zinciri_dogrula" in names
    for t in tools:
        assert t["inputSchema"]["type"] == "object"


def test_market_summary_kanit_donuyor():
    proc = _rpc([{"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                  "params": {"name": "market_summary", "arguments": {}}}])
    d = _parse_resp(proc.stdout.strip().split("\n")[0])
    assert "error" not in d
    payload = json.loads(d["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["rc"] == 0
    # gercek-cekirdekten-gelen-alanlar
    assert "listed_agents" in payload
    assert "verified_volume_usd" in payload
    assert "kanit" in payload["note"] or "kanıt" in payload["note"]


def test_kanit_zinciri_bos_liste_gecerli():
    """Bos-liste gecerli bir-sonsuz-zincirdir ( uzunluk=0, hata-yok)."""
    proc = _rpc([{"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                  "params": {"name": "kanit_zinciri_dogrula",
                             "arguments": {"kayitlar": []}}}])
    d = _parse_resp(proc.stdout.strip().split("\n")[0])
    assert "error" not in d
    payload = json.loads(d["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["uzunluk"] == 0
    assert payload["hatalar"] == []


def test_kanit_zinciri_kayitlar_zorunlu():
    """kayitlar olmadan cagri RED kaniti donmeli ( exception DEGIL)."""
    proc = _rpc([{"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                  "params": {"name": "kanit_zinciri_dogrula", "arguments": {}}}])
    d = _parse_resp(proc.stdout.strip().split("\n")[0])
    assert "error" not in d
    payload = json.loads(d["result"]["content"][0]["text"])
    assert payload["ok"] is False
    assert "kayitlar" in payload["reason"]


def test_bilinmeyen_arac_jsonrpc_hatasi():
    proc = _rpc([{"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                  "params": {"name": "boyle-bir-arac-yok", "arguments": {}}}])
    d = _parse_resp(proc.stdout.strip().split("\n")[0])
    assert d["jsonrpc"] == "2.0"
    assert d["id"] == 6
    err = d["error"]
    assert err["code"] == -32601
    assert "boyle-bir-arac-yok" in err["message"]


def test_ping_ve_bilinmeyen_method():
    proc = _rpc([
        {"jsonrpc": "2.0", "id": 7, "method": "ping"},
        {"jsonrpc": "2.0", "id": 8, "method": "tuhaf-method"},
    ])
    lines = [ln for ln in proc.stdout.strip().split("\n") if ln.strip()]
    p1 = _parse_resp(lines[0])
    assert p1["id"] == 7
    assert p1["result"] == {}
    p2 = _parse_resp(lines[1])
    assert p2["id"] == 8
    assert p2["error"]["code"] == -32601
