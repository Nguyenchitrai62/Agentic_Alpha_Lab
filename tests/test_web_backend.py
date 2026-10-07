"""Web backend: session tokens, roles and the SQLite schema (no network, temporary DB)."""

import importlib
import sys
from dataclasses import replace

import pytest


@pytest.fixture()
def backend(tmp_path, monkeypatch):
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


def test_every_host_requires_header_authentication(backend):
    _, _, auth = backend
    local = auth.current_user(_request("127.0.0.1", {"host": "127.0.0.1:8724"}))
    assert local is None
    assert auth.current_user(_request("127.0.0.1", {"host": "localhost:8724"})) is None
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


@pytest.fixture()
def web_client(backend):
    from fastapi.testclient import TestClient
    server = importlib.import_module("backend.server")
    return TestClient(server.app, base_url="https://testserver"), server, backend


def _bearer(auth, email):
    return {"Authorization": "Bearer " + auth.create_session(email)["access_token"]}


def test_google_login_opens_free_pipelines_without_approval(web_client, monkeypatch):
    client, server, (_, db, auth) = web_client
    monkeypatch.setattr(auth, "SETTINGS", replace(auth.SETTINGS, allow_any_google_viewer=True))
    monkeypatch.setattr(server, "SETTINGS", replace(server.SETTINGS, allow_any_google_viewer=True))
    monkeypatch.setattr(auth, "verify_google", lambda _: {"email": "new@example.com", "name": "New viewer"})
    response = client.post("/api/auth/google", headers={"Origin": "https://crypto.example.com"}, json={"credential": "verified-google"})
    assert response.status_code == 200
    pair = response.json()
    assert pair["user"]["role"] == "viewer"
    assert pair["user"]["allowed_pipelines"] == ["v342", "v340", "v315"] and pair["user"]["bot_access"] is False
    assert "refresh_token" not in pair
    assert "HttpOnly" in response.headers["set-cookie"]
    headers = {"Authorization": "Bearer " + pair["access_token"]}
    assert client.get("/api/pipelines_summary", headers=headers).status_code == 200
    for pipe in ["v342", "v315"]:
        assert client.get(f"/api/trade_plan?pipeline={pipe}", headers=headers).status_code == 200
    for pipe in ["v367", "v362", "v321", "v301", "v295"]:
        assert client.get(f"/api/trade_plan?pipeline={pipe}", headers=headers).status_code == 403
    assert client.get("/api/admin/users", headers=headers).status_code == 403
    assert client.get("/api/trade_plan?pipeline=v342").status_code == 401
    assert client.get("/api/public/config").json()["automatic_viewer_access"] is True


def test_existing_pending_session_gets_free_access_when_automatic_mode_enabled(web_client, monkeypatch):
    client, _, (_, db, auth) = web_client
    with db.write() as c:
        c.execute("INSERT INTO users(email,role,approved) VALUES('waiting@example.com','viewer',0)")
    pair = auth.create_session("waiting@example.com")
    assert pair["user"]["role"] == "pending"
    monkeypatch.setattr(auth, "SETTINGS", replace(auth.SETTINGS, allow_any_google_viewer=True))
    headers = {"Authorization": "Bearer " + pair["access_token"]}
    assert client.get("/api/trade_plan?pipeline=v342", headers=headers).status_code == 200
    assert client.get("/api/auth/me", headers=headers).json()["role"] == "viewer"
    renewed = client.post("/api/auth/refresh", headers={"Authorization": "Bearer " + pair["refresh_token"]}).json()
    assert renewed["user"]["allowed_pipelines"] == ["v342", "v340", "v315"]


