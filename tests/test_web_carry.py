"""Web carry panel: read-only helper over the carry paper ledger + GET /api/carry.

No network, no orders, temporary DB and state files only.
"""

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture()
def backend(tmp_path, monkeypatch):
    monkeypatch.setenv("WEB_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
    monkeypatch.setenv("VIEWER_EMAILS", "viewer@example.com")
    monkeypatch.setenv("ALLOW_ANY_GOOGLE_VIEWER", "false")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "test-secret")
    monkeypatch.setenv("WEB_SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("AUTH_ACCESS_TTL_SECONDS", "900")
    monkeypatch.setenv("AUTH_REFRESH_TTL_SECONDS", "604800")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://crypto.example.com")
    monkeypatch.setenv("CORS_ALLOW_ORIGIN_REGEX", "")
    for m in [m for m in sys.modules if m == "backend" or m.startswith("backend.")]:
        del sys.modules[m]
    config = importlib.import_module("backend.config")
    db = importlib.import_module("backend.db")
    auth = importlib.import_module("backend.auth")
    carry_view = importlib.import_module("backend.carry_view")
    db.init()
    return config, db, auth, carry_view


@pytest.fixture()
def web_client(backend):
    from fastapi.testclient import TestClient
    server = importlib.import_module("backend.server")
    return TestClient(server.app, base_url="https://testserver"), server, backend


def _bearer(auth, email):
    return {"Authorization": "Bearer " + auth.create_session(email)["access_token"]}


NOW = datetime.now(timezone.utc)


def _fake_state(updated_at=None, with_open=True, with_settled=False):
    st = {
        "tag": "carry", "equity_arg": 5000.0, "f": 0.5,
        "rule": {"coins": ["BTC", "ETH"], "roll_days": 7, "basis_threshold": 0.04},
        "rule_sha256": "ab" * 32,
        "created_at": (NOW - timedelta(days=10)).isoformat(),
        "updated_at": (updated_at or NOW).isoformat(),
        "positions": {}, "history": [], "entered_symbols": [],
        "totals": {"n_entered": 0, "n_skipped": 0, "realised_pnl": 0.0, "fees_paid": 0.0},
    }
    if with_open:
        st["positions"]["BTC"] = {
            "coin": "BTC", "symbol": "BTC-26JUN26", "category": "linear",
            "spot_symbol": "BTCUSDT", "status": "open",
            "entry_time": (NOW - timedelta(days=10)).isoformat(),
            "delivery_ms": int((NOW + timedelta(days=70)).timestamp() * 1000),
            "S_entry": 60000.0, "F_entry": 61000.0,
            "ann_basis": 0.08, "dte_days": 80.0,
            "equity_entry": 5000.0, "f": 0.5,
            "entry_fees": 3.875,
            "last_spot": 60600.0, "last_fut": 61400.0,
            "mtm_alloc": 0.012, "unrealised": 30.0,
        }
        st["totals"]["n_entered"] = 1
    if with_settled:
        st["history"].append({
            "coin": "ETH", "symbol": "ETH-26JUN26", "status": "delivered",
            "entry_time": (NOW - timedelta(days=100)).isoformat(),
            "settled_at": (NOW - timedelta(days=5)).isoformat(),
            "S_entry": 3000.0, "F_entry": 3060.0, "S_del": 3030.0,
            "delivery_source": "delivery-price",
            "realised_pnl": 25.5, "realised_ret_alloc": 0.0102,
        })
        st["totals"]["realised_pnl"] = 25.5
        st["totals"]["fees_paid"] = 6.875
    return st


def _write_state(tmp_path, st):
    p = tmp_path / "state.json"
    p.write_text(json.dumps(st), encoding="utf-8")
    return p


def test_empty_missing_file_is_not_stale_crash(backend, tmp_path):
    _, _, _, carry_view = backend
    before = {p.name for p in tmp_path.iterdir()}
    view = carry_view.get_carry_view(tmp_path / "no-such-state.json", now=NOW)
    assert view["open_pairs"] == [] and view["settled_pairs"] == []
    assert view["n_open"] == 0 and view["n_settled"] == 0
    assert view["has_data"] is False and view["stale"] is True
    assert view["updated_at"] is None and view["rule"] is None
    assert view["totals"] == {"n_entered": 0, "n_skipped": 0, "realised_pnl_usdt": 0.0, "fees_paid_usdt": 0.0}
    assert {p.name for p in tmp_path.iterdir()} == before  # read-only: nothing created


def test_corrupt_file_is_empty_not_raised(backend, tmp_path):
    _, _, _, carry_view = backend
    p = tmp_path / "state.json"
    p.write_text("{corrupt", encoding="utf-8")
    view = carry_view.get_carry_view(p, now=NOW)
    assert view["has_data"] is False and view["open_pairs"] == []


def test_one_open_pair_fields(backend, tmp_path):
    _, _, _, carry_view = backend
    p = _write_state(tmp_path, _fake_state())
    raw = p.read_text(encoding="utf-8")
    view = carry_view.get_carry_view(p, now=NOW)
    assert p.read_text(encoding="utf-8") == raw  # read-only: file untouched
    assert view["rule"] == {"coins": ["BTC", "ETH"], "roll_days": 7, "basis_threshold": 0.04}
    assert view["rule_sha256"] == "ab" * 32
    assert view["n_open"] == 1 and view["has_data"] is True and view["stale"] is False
    pos = view["open_pairs"][0]
    assert pos["coin"] == "BTC" and pos["contract"] == "BTC-26JUN26"
    assert datetime.fromisoformat(pos["entry_time"]) <= NOW
    assert pos["entry_basis"] == pytest.approx(0.08)
    assert pos["entry_basis_pct_yr"] == pytest.approx(8.0)
    assert pos["days_to_delivery"] == pytest.approx(70.0, abs=0.01)
    assert pos["mtm_alloc"] == pytest.approx(0.012) and pos["mtm_pct_alloc"] == pytest.approx(1.2)
    assert pos["entry_fees_usdt"] == pytest.approx(3.875)


def test_settled_pairs_and_realised_pnl(backend, tmp_path):
    _, _, _, carry_view = backend
    p = _write_state(tmp_path, _fake_state(with_open=False, with_settled=True))
    view = carry_view.get_carry_view(p, now=NOW)
    assert view["n_open"] == 0 and view["n_settled"] == 1 and view["has_data"] is True
    rec = view["settled_pairs"][0]
    assert rec["coin"] == "ETH" and rec["contract"] == "ETH-26JUN26"
    assert rec["delivery_source"] == "delivery-price"
    assert rec["realised_pnl_usdt"] == pytest.approx(25.5)
    assert rec["realised_ret_alloc"] == pytest.approx(0.0102)
    assert view["totals"]["realised_pnl_usdt"] == pytest.approx(25.5)
    assert view["totals"]["fees_paid_usdt"] == pytest.approx(6.875)


def test_stale_flag_boundary(backend, tmp_path):
    _, _, _, carry_view = backend
    p = tmp_path / "state.json"
    p.write_text(json.dumps(_fake_state(updated_at=NOW - timedelta(minutes=30))), encoding="utf-8")
    assert carry_view.get_carry_view(p, now=NOW)["stale"] is False
    p.write_text(json.dumps(_fake_state(updated_at=NOW - timedelta(hours=3))), encoding="utf-8")
    assert carry_view.get_carry_view(p, now=NOW)["stale"] is True


def test_route_returns_ledger_to_viewer_and_rejects_anonymous(web_client, tmp_path, monkeypatch):
    client, server, (_, _, auth, carry_view) = web_client
    p = tmp_path / "state.json"
    p.write_text(json.dumps(_fake_state(with_settled=True)), encoding="utf-8")
    raw = p.read_text(encoding="utf-8")
    monkeypatch.setattr(carry_view, "default_state_path", lambda: p)
    monkeypatch.setattr(carry_view, "deployed_state_path", lambda: tmp_path / "no_runner.json")  # isolate from the live runner
    server.clear_cache()

    assert client.get("/api/carry").status_code == 401
    viewer = _bearer(auth, "viewer@example.com")
    response = client.get("/api/carry", headers=viewer)
    assert response.status_code == 200
    body = response.json()
    assert body["rule_sha256"] == "ab" * 32 and body["rule"]["basis_threshold"] == 0.04
    assert body["n_open"] == 1 and body["open_pairs"][0]["coin"] == "BTC"
    assert body["open_pairs"][0]["entry_basis_pct_yr"] == pytest.approx(8.0)
    assert body["n_settled"] == 1 and body["totals"]["realised_pnl_usdt"] == pytest.approx(25.5)
    assert body["stale"] is False and body["updated_at"]
    assert p.read_text(encoding="utf-8") == raw  # read-only: the route never writes the ledger
    assert client.get("/api/carry", headers=_bearer(auth, "pending@example.com")).status_code == 403


def test_route_empty_ledger_when_no_state_file(web_client, tmp_path, monkeypatch):
    client, server, (_, _, auth, carry_view) = web_client
    monkeypatch.setattr(carry_view, "default_state_path", lambda: tmp_path / "missing.json")
    monkeypatch.setattr(carry_view, "deployed_state_path", lambda: tmp_path / "no_runner.json")  # isolate from the live runner
    server.clear_cache()
    body = client.get("/api/carry", headers=_bearer(auth, "viewer@example.com")).json()
    assert body["open_pairs"] == [] and body["has_data"] is False and body["stale"] is True
