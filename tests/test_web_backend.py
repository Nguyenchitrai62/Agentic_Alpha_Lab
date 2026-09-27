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