@pytest.mark.parametrize("email", ["new@example.com", "viewer@example.com"])
def test_admin_revocation_overrides_automatic_and_allowlisted_access(web_client, monkeypatch, email):
    client, _, (_, _, auth) = web_client
    monkeypatch.setattr(auth, "SETTINGS", replace(auth.SETTINGS, allow_any_google_viewer=True))
    pair = auth.create_session(email)
    headers = {"Authorization": "Bearer " + pair["access_token"]}
    admin = _bearer(auth, "admin@example.com")
    client.get("/api/trade_plan?pipeline=v342", headers=headers)  # warm cache
    assert client.post("/api/admin/users", headers=admin, json={"email": email, "approved": False}).status_code == 200
    assert client.get("/api/trade_plan?pipeline=v342", headers=headers).status_code == 403
    blocked = client.get("/api/auth/me", headers=headers).json()
    assert blocked["role"] == "pending" and blocked["access_revoked"] and blocked["allowed_pipelines"] == []
    renewed = client.post("/api/auth/refresh", headers={"Authorization": "Bearer " + pair["refresh_token"]}).json()
    assert renewed["user"]["allowed_pipelines"] == []
    monkeypatch.setattr(auth, "verify_google", lambda _: {"email": email})
    assert auth.login("verified-google")["user"]["access_revoked"]  # logging in again cannot undo denial
    listed = next(u for u in client.get("/api/admin/users", headers=admin).json() if u["email"] == email)
    assert listed["access_revoked"] and not listed["approved"]
    assert client.post("/api/admin/users", headers=admin, json={"email": email, "approved": True}).status_code == 200
    assert client.get("/api/trade_plan?pipeline=v342", headers=headers).status_code == 200
    # SQL role/flags cannot revoke or create an ADMIN_EMAILS administrator.
    client.post("/api/admin/users", headers=admin, json={"email": "admin@example.com", "approved": False})
    assert client.get("/api/admin/users", headers=admin).status_code == 200


def test_user_access_migration_preserves_legacy_waiting_and_approved_accounts(backend):
    _, db, _ = backend
    with db.write() as c:
        c.execute("ALTER TABLE users DROP COLUMN access_revoked")
        c.executemany("INSERT INTO users(email,role,approved) VALUES(?,'viewer',?)", [("waiting@example.com", 0), ("old@example.com", 1)])
    db.init()
    db.init()  # idempotent migration
    assert db.rows("SELECT approved, access_revoked FROM users ORDER BY email") == [
        {"approved": 1, "access_revoked": 0}, {"approved": 0, "access_revoked": 0}]


def test_admin_order_and_locks_apply_to_existing_session_and_scheduler(web_client):
    client, _, (_, db, auth) = web_client
    admin, viewer = _bearer(auth, "admin@example.com"), _bearer(auth, "viewer@example.com")
    original = client.get("/api/admin/pipelines", headers=admin).json()
    assert client.get("/api/admin/pipelines", headers=admin).headers["cache-control"] == "no-store"
    assert original["automatic"] and original["revision"] == 0
    # Warm both caches before changing policy; the same viewer access token must acquire/lose rights immediately.
    client.get("/api/pipelines_summary", headers=viewer)
    client.get("/api/trade_plan?pipeline=v342", headers=viewer)
    order = ["g2c", "v315", "v367", "v342", "v301", "v362", "v321", "v295", "v340", "v376"]
    locks = {**original["locked"], "v367": False, "v342": True}
    payload = {"order": order, "locked": locks, "revision": 0}
    response = client.post("/api/admin/pipelines", headers=admin, json=payload)
    assert response.status_code == 200
    assert response.json() == {"order": order, "locked": locks, "automatic": False, "revision": 1}
    assert client.get("/api/trade_plan?pipeline=v367", headers=viewer).status_code == 200
    assert client.get("/api/trade_plan?pipeline=v342", headers=viewer).status_code == 403
    assert client.get("/api/auth/me", headers=viewer).json()["allowed_pipelines"] == ["v315", "v367", "v340"]
    summary = client.get("/api/pipelines_summary", headers=viewer).json()
    assert list(summary) == ["v315", "v367", "v342", "v362", "v340"] and summary["v342"]["locked"] and not summary["v367"]["locked"]
    assert client.get("/api/pipelines_summary", headers=admin).json()["v342"]["locked_for_viewers"]
    assert all(not p["locked"] for p in client.get("/api/pipelines_summary", headers=admin).json().values())
    catalog = importlib.reload(importlib.import_module("backend.catalog"))
    assert catalog.ranked() == order  # persisted, not process-local UI state
    pipeline = importlib.import_module("backend.pipeline")
    db.kv_set("plan_status_v315", {"completed_slot": "slot"})
    plan_rank = [p for p in order if p not in catalog.PLAN_ALIASES]  # g2c reuses v376's plan: never scheduled
    assert pipeline.plan_order("slot") == plan_rank[1:] + plan_rank[:1]
    # A stale admin tab cannot silently undo the change.
    assert client.post("/api/admin/pipelines", headers=admin, json=payload).status_code == 409
    assert catalog.ranked() == order
    # Switching back to automatic ranking keeps locks independently configured.
    payload.update(order=None, revision=1)
    assert client.post("/api/admin/pipelines", headers=admin, json=payload).status_code == 200
    assert catalog.policy()["automatic"] and catalog.policy()["locked"] == {p: v and p in catalog.MANUAL for p, v in locks.items()}


