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
