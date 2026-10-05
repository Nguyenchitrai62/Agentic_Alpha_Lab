"""Tests for oc_bookic (research/tournament/oc_bookic). Lightweight consistency checks on results.json."""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "research" / "tournament" / "oc_bookic"
RES = HERE / "results.json"


def _load():
    return json.loads(RES.read_text())


def test_results_exists_and_schema():
    assert RES.exists(), "run research/tournament/oc_bookic/compute_bookic.py first"
    r = _load()
    for k in ("per_coin", "per_year", "windows", "totals_5y", "legs_5y",
              "regimes_5y", "coins_5y", "definitions"):
        assert k in r, k
    assert len(r["per_coin"]) == 25  # 5 years x 5 coins
    assert len(r["per_year"]) == 5
    assert len(r["windows"]) == 4


def test_legs_partition_totals():
    r = _load()
    for c in r["per_coin"]:
        assert abs(c["pnl_total"] - (c["pnl_long"] + c["pnl_short"])) < 5e-6, c
        assert abs((c["pnl_btc_above"] + c["pnl_btc_below"]) - c["pnl_total"]) < 5e-6, c
        assert abs((c["pnl_vol_high"] + c["pnl_vol_low"]) - c["pnl_total"]) < 5e-6, c
        ic = c["ic_42b"]
        assert ic is None or -1.0 <= ic <= 1.0, c


def test_year_and_5y_aggregation():
    r = _load()
    for y in r["per_year"]:
        rows = [c for c in r["per_coin"] if c["year"] == y["year"]]
        assert abs(sum(c["pnl_total"] for c in rows) - y["pnl_total"]) < 5e-6, y
    assert abs(sum(y["pnl_total"] for y in r["per_year"]) - r["totals_5y"]["pnl_5y_total"]) < 5e-6
    assert abs(sum(r["coins_5y"].values()) - r["totals_5y"]["pnl_5y_total"]) < 5e-6
    assert abs(r["legs_5y"]["long"] + r["legs_5y"]["short"] - r["totals_5y"]["pnl_5y_total"]) < 1e-5


def test_window_sizes():
    r = _load()
    nb = {w["window"]: w["n_bars"] for w in r["windows"]}
    assert nb["W4_2024-01-03"] == 6  # single day = six 4h bars
    assert nb["W3_2022-01-13__2022-01-22"] == 60
    assert nb["W1_2022-07-20__2022-11-10"] == 684
    assert nb["W2_2023-04-17__2023-06-14"] == 354
    for w in r["windows"]:
        coins = [w[s] for s in ("BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT")]
        assert abs(sum(coins) - w["total"]) < 5e-6, w
