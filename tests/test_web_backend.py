"""Web backend: session tokens, roles and the SQLite schema (no network, temporary DB)."""

import importlib
import sys

import pytest


@pytest.fixture()
def backend(tmp_path, monkeypatch):
    monkeypatch.setenv("WEB_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("ADMIN_EMAILS", "Admin@Example.com")
    monkeypatch.setenv("VIEWER_EMAILS", "viewer@example.com")
    monkeypatch.setenv("ALLOW_ANY_GOOGLE_VIEWER", "false")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "test-secret")
    for m in [m for m in sys.modules if m == "backend" or m.startswith("backend.")]:
        del sys.modules[m]
    config = importlib.import_module("backend.config")
    db = importlib.import_module("backend.db")
    auth = importlib.import_module("backend.auth")
    db.init()
    return config, db, auth


def test_session_roundtrip_and_tamper(backend):
    _, _, auth = backend
    tok, exp = auth.issue_session("someone@example.com")
    assert auth._read_session(tok) == "someone@example.com"
    head, body, sig = tok.split(".")
    with pytest.raises(Exception):
        auth._read_session(f"{head}.{body}.{sig[:-2]}xx")


def test_roles(backend):
    _, db, auth = backend
    assert auth.role_for("admin@example.com") == "admin"
    assert auth.role_for("viewer@example.com") == "viewer"
    assert auth.role_for("stranger@example.com") == "pending"
    with db.write() as c:
        c.execute("INSERT INTO users(email, role, approved) VALUES('stranger@example.com', 'viewer', 1)")
    assert auth.role_for("stranger@example.com") == "viewer"
    with db.write() as c:  # the users table can never grant admin
        c.execute("INSERT INTO users(email, role, approved) VALUES('sneaky@example.com', 'admin', 1)")
    assert auth.role_for("sneaky@example.com") == "viewer"


def test_schema_and_rollback(backend):
    _, db, _ = backend
    with db.write() as c:
        c.execute("INSERT INTO candles VALUES('BTCUSDT', '4h', 1, 1, 2, 0.5, 1.5, 10)")
    with pytest.raises(RuntimeError):
        with db.write() as c:
            c.execute("INSERT INTO candles VALUES('BTCUSDT', '4h', 2, 1, 2, 0.5, 1.5, 10)")
            raise RuntimeError("boom")
    assert [r["t"] for r in db.rows("SELECT t FROM candles")] == [1]
    assert db.one("PRAGMA journal_mode")["journal_mode"] == "wal"


def _request(client_host, headers):
    from starlette.requests import Request
    scope = {"type": "http", "method": "GET", "path": "/", "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
             "client": (client_host, 50000), "query_string": b""}
    return Request(scope)


def test_local_requests_skip_login_but_tunnel_does_not(backend):
    _, _, auth = backend
    local = auth.current_user(_request("127.0.0.1", {"host": "127.0.0.1:8724"}))
    assert local and local["role"] == "admin" and local["email"] == "admin@example.com"
    assert auth.current_user(_request("127.0.0.1", {"host": "localhost:8724"}))["role"] == "admin"
    # via cloudflared: loopback client but Cloudflare headers and the public host
    assert auth.current_user(_request("127.0.0.1", {"host": "api-crypto.nguyenchitrai.id.vn", "cf-connecting-ip": "1.2.3.4",
                                                    "cf-ray": "x"})) is None
    assert auth.current_user(_request("127.0.0.1", {"host": "api-crypto.nguyenchitrai.id.vn"})) is None  # public host
    assert auth.current_user(_request("127.0.0.1", {"host": "evil.example:8724"})) is None  # DNS rebinding
    assert auth.current_user(_request("192.168.1.5", {"host": "127.0.0.1:8724"})) is None  # LAN client


def test_build_orders_episodes(backend):
    import pandas as pd
    pipeline = importlib.import_module("backend.pipeline")
    t0 = pd.Timestamp("2024-01-01", tz="UTC")
    bars = [dict(t=t0 + pd.Timedelta(hours=4 * i), sig_d=[0.02]) for i in range(10)]
    ev = lambda h, kind, side, px, w, **k: dict(t=t0 + pd.Timedelta(hours=h, minutes=5), symbol="BTCUSDT", kind=kind,
                                                side=side, price=px, weight=w, **k)
    events = [
        ev(0, "book_fill", "buy", 100.0, 0.10),        # open LONG 10%
        ev(4, "book_fill", "buy", 110.0, 0.10),        # add -> avg 105, size 20%
        ev(8, "book_tp", "sell", 121.8, -0.20),        # take-profit
        ev(12, "book_fill", "sell", 120.0, -0.05),     # open SHORT 5%
        ev(16, "book_fill", "buy", 118.0, 0.049),      # back to ~0 -> closed by rebalance
        ev(20, "rung_fill", "buy", 90.0, 0.08, rung=2.5),
        ev(21, "rung_sl", "sell", 85.0, 0.08, ret=-0.0556),
    ]
    rows = pipeline.build_orders(events, bars, ["BTCUSDT"])
    book = [r for r in rows if r[1] == "book"]
    dip = [r for r in rows if r[1] == "dip"]
    assert len(book) == 2 and len(dip) == 1
    long_ = book[0]
    assert long_[2] == "LONG" and long_[5] == 100.0 and abs(long_[14] - 105.0) < 1e-9 and abs(long_[8] - 0.20) < 1e-9
    assert long_[15] == 2  # two limit fills in the episode
    assert long_[12] == "TP" and long_[7] == 121.8 and abs(long_[13] - 100 * (121.8 / 105 - 1)) < 1e-9
    short = book[1]
    assert short[2] == "SHORT" and short[12] == "Rebalance về 0" and short[13] > 0  # 120 -> 118 on a short
    assert dip[0][12] == "SL" and dip[0][13] < 0
