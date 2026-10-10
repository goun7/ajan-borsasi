"""mainnet_verify._rpc dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-3: urllib.request.urlopen STUBLANIYOR — gercek HTTP YAPILMADI.
Kural-4: saf in-memory (ag YOK).
"""
import io
import json
import sys
import urllib.error
import urllib.request

import pytest

sys.path.insert(0, ".")
from mainnet_verify import _rpc, RPC_URL, RPCError, _UA  # noqa: E402


class _Resp:
    def __init__(self, payload_bytes):
        self._b = payload_bytes

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._b


@pytest.fixture()
def stub(monkeypatch):
    calls = {"last": None}

    def _urlopen(req, timeout=20):
        calls["last"] = {
            "url": req.full_url,
            "body": json.loads(req.data.decode()),
            "headers": req.headers,
            "timeout": timeout,
            "has_data": req.data is not None,
        }
        resp = calls.get("response", {"result": "0x1"})
        if isinstance(resp, Exception):
            raise resp
        return _Resp(json.dumps(resp).encode())

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    return calls


def _resp(monkeypatch, **kw):
    out = {"jsonrpc": "2.0", "id": 1, "result": "0x1"}
    out.update(kw)
    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda req, timeout=20: _Resp(json.dumps(out).encode()))
    return out


# -- mutlu-yol ---------------------------------------------------------------------------------

def test_returns_result(monkeypatch):
    _resp(monkeypatch, result="0xdeadbeef")
    assert _rpc("eth_blockNumber", []) == "0xdeadbeef"


def test_returns_dict_result(monkeypatch):
    _resp(monkeypatch, result={"number": "0x10"})
    assert _rpc("eth_getBlockByNumber", ["latest"]) == {"number": "0x10"}


def test_returns_int_result(monkeypatch):
    _resp(monkeypatch, result=42)
    assert _rpc("net_version", []) == 42


def test_returns_none_result(monkeypatch):
    _resp(monkeypatch, result=None)
    assert _rpc("eth_getBalance", ["0x0", "latest"]) is None


def test_returns_list_result(monkeypatch):
    _resp(monkeypatch, result=["a", "b"])
    assert _rpc("eth_getLogs", [{}]) == ["a", "b"]


# -- istek-icerigi ---------------------------------------------------------------------------------

def test_url_is_rpc_url(stub):
    _rpc("eth_blockNumber", [])
    assert stub["last"]["url"] == RPC_URL


def test_jsonrpc_version(stub):
    _rpc("eth_blockNumber", [])
    assert stub["last"]["body"]["jsonrpc"] == "2.0"


def test_method_sent(stub):
    _rpc("eth_getBalance", ["0x1", "latest"])
    assert stub["last"]["body"]["method"] == "eth_getBalance"


def test_params_sent(stub):
    _rpc("eth_getBalance", ["0x1", "latest"])
    assert stub["last"]["body"]["params"] == ["0x1", "latest"]


def test_empty_params(stub):
    _rpc("eth_blockNumber", [])
    assert stub["last"]["body"]["params"] == []


def test_id_is_1(stub):
    _rpc("eth_blockNumber", [])
    assert stub["last"]["body"]["id"] == 1


def test_content_type_header(stub):
    _rpc("eth_blockNumber", [])
    assert stub["last"]["headers"].get("Content-type", "").startswith("application/json")


def test_user_agent_sent(stub):
    """UA: unpump-mainnet-verify/1.0 (yorumda 'curl' yazar ama deger farkli)."""
    _rpc("eth_blockNumber", [])
    ua = stub["last"]["headers"].get("User-agent", "")
    assert ua and "unpump-mainnet-verify" in ua


def test_timeout_is_20(stub):
    _rpc("eth_blockNumber", [])
    assert stub["last"]["timeout"] == 20


def test_post_body_is_bytes(stub):
    """payload .encode() ile bytes."""
    import mainnet_verify as M
    orig = M.urllib.request.Request
    seen = {}

    class _R:
        def __init__(self, url, data, headers):
            seen["data"] = data
            self.full_url = url
            self.headers = headers
            self.data = data
    M.urllib.request.Request = _R
    try:
        _rpc("eth_blockNumber", [])
    finally:
        M.urllib.request.Request = orig
    assert isinstance(seen["data"], bytes)


def test_post_has_data(stub):
    """data set -> POST (urllib convention)."""
    _rpc("eth_blockNumber", [])
    assert stub["last"]["has_data"] is True


# -- error-dali ---------------------------------------------------------------------------------

def test_rpc_error_raises(monkeypatch):
    _resp(monkeypatch, error={"code": -32000, "message": "revert"})
    with pytest.raises(RPCError, match="revert"):
        _rpc("eth_call", [{}])


