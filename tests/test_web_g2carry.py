"""web_g2carry: deployed BOT 'G2 + carry' catalog entry, v376 plan alias, dip x1.7 and carry source.

FastAPI TestClient, no network, temporary DB and state files only.
"""

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
    catalog = importlib.import_module("backend.catalog")
    carry_view = importlib.import_module("backend.carry_view")
    db.init()
    return config, db, auth, catalog, carry_view


@pytest.fixture()
def web_client(backend):
    from fastapi.testclient import TestClient
    server = importlib.import_module("backend.server")
    return TestClient(server.app, base_url="https://testserver"), server, backend


def _bearer(auth, email):
    return {"Authorization": "Bearer " + auth.create_session(email)["access_token"]}


def test_g2c_catalog_entry_and_rank_first(backend):
    _, _, _, catalog, _ = backend
    g2c = catalog.PIPELINES["g2c"]
    assert g2c["product"] == "bot"
    assert g2c["candidate"] == "v376_R2_4P"  # same plan file as v376
    assert g2c["monthly_5y"] == pytest.approx(5.634, abs=0.01)
    assert g2c["monthly_last_year"] == pytest.approx(4.698, abs=0.01)
    assert g2c["gate_dd"] == pytest.approx(16.75, abs=0.01)
    assert g2c["win_all_hidden"] == pytest.approx(0.653, abs=0.02)
    assert g2c["losing_years"] == 0
    assert "g2c" in catalog.BOT and "g2c" not in catalog.MANUAL
    order = catalog.metric_order()
    bots = [p for p in order if p in catalog.BOT]
    assert bots[0] == "g2c"  # ranked first among BOT pipelines


def test_g2c_uses_v376_plan(web_client):
    client, server, (_, db, auth, catalog, _) = web_client
    admin = _bearer(auth, "admin@example.com")
    plan = {"pipeline": "v376", "coins": {"BTCUSDT": {"state": "flat"}}, "net_return_pct": 3.5, "freeze": "2026-10-06"}
    db.kv_set("trade_plan_v376", plan)
    server.clear_cache()
    assert catalog.require_pipeline({"role": "admin"}, "g2c") == "g2c"
    got_g2c = client.get("/api/trade_plan?pipeline=g2c", headers=admin).json()
    got_v376 = client.get("/api/trade_plan?pipeline=v376", headers=admin).json()
    assert got_g2c == got_v376 == plan
    ov = client.get("/api/overview?pipeline=g2c", headers=admin).json()
    assert ov["plan"] == plan  # same plan file
    summary = client.get("/api/pipelines_summary", headers=admin).json()
    assert "g2c" in summary
    wf = summary["g2c"]["walkforward"]
    assert wf["monthly_5y"] == pytest.approx(5.634, abs=0.01)
    assert wf["gate_dd"] == pytest.approx(16.75, abs=0.01)
    assert summary["g2c"]["paper_net_pct"] == pytest.approx(3.5)


def test_g2c_bot_grant_no_locks(web_client):
    client, _, (_, db, auth, catalog, _) = web_client
    admin, viewer = _bearer(auth, "admin@example.com"), _bearer(auth, "viewer@example.com")
    db.kv_set("trade_plan_v376", {"pipeline": "v376", "coins": {}})
    assert client.get("/api/trade_plan?pipeline=g2c", headers=viewer).status_code == 403
    assert client.post("/api/admin/users", headers=admin,
                       json={"email": "viewer@example.com", "pipelines": ["bot"]}).status_code == 200
    assert client.get("/api/trade_plan?pipeline=g2c", headers=viewer).status_code == 200
    summary = client.get("/api/pipelines_summary", headers=viewer).json()
    assert "g2c" in summary and not summary["g2c"]["locked"]


NOW = datetime.now(timezone.utc)


def _runner_state():
    entry = (NOW - timedelta(days=1)).isoformat()
    return {
        "ledger": {}, "links": {}, "last_exec_ms": 1, "seen_exec": [],
        "last_cycle_ms": 1.0, "carry": {
            "positions": {
                "BTC": {"coin": "BTC", "symbol": "BTCUSDT-25DEC26", "category": "linear",
                        "entry_time": entry, "delivery_ms": int((NOW + timedelta(days=70)).timestamp() * 1000),
                        "ann_basis": 0.053, "dte_days": 80.0, "equity_entry": 5000.0, "f": 0.25},
            },
            "entered": ["BTC:BTCUSDT-25DEC26"], "history": [], "skip_logged": {},
        },
    }


def _paper_carry_state():
    return {
        "tag": "carry", "equity_arg": 5000.0, "f": 0.5,
        "rule": {"coins": ["BTC"], "basis_threshold": 0.04}, "rule_sha256": "ab" * 32,
        "created_at": (NOW - timedelta(days=2)).isoformat(), "updated_at": NOW.isoformat(),
        "positions": {}, "history": [], "entered_symbols": [],
        "totals": {"n_entered": 0, "n_skipped": 1, "realised_pnl": 0.0, "fees_paid": 0.0},
    }


def test_carry_prefers_deployed_runner_then_falls_back(web_client, tmp_path, monkeypatch):
    client, server, (_, _, auth, _, carry_view) = web_client
    deployed = tmp_path / "deployed.json"
    deployed.write_text(json.dumps(_runner_state()), encoding="utf-8")
    paper = tmp_path / "paper.json"
    paper.write_text(json.dumps(_paper_carry_state()), encoding="utf-8")
    monkeypatch.setattr(carry_view, "deployed_state_path", lambda: deployed)
    monkeypatch.setattr(carry_view, "default_state_path", lambda: paper)
    server.clear_cache()
    body = client.get("/api/carry", headers=_bearer(auth, "viewer@example.com")).json()
    assert body["source"] == "paper_d17bfg2c"
    assert body["n_open"] == 1 and body["open_pairs"][0]["coin"] == "BTC"
    assert body["open_pairs"][0]["f"] == pytest.approx(0.25)
    deployed.write_text(json.dumps({"ledger": {}}), encoding="utf-8")  # no carry -> fallback
    server.clear_cache()
    body = client.get("/api/carry", headers=_bearer(auth, "viewer@example.com")).json()
    assert body["source"] == "paper_carry"
    assert body["n_open"] == 0


def test_frontend_g2c_strings():
    root = Path(__file__).resolve().parents[1]
    app = (root / "frontend" / "app.js").read_text(encoding="utf-8")
    assert '"g2c"' in app and "G2+carry" in app
    assert "plan ×1,7" in app or "× 1,7" in app or "1.7" in app
    assert "corr-size" in app and "dip-gross-cap" in app and "bear-book" in app
    assert "paper_d17bfg2c" in app
    assert "3,7" in app and "FINAL_REPORT_VI" in app  # honest MANUAL estimate note


def test_older_order_without_g2c_appends_instead_of_400(backend):
    _, _, _, catalog, _ = backend
    order9 = [p for p in catalog.metric_order() if p != "g2c"]  # older admin UI without the display alias
    locks9 = {p: False for p in order9}
    saved = catalog.save_policy({"order": order9, "locked": locks9, "revision": 0}, "admin@example.com")
    assert "g2c" in saved["order"] and len(saved["order"]) == len(catalog.PIPELINES)  # appended, not 400
    assert "g2c" not in catalog.plan_pipes()  # never a plan job / replay of its own
