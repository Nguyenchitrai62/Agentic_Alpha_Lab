"""ops_festale (2026-10-06): the plan response must carry a generation timestamp
so the UI can warn when the plan is stale; the UI must show a Vietnamese
staleness/offline banner. FastAPI TestClient, no network."""

import importlib
import sys
from datetime import datetime, timezone

import pytest


@pytest.fixture()
def web_client(tmp_path, monkeypatch):
    monkeypatch.setenv("WEB_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("ADMIN_EMAILS", "Admin@Example.com")
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
    importlib.import_module("backend.config")
    db = importlib.import_module("backend.db")
    auth = importlib.import_module("backend.auth")
    db.init()
    from fastapi.testclient import TestClient
    server = importlib.import_module("backend.server")
    return TestClient(server.app, base_url="https://testserver"), server, db, auth


def _viewer(auth):
    return {"Authorization": "Bearer " + auth.create_session("viewer@example.com")["access_token"]}


def test_trade_plan_carries_generation_timestamp(web_client):
    client, _, db, auth = web_client
    now = datetime.now(timezone.utc).isoformat()
    plan = {"pipeline": "v342", "generated_at": now, "decision_bar": now,
            "next_decision": now, "freeze": now, "coins": {}, "net_return_pct": 1.5}
    db.kv_set("trade_plan_v342", plan)
    r = client.get("/api/trade_plan?pipeline=v342", headers=_viewer(auth))
    assert r.status_code == 200
    body = r.json()
    for field in ("generated_at", "decision_bar", "next_decision"):
        assert body.get(field), f"trade_plan lacks {field}"
        datetime.fromisoformat(str(body[field]).replace("Z", "+00:00"))
    assert body["coins"] == {} and body["net_return_pct"] == 1.5  # existing fields unchanged


def test_frontend_staleness_banner_present():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    html = (root / "frontend/index.html").read_text(encoding="utf-8")
    js = (root / "frontend/app.js").read_text(encoding="utf-8")
    css = (root / "frontend/styles.css").read_text(encoding="utf-8")
    assert "planFreshBanner" in html and "planFreshBannerLive" in html
    assert "KHÔNG đặt lệnh mới" in js and "Mất kết nối máy chủ" in js
    assert "75 * 60 * 1000" in js and "270 * 60 * 1000" in js  # 1h15m warn / 4h30m crit
    assert "fresh-banner" in css