@pytest.mark.parametrize("email", [None, "viewer@example.com", "pending@example.com"])
def test_pipeline_settings_require_admin(web_client, email):
    client, _, (_, db, auth) = web_client
    headers = _bearer(auth, email) if email else {}
    for method in (client.get, client.post):
        assert method("/api/admin/pipelines", headers=headers).status_code in (401, 403)
    assert db.kv_get("pipeline_access_policy") is None


@pytest.mark.parametrize("invalid", [
    {"order": ["v301"]}, {"order": ["v301"] * 5}, {"order": {}},
    {"order": ["v301", "v295", "v285", "v269", {}]}, {"order": ["v301", "v295", "v285", "v269", "unknown"]},
    {"locked": {"v301": True}}, {"locked": {p: "false" for p in ("v301", "v295", "v285", "v269", "v266")}},
    {"revision": True}, {"revision": -1},
])
def test_pipeline_policy_validates_before_mutation(web_client, invalid):
    client, _, (_, db, auth) = web_client
    admin = _bearer(auth, "admin@example.com")
    policy = client.get("/api/admin/pipelines", headers=admin).json()
    payload = {"order": policy["order"], "locked": policy["locked"], "revision": 0, **invalid}
    assert client.post("/api/admin/pipelines", headers=admin, json=payload).status_code == 400
    assert db.kv_get("pipeline_access_policy") is None


def test_all_locked_and_all_unlocked_are_supported(web_client):
    client, _, (_, _, auth) = web_client
    admin, viewer = _bearer(auth, "admin@example.com"), _bearer(auth, "viewer@example.com")
    policy = client.get("/api/admin/pipelines", headers=admin).json()
    for revision, locked in enumerate((True, False)):
        payload = {"order": policy["order"], "locked": {p: locked for p in policy["order"]}, "revision": revision}
        assert client.post("/api/admin/pipelines", headers=admin, json=payload).status_code == 200
        n = 5  # MANUAL pipelines; the Bot tab needs the account's BOT grant
        assert len(client.get("/api/auth/me", headers=viewer).json()["allowed_pipelines"]) == (0 if locked else n)
        assert len(client.get("/api/pipelines_summary", headers=viewer).json()) == n
        for path in ("/api/trade_plan", "/api/overview"):
            assert client.get(path, headers=viewer).status_code == (403 if locked else 200)
            assert client.get(path, headers=admin).status_code == 200


def test_locked_pipeline_shows_full_historical_evaluation_without_signals(web_client):
    client, _, (_, db, auth) = web_client
    metrics = {"monthly_5y": 6.3, "monthly_dev4": 6.7, "monthly_last_year": 5.349,
               "gate_dd": 17.09, "dd_4h": 16.2, "dd_1m": 17.09, "win_dev": .61, "win_hidden": .558,
               "trades_dev": 200, "trades_hidden": 55, "losing_years": 0, "yearly": [["2021-09-24", 80, 17.09]],
               "win_all_dev": .66, "win_all_hidden": .63, "rungs_dev": 900, "rungs_hidden": 300}
    db.kv_set("summary_tm_v367", {**metrics, "coins": {"BTCUSDT": "SECRET"}, "events": ["SECRET"]})
    db.kv_set("trade_plan_v367", {"coins": {"BTCUSDT": "SECRET"}, "net_return_pct": 12, "freeze": "SECRET"})
    response = client.get("/api/pipelines_summary", headers=_bearer(auth, "viewer@example.com"))
    assert response.json()["v367"]["walkforward"] == metrics
    assert response.json()["v367"]["locked"]
    assert "SECRET" not in response.text and response.json()["v367"]["paper_net_pct"] is None
    assert "v301" not in response.json()  # BOT pipelines are not even listed without the BOT grant


@pytest.mark.parametrize("path", [
    "/api/trade_plan?pipeline=v301", "/api/overview?pipeline=v295",
    "/api/signals/latest?source=tm_v301", "/api/signals?source=paper_v295",
    "/api/signals?source=tm_v301&symbol=BTCUSDT",
    "/api/signals/at?source=paper_v301&t=999999",
    "/api/positions?symbol=BTCUSDT&source=tm_v295",
    "/api/trades?symbol=BTCUSDT&source=paper_v301",
    "/api/orders?source=tm_v301", "/api/orders/stats?source=paper_v295",
    "/api/equity?source=tm_v301", "/api/confidence",
    "/api/signals?source=live", "/api/orders?source=walkforward", "/api/equity?source=forward",
    "/api/trade_plan?pipeline=unknown", "/api/orders?source=paper_v301_G2",
])
def test_viewer_cannot_read_restricted_pipeline(web_client, path):
    client, _, (_, _, auth) = web_client
    assert client.get(path, headers=_bearer(auth, "viewer@example.com")).status_code == 403


