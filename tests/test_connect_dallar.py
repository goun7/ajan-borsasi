"""borsa_core._connect dal-kesen testleri (LEED).

Kural-1: mevcut dosyalara DOKUNULMADI, SADECE bu yeni dosya eklendi.
Kural-4: saf in-memory sqlite (tmp_path — dis cagri YOK).
3-tablo semasi + WAL + Row-factory.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, ".")
from borsa_core import _connect, DB_PATH  # noqa: E402


@pytest.fixture()
def conn(tmp_path):
    return _connect(str(tmp_path / "b.db"))


# == temel ==========================================================================================

def test_returns_connection(conn):
    assert isinstance(conn, sqlite3.Connection)


def test_row_factory(conn):
    """ORTAM: row_factory = sqlite3.Row (subscriptable)."""
    assert conn.row_factory is sqlite3.Row


def test_wal_mode(conn):
    """ORTAM: journal_mode=WAL."""
    r = conn.execute("PRAGMA journal_mode").fetchone()
    assert r[0].lower() == "wal"


def test_parent_dir_olusturulur(tmp_path):
    """ORTAM: parent.mkdir(parents=True)."""
    derin = tmp_path / "a" / "b" / "c.db"
    c = _connect(str(derin))
    assert derin.parent.is_dir()
    c.close()


def test_repeatable(tmp_path):
    """ORTAM: ayni-db tekrar-baglanabilir."""
    p = str(tmp_path / "r.db")
    c1 = _connect(p)
    c1.close()
    c2 = _connect(p)
    assert isinstance(c2, sqlite3.Connection)
    c2.close()


# == tablolar =======================================================================================

@pytest.mark.parametrize("tablo", ["listings", "bids", "matches"])
def test_tablo_var(conn, tablo):
    """ORTAM: 3-tablo olusturulur."""
    r = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (tablo,)).fetchone()
    assert r is not None


def test_tablo_sayisi(conn):
    """ORTAM: tam olarak 3-tablo."""
    r = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()
    assert r[0] == 3


def test_tablolar_listesi(conn):
    r = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "ORDER BY name").fetchall()
    assert [x[0] for x in r] == ["bids", "listings", "matches"]


# == listings-tablo ====================================================================================

def test_liste_kolonlar(conn):
    """ORTAM: listings-tablo kolonlari."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(listings)")}
    for c in ("agent_id", "name", "price_target", "proof_hash"):
        assert c in cols


def test_liste_primary_key(conn):
    """ORTAM: agent_id PRIMARY KEY."""
    cols = conn.execute("PRAGMA table_info(listings)").fetchall()
    pk = [r[1] for r in cols if r[5]]
    assert "agent_id" in pk


def test_liste_insert(conn):
    conn.execute("INSERT INTO listings (agent_id, name) VALUES ('a1', 'x')")
    conn.commit()
    r = conn.execute("SELECT agent_id FROM listings").fetchone()
    assert r[0] == "a1"


def test_liste_duplicate_red(conn):
    """ORTAM: PRIMARY KEY duplicate -> IntegrityError."""
    conn.execute("INSERT INTO listings (agent_id, name) VALUES ('a1', 'x')")
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO listings (agent_id, name) VALUES ('a1', 'y')")


# == bids-tablo ======================================================================================

def test_bid_kolonlar(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(bids)")}
    for c in ("bid_id", "agent_id", "work_spec", "nonce"):
        assert c in cols


def test_bid_nonce_unique(conn):
    """ORTAM: nonce UNIQUE."""
    conn.execute("INSERT INTO bids (bid_id, nonce) VALUES ('b1', 'n1')")
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO bids (bid_id, nonce) VALUES ('b2', 'n1')")


def test_bid_insert(conn):
    conn.execute("INSERT INTO bids (bid_id, agent_id, nonce) "
                 "VALUES ('b1', 'a1', 'n1')")
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM bids").fetchone()[0] == 1


# == matches-tablo ====================================================================================

def test_match_kolonlar(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(matches)")}
    for c in ("match_id", "bid_id", "work_done"):
        assert c in cols


def test_match_insert(conn):
    conn.execute("INSERT INTO matches (match_id, bid_id) VALUES ('m1', 'b1')")
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0] == 1


# == DB_PATH =========================================================================================

def test_db_path_str():
    assert isinstance(DB_PATH, str)


def test_db_path_icerik():
    """ORTAM: default yol."""
    assert "bors" in DB_PATH.lower() or ".db" in DB_PATH.lower()


# == cesitli =========================================================================================

def test_transaction_commit(conn):
    """ORTAM: commit() sonrasi kayit kalici."""
    conn.execute("INSERT INTO listings (agent_id) VALUES ('a')")
    conn.commit()
    r = conn.execute("SELECT COUNT(*) FROM listings").fetchone()
    assert r[0] == 1


def test_row_subscriptable(conn):
    """ORTAM: Row-factory ile sutun-erisimi."""
    conn.execute("INSERT INTO listings (agent_id, name) VALUES ('a', 'x')")
    conn.commit()
    r = conn.execute("SELECT * FROM listings").fetchone()
    assert r["agent_id"] == "a"
    assert r["name"] == "x"


def test_autocommit_degil(conn):
    """ORTAM: commit yapilmadan kayit gorunmez (rollback)."""
    conn.execute("INSERT INTO listings (agent_id) VALUES ('a')")
    conn.rollback()
    assert conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 0


def test_bos_tablo_sorgu(conn):
    assert conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 0


def test_turkce_deger(conn):
    conn.execute("INSERT INTO listings (agent_id, name) VALUES ('a1', 'Türkçe')")
    conn.commit()
    r = conn.execute("SELECT name FROM listings").fetchone()
    assert r[0] == "Türkçe"


def test_uzun_deger(conn):
    conn.execute("INSERT INTO bids (bid_id, work_spec) VALUES ('b', ?)",
                 ("x" * 10000,))
    conn.commit()
    r = conn.execute("SELECT work_spec FROM bids").fetchone()
    assert len(r[0]) == 10000


@pytest.mark.parametrize("tablo,kolon", [
    ("listings", "agent_id"), ("bids", "bid_id"), ("matches", "match_id"),
])
def test_primary_key_matrix(conn, tablo, kolon):
    cols = conn.execute(f"PRAGMA table_info({tablo})").fetchall()
    pk = [r[1] for r in cols if r[5]]
    assert kolon in pk
