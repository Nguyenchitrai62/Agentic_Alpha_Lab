"""carry_paper: prospective paper ledger for the frozen cash-and-carry sleeve.

Fake public client only (no network, no keys, no orders). Covers: entry on a
high basis, idempotent hold, skip when basis < 4 %, delivery settlement via
the delivery-price endpoint, no-eligible / delisted / API-error handling, and
the public-only guarantee.
"""
import importlib.util
import json
import math
import time
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "carry_paper", Path(__file__).resolve().parents[1] / "scripts" / "carry_paper.py")
cp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cp)

DAY = 86_400_000


@pytest.fixture(autouse=True)
def _synthetic_dates_are_quarterly(request, monkeypatch):
    """Logic tests use synthetic delivery dates (now + N days); the quarterly-cycle filter has its own test."""
    if "quarterly_filter" not in request.node.name:
        monkeypatch.setattr(cp, "is_quarterly_delivery", lambda ms: True)


class FakePublic:
    """Minimal Bybit V5 PUBLIC surface the ledger reads (instruments-info, tickers, delivery-price)."""

    def __init__(self, contracts, spots, futs, delivery=None, fail_first=()):
        # contracts: list of {symbol, category, coin, delivery_ms}
        self.contracts = list(contracts)
        self.spots = dict(spots)       # "BTCUSDT" -> mid
        self.futs = dict(futs)         # "BTC-..." -> mid
        self.delivery = dict(delivery or {})  # symbol -> delivery price
        self.fail_first = dict(fail_first)  # path -> remaining failures
        self.calls = []

    def public(self, path, **params):
        self.calls.append((path, dict(params)))
        if self.fail_first.get(path, 0) > 0:
            self.fail_first[path] -= 1
            raise RuntimeError("10006: Too many visits (fake rate limit)")
        if path == "/v5/market/instruments-info":
            cat = params.get("category")
            rows = []
            for c in self.contracts:
                if c["category"] != cat:
                    continue
                rows.append({"symbol": c["symbol"], "status": "Trading",
                             "baseCoin": c["coin"], "contractType": "LinearFutures",
                             "deliveryTime": str(c["delivery_ms"]), "deliveryFeeRate": "0.0002"})
            return {"list": rows, "nextPageCursor": ""}
        if path == "/v5/market/tickers":
            cat, sym = params.get("category"), params.get("symbol")
            px = self.spots.get(sym) if cat == "spot" else self.futs.get(sym)
            if px is None:
                return {"list": []}
            return {"list": [{"symbol": sym, "bid1Price": str(px), "ask1Price": str(px),
                              "lastPrice": str(px), "markPrice": str(px)}]}
        if path == "/v5/market/delivery-price":
            sym = params.get("symbol")
            if sym in self.delivery:
                return {"list": [{"symbol": sym, "deliveryPrice": str(self.delivery[sym]),
                                   "deliveryTime": "1"}]}
            return {"list": []}
        raise AssertionError(f"unexpected public path {path}")


def _contracts(now, front_dte=60, nxt_dte=150, coin="BTC", cat="linear"):
    return [
        {"symbol": f"{coin}-FRONT", "category": cat, "coin": coin,
         "delivery_ms": now + front_dte * DAY},
        {"symbol": f"{coin}-NEXT", "category": cat, "coin": coin,
         "delivery_ms": now + nxt_dte * DAY},
    ]


def _actions(sdir):
    p = Path(sdir) / "actions.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def test_rule_frozen_sha_and_fees():
    assert cp.RULE_PARAMS["basis_threshold"] == 0.04
    assert cp.RULE_PARAMS["roll_days"] == 7
    assert cp.RULE_PARAMS["fee_spot_taker"] == 0.001
    assert cp.RULE_PARAMS["fee_fut_entry"] == 0.00055
    assert cp.RULE_PARAMS["fee_fut_delivery"] == 0.0002
    assert abs(cp.RULE_PARAMS["fee_drag_total"] - 0.00275) < 1e-12
    sha = cp.rule_sha256()
    assert len(sha) == 64 and all(c in "0123456789abcdef" for c in sha)