def test_pipeline_permissions_and_cache_are_role_safe(web_client):
    client, _, (_, db, auth) = web_client
    admin, viewer = _bearer(auth, "admin@example.com"), _bearer(auth, "viewer@example.com")
    for pipe in ("v321", "v301", "v295", "v315", "v340", "v342", "v362", "v367", "v376"):
        db.kv_set(f"trade_plan_{pipe}", {"pipeline": pipe, "coins": {"secret": pipe}})
    assert len(client.get("/api/pipelines_summary", headers=admin).json()) == 10  # + g2c (reuses v376's plan)
    summary = client.get("/api/pipelines_summary", headers=viewer).json()
    assert len(summary) == 5  # MANUAL only; the two best MANUAL pipelines are locked by default
    assert [p for p in summary if summary[p]["locked"]] == ["v367", "v362"]
    assert summary["v367"]["paper_net_pct"] is None
    assert summary["v367"]["freeze"] is None
    assert client.get("/api/auth/me", headers=viewer).json()["allowed_pipelines"] == ["v342", "v340", "v315"]
    for pipe in ("v342", "v315"):
        assert client.get(f"/api/trade_plan?pipeline={pipe}", headers=viewer).json()["pipeline"] == pipe
    assert client.get("/api/trade_plan", headers=viewer).json()["pipeline"] == "v342"
    assert client.get("/api/trade_plan?pipeline=v301", headers=admin).status_code == 200
    assert client.get("/api/trade_plan?pipeline=v301", headers=viewer).status_code == 403
    assert client.get("/api/pipelines_summary", headers=_bearer(auth, "pending@example.com")).status_code == 403


@pytest.mark.parametrize("path", [
    "/api/overview", "/api/pipelines_summary", "/api/trade_plan", "/api/status", "/api/auth/me",
    "/api/signals/latest", "/api/signals", "/api/signals/at?t=1", "/api/signals/1",
    "/api/candles?symbol=BTCUSDT", "/api/positions?symbol=BTCUSDT", "/api/trades?symbol=BTCUSDT",
    "/api/orders", "/api/orders/stats", "/api/confidence", "/api/equity",
    "/api/admin/users", "/api/admin/jobs", "/api/admin/pipelines",
])
def test_data_api_rejects_missing_header_even_with_other_credentials(web_client, path):
    client, _, (_, _, auth) = web_client
    pair = auth.create_session("admin@example.com")
    client.cookies.set("aal_refresh", pair["refresh_token"])
    client.cookies.set("access_token", pair["access_token"])
    response = client.get(path, params={"token": pair["access_token"]},
                          headers={"X-Role": "admin", "X-User-Email": "admin@example.com"})
    assert response.status_code == 401


def test_new_routes_are_protected_by_default_and_health_has_no_data(web_client):
    client, server, (_, _, auth) = web_client
    @server.app.get("/api/new-data")
    def newly_added():
        return {"private": True}
    assert client.get("/api/new-data").status_code == 401
    assert client.get("/api/new-data", headers=_bearer(auth, "viewer@example.com")).status_code == 200
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("path", [
    "/api/trade_plan?pipeline=v367", "/api/overview?pipeline=v367",
    "/api/signals/latest?source=tm_v367", "/api/signals?source=paper_v367",
    "/api/positions?symbol=BTCUSDT&source=tm_v367", "/api/trades?symbol=BTCUSDT&source=paper_v367",
    "/api/orders?source=tm_v367", "/api/orders/stats?source=paper_v367", "/api/equity?source=tm_v367",
])
def test_individual_vip_grant_and_revocation_apply_to_existing_header_and_cache(web_client, path):
    client, _, (_, db, auth) = web_client
    admin = _bearer(auth, "admin@example.com")
    first, second = _bearer(auth, "viewer@example.com"), _bearer(auth, "other@example.com")
    client.post("/api/admin/users", headers=admin, json={"email": "other@example.com", "approved": True})
    db.kv_set("trade_plan_v367", {"pipeline": "v367", "coins": {}})
    assert client.get(path, headers=first).status_code == 403
    assert client.post("/api/admin/users", headers=first, json={"email": "viewer@example.com", "pipelines": ["v367"]}).status_code == 403
    grant = {"email": "viewer@example.com", "pipelines": ["v367"]}
    assert client.post("/api/admin/users", headers=admin, json=grant).status_code == 200
    db.init()  # schema initialization preserves grants
    assert client.get("/api/auth/me", headers=first).json()["allowed_pipelines"] == ["v367", "v342", "v340", "v315"]
    assert not client.get("/api/pipelines_summary", headers=first).json()["v367"]["locked"]
    assert client.get("/api/pipelines_summary", headers=second).json()["v367"]["locked"]
    assert client.get(path, headers=second).status_code == 403
    warmed = client.get(path, headers=first)
    assert warmed.status_code == 200
    assert client.get("/api/trade_plan?pipeline=v362", headers=first).status_code == 403
    assert client.post("/api/admin/users", headers=admin, json={**grant, "pipelines": []}).status_code == 200
    assert client.get(path, headers={**first, "If-None-Match": warmed.headers["etag"]}).status_code == 403
    assert client.get("/api/trade_plan?pipeline=v342", headers=first).status_code == 200


