"""carry_calendar: read-only inverse-quarterly schedule (offline, fake API only).

No network, no keys, no orders. Covers: inverse-only quarterly listing
(linear + monthly/bi-weekly excluded), UTC/Vietnam delivery times, DTE +
annualised basis vs the frozen 4 %/yr threshold, roll window (<= 7d), owner
actions (sell the spot leg at delivery), --json output, and the public-only
guarantee.
"""
import datetime as dt
import importlib.util
import io
import json
import math
from contextlib import redirect_stdout
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "carry_calendar", Path(__file__).resolve().parents[1] / "scripts" / "carry_calendar.py")
cc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cc)

DAY = 86_400_000


def _ms(s: str) -> int:
    return int(dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


class FakePublic:
    """Minimal Bybit V5 PUBLIC surface the calendar reads (instruments-info, tickers)."""

    def __init__(self, contracts, spots, futs):
        self.contracts = list(contracts)  # {symbol, category, coin, delivery_ms}
        self.spots = dict(spots)
        self.futs = dict(futs)
        self.calls = []

    def public(self, path, **params):
        self.calls.append((path, dict(params)))
        if path == "/v5/market/instruments-info":
            cat = params.get("category")
            rows = []
            for c in self.contracts:
                if c["category"] != cat:
                    continue
                rows.append({"symbol": c["symbol"], "status": "Trading",
                             "baseCoin": c["coin"], "contractType": "InverseFutures",
                             "deliveryTime": str(c["delivery_ms"]), "deliveryFeeRate": "0.0005"})
            return {"list": rows, "nextPageCursor": ""}
        if path == "/v5/market/tickers":
            cat, sym = params.get("category"), params.get("symbol")
            px = self.spots.get(sym) if cat == "spot" else self.futs.get(sym)
            if px is None:
                return {"list": []}
            return {"list": [{"symbol": sym, "bid1Price": str(px), "ask1Price": str(px),
                               "lastPrice": str(px), "markPrice": str(px)}]}
        raise AssertionError(f"unexpected public path {path}")


def _client(s, f_dec, f_mar, s_eth=2700.0, f_eth_dec=None, f_eth_mar=None):
    dec = _ms("2026-12-25T08:00")
    mar = _ms("2027-03-26T08:00")
    mon = _ms("2026-10-30T08:00")  # monthly, not quarterly
    contracts = [
        {"symbol": "BTCUSDZ26", "category": "inverse", "coin": "BTC", "delivery_ms": dec},
        {"symbol": "BTCUSDH27", "category": "inverse", "coin": "BTC", "delivery_ms": mar},
        {"symbol": "BTCUSDT-25DEC26", "category": "linear", "coin": "BTC", "delivery_ms": dec},
        {"symbol": "BTCUSDMONTH", "category": "inverse", "coin": "BTC", "delivery_ms": mon},
        {"symbol": "ETHUSDZ26", "category": "inverse", "coin": "ETH", "delivery_ms": dec},
        {"symbol": "ETHUSDH27", "category": "inverse", "coin": "ETH", "delivery_ms": mar},
    ]
    dte_dec = (dec - NOW) / DAY
    spots = {"BTCUSDT": s, "ETHUSDT": s_eth}
    futs = {"BTCUSDZ26": f_dec, "BTCUSDH27": f_mar,
            "ETHUSDZ26": f_eth_dec or s_eth * math.exp(0.01 * dte_dec / 365.0),
            "ETHUSDH27": f_eth_mar or s_eth * 1.01,
            "BTCUSDMONTH": s * 1.001, "BTCUSDT-25DEC26": f_dec}
    return FakePublic(contracts, spots, futs)


NOW = _ms("2026-10-06T15:00")


def test_lists_only_inverse_quarterlies_with_both_timezones():
    s = 86000.0
    dte = (_ms("2026-12-25T08:00") - NOW) / DAY
    f = s * math.exp(0.08 * dte / 365.0)  # 8 %/yr -> ENTER-able
    cli = _client(s, f, f * 1.02)
    rows = cc.build_rows(cli, now_ms=NOW)
    syms = [r["symbol"] for r in rows]
    assert syms == ["BTCUSDZ26", "ETHUSDZ26", "BTCUSDH27", "ETHUSDH27"]
    assert "BTCUSDT-25DEC26" not in syms and "BTCUSDMONTH" not in syms
    front = rows[0]
    assert front["delivery_utc"] == "2026-12-25T08:00:00+00:00"
    assert front["delivery_vn"] == "2026-12-25T15:00:00+07:00"  # UTC+7
    assert front["dte_days"] == pytest.approx(dte, abs=0.01)
    assert front["ann_basis"] == pytest.approx(0.08, abs=1e-3)
    assert front["basis_threshold"] == 0.04
    assert front["above_threshold"] is True
    eth = [r for r in rows if r["symbol"] == "ETHUSDZ26"][0]
    assert eth["above_threshold"] is False  # 1 %/yr < 4 %/yr


def test_roll_window_and_owner_actions():
    s = 86000.0
    dte = (_ms("2026-12-25T08:00") - NOW) / DAY
    f = s * math.exp(0.08 * dte / 365.0)
    cli = _client(s, f, f * 1.02)
    rows = cc.build_rows(cli, now_ms=NOW)
    front = rows[0]
    assert front["in_roll_window"] is False  # ~80d left
    assert front["roll_start_utc"] == "2026-12-18T08:00:00+00:00"
    assert front["roll_start_vn"] == "2026-12-18T15:00:00+07:00"
    near = _ms("2026-12-20T08:00")  # 5d before delivery -> inside roll window
    rows2 = cc.build_rows(cli, now_ms=near)
    assert rows2[0]["in_roll_window"] is True
    txt = " ".join(rows2[0]["owner_actions"])
    assert "08:00 UTC" in txt and "15:00" in txt  # sell the spot leg at 08:00 UTC = 15:00 VN
    assert "BAN" in txt or "ban" in txt.lower()


def test_json_option_and_public_only():
    s = 86000.0
    dte = (_ms("2026-12-25T08:00") - NOW) / DAY
    f = s * math.exp(0.08 * dte / 365.0)
    cli = _client(s, f, f * 1.02)
    rows = cc.build_rows(cli, now_ms=NOW)
    for path, _ in cli.calls:
        assert path in ("/v5/market/instruments-info", "/v5/market/tickers"), path
        assert "order" not in path and "position" not in path
    # frozen rule import (never re-defined in the calendar module)
    assert cc.RULE_PARAMS["basis_threshold"] == 0.04
    assert cc.RULE_PARAMS["roll_days"] == 7
    assert "RULE_PARAMS = " not in Path(cc.__file__).read_text(encoding="utf-8")
    # text render mentions both zones + threshold
    txt = cc.render_text(rows, NOW)
    assert "UTC" in txt and "VN" in txt and "4%/yr" in txt
    # empty listing renders cleanly
    assert "no listed" in cc.render_text([], NOW).lower()