def test_entry_hold_settle_flow(tmp_path):
    now = int(time.time() * 1000)
    dte = 90.0
    s, fwd = 60000.0, 60000.0 * math.exp(0.08 * dte / 365.0)  # 8 %/yr -> ENTER
    cli = FakePublic(_contracts(now, front_dte=90, nxt_dte=180), {"BTCUSDT": s}, {"BTC-FRONT": fwd})
    res = cp.run_once(cli, tmp_path, 5000.0, 0.5, "carry", now_ms=now)
    assert res["entered"] == 1
    st = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert "BTC" in st["positions"]
    pos = st["positions"]["BTC"]
    assert pos["symbol"] == "BTC-FRONT"  # first availability takes the front
    assert abs(pos["S_entry"] - s) < 1e-9 and abs(pos["F_entry"] - fwd) < 1e-9
    assert pos["ann_basis"] == pytest.approx(0.08, abs=1e-3)
    notion = 0.5 * 5000.0
    assert pos["spot_qty"] == pytest.approx(notion / s)
    assert pos["fut_qty"] == pytest.approx(notion / fwd)
    ops = [a["op"] for a in _actions(tmp_path)]
    assert "entry" in ops

    # hold: changed marks update mtm, no duplicate entry
    cli.spots["BTCUSDT"] = s * 1.01
    cli.futs["BTC-FRONT"] = fwd * 1.005
    res2 = cp.run_once(cli, tmp_path, 5000.0, 0.5, "carry", now_ms=now + 3600_000)
    assert res2["entered"] == 0 and res2["holding"] == 1
    st2 = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert st2["totals"]["n_entered"] == 1
    assert st2["positions"]["BTC"]["last_spot"] == pytest.approx(s * 1.01)

    # settle at delivery via the delivery-price endpoint
    s_del = s * 1.02
    cli.delivery["BTC-FRONT"] = s_del
    dlv_ms = st2["positions"]["BTC"]["delivery_ms"]
    res3 = cp.run_once(cli, tmp_path, 5000.0, 0.5, "carry", now_ms=dlv_ms + 1000)
    assert res3["settled"] == 1
    st3 = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert "BTC" not in st3["positions"] and len(st3["history"]) == 1
    tr = st3["history"][0]
    exp_alloc = (s_del - s) / s + (fwd - s_del) / fwd - 0.00275
    assert tr["realised_ret_alloc"] == pytest.approx(exp_alloc, abs=1e-6)
    assert tr["realised_pnl"] == pytest.approx(0.5 * 5000.0 * exp_alloc, abs=1e-3)
    assert tr["delivery_source"] == "delivery-price"
    assert st3["totals"]["realised_pnl"] == pytest.approx(tr["realised_pnl"])


def test_skip_when_basis_below_threshold(tmp_path):
    now = int(time.time() * 1000)
    dte = 90.0
    s, fwd = 60000.0, 60000.0 * math.exp(0.01 * dte / 365.0)  # 1 %/yr -> SKIP
    cli = FakePublic(_contracts(now), {"BTCUSDT": s}, {"BTC-FRONT": fwd})
    res = cp.run_once(cli, tmp_path, 5000.0, 0.5, "carry", now_ms=now)
    assert res["entered"] == 0 and res["skipped"] == 1
    st = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert "BTC" not in st["positions"]
    assert any(a["op"] == "skip" for a in _actions(tmp_path))