def test_account_revocation_overrides_individual_grants_and_refresh(web_client):
    client, _, (_, _, auth) = web_client
    admin = _bearer(auth, "admin@example.com")
    pair = auth.create_session("viewer@example.com")
    headers = {"Authorization": "Bearer " + pair["access_token"]}
    payload = {"email": "viewer@example.com", "pipelines": ["v367", "bot"]}
    client.post("/api/admin/users", headers=admin, json=payload)
    client.post("/api/admin/users", headers=admin, json={"email": payload["email"], "approved": False})
    client.post("/api/admin/users", headers=admin, json=payload)  # editing grants must not restore a revoked account
    assert client.get("/api/trade_plan?pipeline=v367", headers=headers).status_code == 403
    assert client.get("/api/trade_plan?pipeline=v321", headers=headers).status_code == 403
    renewed = client.post("/api/auth/refresh", headers={"Authorization": "Bearer " + pair["refresh_token"]})
    assert renewed.status_code == 200 and renewed.json()["user"]["allowed_pipelines"] == []
    assert renewed.json()["user"]["role"] == "pending"


def test_vip_grant_covers_signal_ids_without_unlocking_legacy_sources(web_client):
    client, _, (_, db, auth) = web_client
    admin, viewer = _bearer(auth, "admin@example.com"), _bearer(auth, "viewer@example.com")
    with db.write() as c:
        run_id = c.execute("INSERT INTO runs(source,decision_time,pipeline,created_at) VALUES('tm_v367',1,'v367',1)").lastrowid
    client.post("/api/admin/users", headers=admin, json={"email": "viewer@example.com", "pipelines": ["v367"]})
    assert client.get(f"/api/signals/{run_id}", headers=viewer).status_code == 200
    assert client.get("/api/signals/at?source=tm_v367&t=2024-01-01T00:00:00Z", headers=viewer).status_code == 200
    assert client.get("/api/signals?source=live", headers=viewer).status_code == 403
    client.post("/api/admin/users", headers=admin, json={"email": "viewer@example.com", "pipelines": []})
    assert client.get(f"/api/signals/{run_id}", headers=viewer).status_code == 403


def test_health_watchdog_staleness_preserves_private_details(web_client, monkeypatch):
    client, server, (config, _, _) = web_client
    monkeypatch.setattr(server, "SETTINGS", replace(config.SETTINGS, scheduler_enabled=True))
    monkeypatch.setattr(server, "_heartbeat", {"t": None})
    monkeypatch.setattr(server, "_started_at", server.time.time() - 2401)
    response = client.get("/health")
    assert response.status_code == 503 and response.json() == {"status": "unhealthy"}
    from datetime import datetime, timezone
    server._heartbeat["t"] = datetime.now(timezone.utc).isoformat()
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize("grants", [None, "v367", ["v367", "v367"], ["unknown"], [1], {"v367": True}, ["v301"]])
def test_invalid_grants_leave_existing_permissions_unchanged(web_client, grants):
    client, _, (_, _, auth) = web_client
    admin = _bearer(auth, "admin@example.com")
    payload = {"email": "viewer@example.com", "pipelines": ["v367"]}
    assert client.post("/api/admin/users", headers=admin, json=payload).status_code == 200
    assert client.post("/api/admin/users", headers=admin, json={**payload, "pipelines": grants}).status_code == 400
    users = client.get("/api/admin/users", headers=admin).json()
    assert next(u for u in users if u["email"] == payload["email"])["granted_pipelines"] == ["v367"]