def test_error_includes_method(monkeypatch):
    _resp(monkeypatch, error={"code": 1, "message": "boom"})
    with pytest.raises(RPCError, match="eth_call"):
        _rpc("eth_call", [{}])


def test_error_is_exception(monkeypatch):
    _resp(monkeypatch, error={"message": "x"})
    with pytest.raises(Exception):
        _rpc("eth_call", [])


def test_error_none_result_no_raise(monkeypatch):
    """result None ama error yoksa None doner (hata DEGIL)."""
    _resp(monkeypatch, result=None)
    assert _rpc("eth_call", []) is None


def test_error_dict_value(monkeypatch):
    _resp(monkeypatch, error={"code": -32601, "message": "not found"})
    with pytest.raises(RPCError) as exc:
        _rpc("unknown_method", [])
    assert "not found" in str(exc.value)


def test_error_string_value(monkeypatch):
    _resp(monkeypatch, error="plain string error")
    with pytest.raises(RPCError, match="plain"):
        _rpc("eth_call", [])


# -- http-hatalari ---------------------------------------------------------------------------------

def test_url_error_raises(monkeypatch):
    def _boom(req, timeout=20):
        raise urllib.error.URLError("no host")
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    with pytest.raises(urllib.error.URLError):
        _rpc("eth_blockNumber", [])


def test_timeout_error_raises(monkeypatch):
    import socket

    def _boom(req, timeout=20):
        raise socket.timeout("timed out")
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    with pytest.raises(socket.timeout):
        _rpc("eth_blockNumber", [])


def test_http_error_raises(monkeypatch):
    def _boom(req, timeout=20):
        raise urllib.error.HTTPError(RPC_URL, 500, "err", {}, None)
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    with pytest.raises(urllib.error.HTTPError):
        _rpc("eth_blockNumber", [])


def test_json_decode_error_raises(monkeypatch):
    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda req, timeout=20: _Resp(b"{not-json"))
    with pytest.raises(json.JSONDecodeError):
        _rpc("eth_blockNumber", [])


def test_empty_body_raises(monkeypatch):
    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda req, timeout=20: _Resp(b""))
    with pytest.raises(json.JSONDecodeError):
        _rpc("eth_blockNumber", [])


def test_error_key_missing_raises(monkeypatch):
    """{"jsonrpc":..} ne result ne error -> KeyError."""
    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda req, timeout=20: _Resp(json.dumps({"jsonrpc": "2.0", "id": 1}).encode()))
    with pytest.raises(KeyError):
        _rpc("eth_blockNumber", [])


# -- params-cesitleri ---------------------------------------------------------------------------------

def test_params_single_string(stub):
    _rpc("eth_getBalance", ["0xabc"])
    assert stub["last"]["body"]["params"] == ["0xabc"]


def test_params_nested(stub):
    params = [{"to": "0x1", "data": "0x2"}, "latest"]
    _rpc("eth_call", params)
    assert stub["last"]["body"]["params"] == params


def test_params_empty_string(stub):
    _rpc("eth_call", [""])
    assert stub["last"]["body"]["params"] == [""]


def test_params_int(stub):
    _rpc("eth_getBlockByNumber", [1, False])
    assert stub["last"]["body"]["params"] == [1, False]


def test_params_bool(stub):
    _rpc("eth_getBlockByNumber", ["latest", True])
    assert stub["last"]["body"]["params"][1] is True


# -- tekrar ---------------------------------------------------------------------------------

def test_repeatable(monkeypatch):
    _resp(monkeypatch, result="0x1")
    assert _rpc("eth_blockNumber", []) == _rpc("eth_blockNumber", [])


def test_independent_calls(stub):
    assert _rpc("eth_blockNumber", []) == "0x1"
    assert _rpc("eth_blockNumber", []) == "0x1"


def test_method_change_reflected(stub):
    assert _rpc("a", []) == "0x1"
    _rpc("b", [])
    assert stub["last"]["body"]["method"] == "b"


# -- constant ---------------------------------------------------------------------------------

def test_rpc_url_is_https():
    assert RPC_URL.startswith("https://")


def test_rpc_url_base():
    assert "base" in RPC_URL or "publicnode" in RPC_URL


def test_rpc_error_class():
    assert issubclass(RPCError, Exception)


def test_ua_has_content_type():
    assert _UA.get("Content-Type", "").startswith("application/json")


def test_ua_unpump():
    """BILGI: yorum 'curl user-agent' der ama gercek UA farkli."""
    assert "unpump-mainnet-verify" in _UA.get("User-Agent", "")
