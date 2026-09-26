import numpy as np
import pandas as pd
import pytest

from agentic_alpha_lab.backtest.ma_ribbon import NORMAL, Costs
from agentic_alpha_lab.backtest.portfolio import position_backtest, summarize_curve


def _bars(n=600, seed=3):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, n)))
    open_ = np.concatenate([[100.0], close[:-1]])
    t = pd.date_range("2020-01-01", periods=n, freq="4h", tz="UTC")
    return pd.DataFrame({"open_time": t, "close_time": t + pd.Timedelta("4h") - pd.Timedelta("1ms"), "open": open_,
                         "high": np.maximum(open_, close) * 1.003, "low": np.minimum(open_, close) * 0.997, "close": close,
                         "volume": 1.0, "quote_volume": 100.0, "taker_buy_volume": 0.5})


def test_position_backtest_fills_next_open_and_accounts_costs():
    b = _bars(20)
    tgt = np.zeros(20)
    tgt[5:8] = 0.5  # decided at close of 5, traded at open 6; flat decided at 8 -> exit open 9
    zeros = np.zeros(20)
    res = position_backtest(b, tgt, 0, 15, Costs(fee=0.0), zeros, zeros)
    expected = 100 * (1 + 0.5 * (b.open[9] / b.open[6] - 1))
    assert np.isclose(res["equity"], expected)
    res_fee = position_backtest(b, tgt, 0, 15, Costs(fee=0.001), zeros, zeros)
    assert res_fee["equity"] < res["equity"] and np.isclose(res_fee["equity"] - 100, res_fee["gross"] - res_fee["fees"] - res_fee["funding"])


def test_short_fixed_quantity_no_volatility_drag():
    b = _bars(10)
    b.loc[:, "open"] = [100, 100, 50, 100, 100, 100, 100, 100, 100, 100]
    b.loc[:, "close"] = b["open"].shift(-1).fillna(100)
    b.loc[:, "high"] = b[["open", "close"]].max(axis=1)
    b.loc[:, "low"] = b[["open", "close"]].min(axis=1)
    tgt = np.zeros(10)
    tgt[0:3] = -1.0  # short from open 1 (100) to open 4 (100)
    zeros = np.zeros(10)
    res = position_backtest(b, tgt, 0, 6, Costs(fee=0.0), zeros, zeros)
    assert np.isclose(res["equity"], 100.0)


def _ctx(bars):
    from agentic_alpha_lab.research_vf import Context
    daily = bars.iloc[5::6].reset_index(drop=True).copy()  # coarse stand-in daily bars closing at 4h closes
    f = pd.DataFrame({"fundingTime": bars["open_time"], "fundingRate": 0.0001})
    return Context("4h", bars, daily, f, np.zeros(len(bars)), np.ones(len(bars)))


@pytest.mark.parametrize("family", ["trend_long", "trend_long_short", "donchian_long_short", "combo", "trend_hyst", "rotation", "multibook"])
def test_families_are_prefix_invariant(family):
    from agentic_alpha_lab.vf_families import FAMILIES
    bars = _bars(1500)
    fn, grid = FAMILIES[family]
    p = grid[0]
    full = fn(_ctx(bars), p, fit_end=1000)
    cut = 1200
    part = fn(_ctx(bars.iloc[: cut + 1].reset_index(drop=True)), p, fit_end=1000)
    assert np.allclose(full[: cut + 1], part, equal_nan=True)


def test_selection_never_sees_hidden_window():
    from agentic_alpha_lab import research_vf as V
    bars = _bars(4000)
    bars["open_time"] = pd.date_range("2023-01-01", periods=4000, freq="4h", tz="UTC")
    bars["close_time"] = bars["open_time"] + pd.Timedelta("4h") - pd.Timedelta("1ms")
    ctx = _ctx(bars)
    seen = []

    def fn(c, p, fit_end=None):
        seen.append(fit_end)
        return np.ones(len(c.bars)) * p["x"]

    w = V.windows(ctx, "2024-06-01", None)
    V.run(ctx, fn, [dict(x=0.5), dict(x=1.0)], anchors=("2024-06-01",), min_changes=0)
    sel_calls = seen[:2]
    assert all(f == w["sel"][1] for f in sel_calls)
    assert bars["open_time"].iloc[w["sel"][1]] < pd.Timestamp("2024-06-01", tz="UTC") - pd.Timedelta(days=V.EMBARGO_DAYS - 1)
    assert seen[-1] == w["fwd"][0]


def test_combo_report_matches_family_target():
    from agentic_alpha_lab.signals.combo_advisor import PARAMS, SCALE, report
    from agentic_alpha_lab.vf_families import combo
    bars = _bars(1500)
    ctx = _ctx(bars)
    r = report(bars, ctx.daily)
    tgt = combo(_ctx(bars), PARAMS) * SCALE
    assert np.isclose(r["target_fraction"], round(float(tgt[-1]), 4))
    assert np.isclose(r["previous_target_fraction"], round(float(tgt[-2]), 4))
    assert r["notes"] and r["levels"]["ema20_4h"] > 0