@pytest.mark.parametrize("source", ["tm_v301", "paper_v301", "live"])
def test_signal_id_cache_cannot_bypass_permissions(web_client, source):
    client, _, (_, db, auth) = web_client
    with db.write() as c:
        run_id = c.execute("INSERT INTO runs(source, decision_time, pipeline, created_at) VALUES(?,1,'v301',1)",
                           (source,)).lastrowid
    path = f"/api/signals/{run_id}"
    warmed = client.get(path, headers=_bearer(auth, "admin@example.com"))
    assert warmed.status_code == 200
    response = client.get(path, headers={**_bearer(auth, "viewer@example.com"), "If-None-Match": warmed.headers["etag"]})
    assert response.status_code == 403


def test_expired_access_refresh_rotation_and_replay(web_client, monkeypatch):
    client, _, (_, db, auth) = web_client
    now = int(auth.time.time())
    monkeypatch.setattr(auth.time, "time", lambda: now)
    pair = auth.create_session("viewer@example.com")
    assert pair["expires_at"] == now + 900
    assert not db.one("SELECT 1 AS x FROM auth_refresh_tokens WHERE token_hash=?", (pair["refresh_token"],))
    monkeypatch.setattr(auth.time, "time", lambda: now + 901)
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer " + pair["access_token"]}).status_code == 401
    response = client.post("/api/auth/refresh", headers={"Authorization": "Bearer " + pair["refresh_token"]})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    renewed = response.json()
    assert "refresh_token" not in renewed
    rotated_refresh = client.cookies.get("aal_refresh")
    assert rotated_refresh != pair["refresh_token"]
    headers = {"Authorization": "Bearer " + renewed["access_token"]}
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer " + rotated_refresh}).status_code == 401
    assert client.post("/api/auth/refresh", headers={"Authorization": "Bearer " + pair["refresh_token"]}).status_code == 401
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert client.post("/api/auth/refresh", headers={"Authorization": "Bearer " + rotated_refresh}).status_code == 401


def test_logout_revokes_access_and_refresh(web_client):
    client, _, (_, _, auth) = web_client
    pair = auth.create_session("viewer@example.com")
    assert client.post("/api/auth/logout", headers={"Authorization": "Bearer " + pair["refresh_token"]}).status_code == 200
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer " + pair["access_token"]}).status_code == 401
    assert client.post("/api/auth/refresh", headers={"Authorization": "Bearer " + pair["refresh_token"]}).status_code == 401


def test_role_is_rechecked_for_access_and_refresh(web_client):
    client, _, (_, db, auth) = web_client
    with db.write() as c:
        c.execute("INSERT INTO users(email,role,approved) VALUES('approved@example.com','viewer',1)")
    pair = auth.create_session("approved@example.com")
    with db.write() as c:
        c.execute("UPDATE users SET approved=0 WHERE email='approved@example.com'")
    assert client.get("/api/trade_plan", headers={"Authorization": "Bearer " + pair["access_token"]}).status_code == 403
    renewed = client.post("/api/auth/refresh", headers={"Authorization": "Bearer " + pair["refresh_token"]}).json()
    assert renewed["user"]["role"] == "pending" and renewed["user"]["allowed_pipelines"] == []


@pytest.mark.parametrize("token", ["garbage", "a.b.c", "a.b.☃", "", "a.b.c.d"])
def test_malformed_tokens_are_unauthorized(web_client, token):
    client, _, _ = web_client
    # HTTP headers themselves must be ASCII.
    if token.isascii():
        assert client.get("/api/auth/me", headers={"Authorization": "Bearer " + token}).status_code == 401


