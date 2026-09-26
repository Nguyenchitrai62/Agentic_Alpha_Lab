import numpy as np
import pandas as pd
import pytest

from agentic_alpha_lab.patterns.common import (
    DEV_DATA_END, assert_causal, benjamini_hochberg, event_study, forward_log_return, load_bars,
)


def _bars(n=300, seed=1, freq="4h"):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    open_ = np.concatenate([[100.0], close[:-1]])
    t = pd.date_range("2020-01-01", periods=n, freq=freq, tz="UTC")
    return pd.DataFrame({"open_time": t, "open": open_, "high": np.maximum(open_, close) * 1.002,
                         "low": np.minimum(open_, close) * 0.998, "close": close, "volume": 1.0})


def test_assert_causal_catches_centered_window():
    bars = _bars()
    good = lambda b: pd.DataFrame({"x": b["close"].rolling(5).mean()}, index=b.index)
    bad = lambda b: pd.DataFrame({"x": b["close"].rolling(5, center=True).mean()}, index=b.index)
    assert_causal(good, bars)
    with pytest.raises(AssertionError):
        assert_causal(bad, bars)


def test_forward_return_starts_at_next_open():
    bars = _bars(10)
    r = forward_log_return(bars, 2)
    assert np.isclose(r[0], np.log(bars.open[3] / bars.open[1]))
    assert r.iloc[-3:].isna().all()


def test_event_study_detects_planted_edge():
    bars = _bars(3000, freq="D")
    r = forward_log_return(bars, 1).to_numpy()
    ev = pd.DataFrame({"oracle": np.where(r > 0, 1, -1), "noise": np.random.default_rng(0).choice([-1, 0, 1], len(bars))})
    out = event_study(bars, ev, horizons=(1,))
    assert out.set_index("pattern").loc["oracle", "stable_significant"]
    assert not out.set_index("pattern").loc["noise", "stable_significant"]


def test_bh_is_monotone_and_bounded():
    q = benjamini_hochberg(np.array([0.01, 0.04, 0.03, 0.5]))
    assert np.all(q <= 1) and q[0] <= q[2] <= q[1] <= q[3]


def test_default_loader_hides_opened_year():
    try:
        bars = load_bars("1d")
    except FileNotFoundError:
        pytest.skip("local data not present")
    assert bars["open_time"].max() < DEV_DATA_END
