import numpy as np
import pandas as pd

from agentic_alpha_lab.backtest.ma_ribbon import NORMAL, Costs, backtest, funding_per_bar, ribbon_target, summarize
from agentic_alpha_lab.models.ma_ribbon_ml import EMBARGO, HORIZON, daily_features, labels, trainable_mask


def _bars(n=400, seed=0):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    open_ = np.concatenate([[100.0], close[:-1]])
    t = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame({
        "open_time": t, "close_time": t + pd.Timedelta("1D") - pd.Timedelta("1ms"),
        "open": open_, "high": np.maximum(open_, close) * 1.01, "low": np.minimum(open_, close) * 0.99,
        "close": close, "volume": 10.0, "quote_volume": 1000.0 * (1 + rng.random(n)), "taker_buy_volume": 5.0,
    })


def _funding(bars):
    times = pd.date_range(bars.open_time.iloc[0], bars.close_time.iloc[-1], freq="8h")
    return pd.DataFrame({"fundingTime": times, "fundingRate": 0.0001})


def test_ribbon_target_is_prefix_invariant():
    bars = _bars()
    for rule in ("cross", "close_above_slow", "ribbon"):
        base = ribbon_target(bars.close, 20, 50, rule, "long_short")
        changed = bars.close.copy()
        changed.iloc[300:] *= 3
        assert np.array_equal(base[:300], ribbon_target(changed, 20, 50, rule, "long_short")[:300])


def test_signal_fills_at_next_open_only():
    bars = _bars(20)
    target = np.zeros(20, dtype=int)
    target[5] = 1  # decided at close of bar 5
    fr, fc = funding_per_bar(bars, _funding(bars))
    res = backtest(bars, target, 0, 10, Costs(fee=0.0), np.zeros(20), np.zeros(20))
    (trade,) = res["trades"]
    assert trade["entry_index"] == 6 and trade["entry_price"] == bars.open[6]
    assert trade["exit_index"] == 7 and trade["exit_price"] == bars.open[7]
    assert np.isclose(res["equity"], 100 * bars.open[7] / bars.open[6])


def test_costs_reduce_equity_and_decompose():
    bars = _bars(60)
    target = np.ones(60, dtype=int)
    fr, fc = funding_per_bar(bars, _funding(bars))
    res = backtest(bars, target, 0, 50, NORMAL, fr, fc)
    assert res["fees"] > 0 and res["funding"] > 0
    assert np.isclose(res["equity"] - 100, res["gross"] - res["fees"] - res["funding"])
    s = summarize(res)
    assert s["dd_intrabar_pct"] >= s["dd_close_pct"]


def test_funding_assigned_to_bar_containing_time():
    bars = _bars(5)
    fr, fc = funding_per_bar(bars, _funding(bars))
    assert list(fc) == [3, 3, 3, 3, 3]


def test_features_are_prefix_invariant():
    bars = _bars(400)
    fund = _funding(bars)
    base = daily_features(bars, fund)
    changed = bars.copy()
    changed.loc[350:, ["open", "high", "low", "close"]] *= 2
    changed.loc[350:, "quote_volume"] *= 5
    fund2 = fund.copy()
    fund2.loc[fund2.fundingTime > bars.close_time[349], "fundingRate"] = 0.01
    alt = daily_features(changed, fund2)
    pd.testing.assert_frame_equal(base.iloc[:350], alt.iloc[:350])


def test_training_labels_realized_before_fit_with_embargo():
    bars = _bars(400)
    feats = daily_features(bars, _funding(bars))
    y = labels(bars)
    fit_index = 350
    mask = trainable_mask(feats, y, fit_index)
    rows = np.flatnonzero(mask)
    assert rows.max() + 1 + HORIZON <= fit_index - EMBARGO
    assert rows.max() == fit_index - EMBARGO - 1 - HORIZON