def test_plan_priority_uses_product_rank_and_unfinished_cycle(backend):
    _, db, _ = backend
    pipe = importlib.import_module("backend.pipeline")
    slot = 100
    assert pipe.plan_order(slot) == ["v321", "v301", "v295", "v367", "v362", "v342", "v376", "v340", "v315"]
    db.kv_set("plan_status_v301", {"completed_slot": slot})
    assert pipe.plan_order(slot)[0] == "v321" and pipe.plan_order(slot)[-1] == "v301"
    db.kv_set("summary_tm_v342", {"monthly_last_year": 9, "gate_dd": 15, "win_hidden": .6})
    assert pipe.plan_order(slot)[0] == "v342"
    assert pipe.plan_order(slot + pipe.H4_MS)[0] == "v342"
    # DD and then win break return ties; dev4 results cannot affect the product rank.
    # g2c (deployed BOT) ranks first by explicit priority; plan jobs still exclude it.
    for p in pipe.catalog.PIPELINES:
        db.kv_set(f"summary_tm_{p}", {"monthly_last_year": 5, "gate_dd": 20, "win_hidden": .5})
    db.kv_set("summary_tm_v315", {"monthly_last_year": 5, "gate_dd": 19, "win_hidden": .5})
    db.kv_set("summary_tm_v362", {"monthly_last_year": 5, "gate_dd": 19, "win_hidden": .6, "monthly_dev4": -99})
    assert pipe.catalog.ranked()[:3] == ["g2c", "v362", "v315"]
    assert "g2c" not in pipe.plan_order(slot) and "g2c" not in pipe.catalog.plan_pipes()