def test_roll_rule_next_quarter_when_front_near(tmp_path):
    now = int(time.time() * 1000)
    cons = _contracts(now, front_dte=3, nxt_dte=93)  # front <= 7d -> candidate NEXT
    dte = 93.0
    s, fwd = 60000.0, 60000.0 * math.exp(0.06 * dte / 365.0)
    cli = FakePublic(cons, {"BTCUSDT": s}, {"BTC-NEXT": fwd, "BTC-FRONT": s})
    res = cp.run_once(cli, tmp_path, 5000.0, 0.5, "carry", now_ms=now)
    assert res["entered"] == 1
    st = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert st["positions"]["BTC"]["symbol"] == "BTC-NEXT"


def test_no_eligible_delisted_and_api_error_never_crash(tmp_path):
    now = int(time.time() * 1000)
    # no contracts listed -> no_eligible, no crash
    cli = FakePublic([], {}, {})
    res = cp.run_once(cli, tmp_path, 5000.0, 0.5, "carry", now_ms=now)
    assert res["status"] == "ok"
    assert any(a["op"] == "no_eligible" for a in _actions(tmp_path))

    # stale file must not break idempotency: corrupt state is rebuilt, not raised
    (tmp_path / "state.json").write_text("{corrupt", encoding="utf-8")
    res = cp.run_once(FakePublic([], {}, {}), tmp_path, 5000.0, 0.5, "carry", now_ms=now)
    assert res["status"] == "ok"

    # delisted: open position whose contract left Trading -> hold with delisted note
    dte = 90.0
    s, fwd = 60000.0, 60000.0 * math.exp(0.08 * dte / 365.0)
    cli2 = FakePublic(_contracts(now), {"BTCUSDT": s}, {"BTC-FRONT": fwd})
    cp.run_once(cli2, tmp_path / "d2", 5000.0, 0.5, "carry", now_ms=now)
    gone = FakePublic([], {"BTCUSDT": s}, {"BTC-FRONT": fwd})  # contract delisted
    res = cp.run_once(gone, tmp_path / "d2", 5000.0, 0.5, "carry", now_ms=now + 1000)
    assert res["status"] == "ok"
    assert any(a["op"] == "delisted" for a in _actions(tmp_path / "d2"))

    # transient 10006 then success: retry/backoff recovers
    cli3 = FakePublic(_contracts(now), {"BTCUSDT": s}, {"BTC-FRONT": fwd},
                      fail_first={"/v5/market/instruments-info": 1})
    res = cp.run_once(cli3, tmp_path / "d3", 5000.0, 0.5, "carry", now_ms=now)
    assert res["status"] == "ok" and res["entered"] == 1

    # persistent failure: logged as error, still no raise
    class Boom:
        def public(self, path, **kw):
            raise RuntimeError("boom")
    res = cp.run_once(Boom(), tmp_path / "d4", 5000.0, 0.5, "carry", now_ms=now)
    assert res["status"] == "error"
    assert any(a["op"] == "error" for a in _actions(tmp_path / "d4"))


def test_public_only_never_places_orders(tmp_path):
    now = int(time.time() * 1000)
    dte = 90.0
    s, fwd = 60000.0, 60000.0 * math.exp(0.08 * dte / 365.0)
    cli = FakePublic(_contracts(now), {"BTCUSDT": s}, {"BTC-FRONT": fwd},
                     delivery={"BTC-FRONT": s * 1.01})
    cp.run_once(cli, tmp_path, 5000.0, 0.5, "carry", now_ms=now)
    for path, _ in cli.calls:
        assert path in ("/v5/market/instruments-info", "/v5/market/tickers",
                        "/v5/market/delivery-price"), path
        assert "order" not in path and "position" not in path


def test_quarterly_filter_only_last_friday_of_quarter_months():
    import datetime as dt
    c = cp

    def ms(s):
        return int(dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)

    assert c.is_quarterly_delivery(ms("2026-12-25T08:00"))
    assert c.is_quarterly_delivery(ms("2027-03-26T08:00"))
    assert not c.is_quarterly_delivery(ms("2026-10-16T08:00"))  # bi-weekly contract, not quarterly
    assert not c.is_quarterly_delivery(ms("2026-10-30T08:00"))  # monthly contract