def test_plan_failure_still_attempts_all_five_and_retries_unfinished(backend, tmp_path, monkeypatch):
    import json
    import subprocess
    _, db, _ = backend
    pipe = importlib.import_module("backend.pipeline")
    history = importlib.import_module("backend.history_tm")
    folder = tmp_path / "artifacts/research/advisor_shadow"
    folder.mkdir(parents=True)
    for name in pipe.catalog.PIPELINES:
        (folder / f"trade_plan_{name}.json").write_text(json.dumps({"coins": {}, "net_return_pct": 0, "bars": [],
                                                                 "decision_bar": str(__import__("pandas").Timestamp.now(tz="UTC").floor("4h"))}))
    monkeypatch.setattr(pipe, "ROOT", tmp_path)
    monkeypatch.setattr(history, "store_paper", lambda *a: None)
    calls = []
    def execute(cmd, **kwargs):
        candidate = cmd[cmd.index("--candidate") + 1]
        calls.append(candidate)
        if candidate == "v301_G2":
            raise subprocess.TimeoutExpired(cmd, 1800)
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(pipe.subprocess, "run", execute)
    monkeypatch.setattr(pipe.multiphase, "refresh", lambda db_, slot=None: calls.append("v376_R2_4P")
                        or db_.kv_set("plan_status_v376", {"completed_slot": slot, "completed_at": db_.now_ms()}) or "ok")
    with pytest.raises(RuntimeError, match="v301"):
        pipe.job_trade_plan()
    assert calls == ["v321_R2", "v301_G2", "v295_CS", "v367_M5", "v362_M4", "v342_M3", "v376_R2_4P", "v340_M2", "v315_M1"]
    assert pipe.plan_order(db.now_ms() // pipe.H4_MS * pipe.H4_MS)[0] == "v301"
    assert not db.kv_get("plan_status_v301")
    assert db.kv_get("plan_status_v315")["completed_at"]


def test_cookie_refresh_is_httponly_and_requires_trusted_origin(web_client):
    client, _, (_, _, auth) = web_client
    pair = auth.create_session("viewer@example.com")
    response = client.post("/api/auth/refresh", headers={"Authorization": "Bearer " + pair["refresh_token"]})
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=none" in cookie
    assert "refresh_token" not in response.json()
    assert client.post("/api/auth/refresh", headers={"Origin": "https://evil.example.com"}).status_code == 403
    assert client.post("/api/auth/refresh").status_code == 403
    assert client.post("/api/auth/refresh", headers={"Origin": "https://crypto.example.com"}).status_code == 200
    assert client.post("/api/auth/logout", headers={"Origin": "https://crypto.example.com"}).status_code == 200
    assert client.post("/api/auth/refresh", headers={"Origin": "https://crypto.example.com"}).status_code == 401


def test_tokens_in_query_or_cookie_cannot_authorize_signal_api(web_client):
    client, _, (_, _, auth) = web_client
    pair = auth.create_session("viewer@example.com")
    assert client.get("/api/trade_plan?token=" + pair["access_token"]).status_code == 401
    client.cookies.set("access_token", pair["access_token"])
    assert client.get("/api/trade_plan").status_code == 401


def test_cors_security_headers_and_request_limits(web_client):
    client, _, _ = web_client
    for origin, allowed in (("https://crypto.example.com", True), ("https://attacker.vercel.app", False)):
        response = client.options("/api/auth/refresh", headers={"Origin": origin, "Access-Control-Request-Method": "POST"})
        assert (response.headers.get("access-control-allow-origin") == origin) == allowed
    response = client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.post("/api/auth/google", content=b"x" * 65537).status_code == 413
    # Chunked bodies are bounded too, without relying on Content-Length.
    assert client.post("/api/auth/google", content=iter([b"x" * 40000, b"x" * 40000])).status_code == 413


def test_client_cannot_spoof_cf_ip_to_bypass_rate_limits(web_client):
    client, server, _ = web_client
    import time
    server._buckets["testclient"] = [0, time.time()]
    assert client.get("/health", headers={"CF-Connecting-IP": "1.2.3.4", "CF-Ray": "fake"}).status_code == 429


def test_scheduler_retries_failed_and_busy_cycles(backend, monkeypatch):
    server = importlib.import_module("backend.server")
    statuses, triggers, pauses = iter(["failed", "busy", "done"]), [], []
    def run(kind, fn, trigger):
        triggers.append(trigger)
        return {"status": next(statuses)}
    monkeypatch.setattr(server.pipeline, "run_job", run)
    monkeypatch.setattr(server.time, "sleep", pauses.append)
    server._run_cycle_until_done("catch-up")
    assert triggers == ["catch-up", "retry", "retry"] and pauses == [60, 60]


def test_access_permission_updates_when_ranking_changes(web_client):
    client, _, (_, db, auth) = web_client
    headers = _bearer(auth, "viewer@example.com")
    assert client.get("/api/trade_plan?pipeline=v342", headers=headers).status_code == 200
    db.kv_set("summary_tm_v342", {"monthly_last_year": 100, "gate_dd": 10, "win_hidden": .7})  # now a top-two MANUAL pipeline -> locked
    assert client.get("/api/trade_plan?pipeline=v342", headers=headers).status_code == 403


def test_saved_policy_from_older_catalogue_appends_new_pipeline_locked(backend):
    _, db, _ = backend
    catalog = importlib.import_module("backend.catalog")
    old = ["v266", "v301", "v269", "v295", "v285", "v342"]  # an older catalogue (v266 / v269 / v285 retired since)
    db.kv_set("pipeline_access_policy", {"order": old, "locked": {p: p == "v301" for p in old}, "revision": 3})
    pol = catalog.policy()
    assert pol["order"] == ["v301", "v295", "v342", "g2c", "v321", "v367", "v362", "v376", "v340", "v315"]
    # MANUAL pipelines missing from the saved locks start locked; bots never carry a lock
    assert pol["locked"] == {"v301": False, "v295": False, "v342": False, "g2c": False, "v321": False, "v367": True, "v362": True,
                             "v376": False, "v340": True, "v315": True}
    assert catalog.allowed({"role": "viewer", "email": "nobody@example.com"}) == ["v342"]


def test_bot_tab_is_an_account_grant_without_pipeline_locks(web_client):
    client, _, (_, db, auth) = web_client
    admin, viewer = _bearer(auth, "admin@example.com"), _bearer(auth, "viewer@example.com")
    for pipe in ("v321", "v301", "v295"):
        db.kv_set(f"trade_plan_{pipe}", {"pipeline": pipe, "coins": {}})
    me = client.get("/api/auth/me", headers=viewer).json()
    assert me["bot_access"] is False and not set(me["allowed_pipelines"]) & {"g2c", "v321", "v301", "v295"}
    assert client.get("/api/trade_plan?pipeline=v321", headers=viewer).status_code == 403
    assert client.post("/api/admin/users", headers=admin, json={"email": "viewer@example.com", "pipelines": ["v321"]}).status_code == 400
    assert client.post("/api/admin/users", headers=admin, json={"email": "viewer@example.com", "pipelines": ["bot"]}).status_code == 200
    me = client.get("/api/auth/me", headers=viewer).json()
    assert me["bot_access"] is True and me["allowed_pipelines"] == ["g2c", "v321", "v301", "v295", "v342", "v376", "v340", "v315"]
    summary = client.get("/api/pipelines_summary", headers=viewer).json()
    assert all(not summary[p]["locked"] for p in ("g2c", "v321", "v301", "v295")) and summary["v367"]["locked"]
    for pipe in ("g2c", "v321", "v301", "v295"):
        assert client.get(f"/api/trade_plan?pipeline={pipe}", headers=viewer).status_code == 200
    assert client.get("/api/auth/me", headers=admin).json()["bot_access"] is True
    assert client.post("/api/admin/users", headers=admin, json={"email": "viewer@example.com", "pipelines": []}).status_code == 200
    assert client.get("/api/trade_plan?pipeline=v321", headers=viewer).status_code == 403
