import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def test_advisor_matches_backtest_painting_and_is_causal():
    from pattern_lab_meta import primary_trades
    from pattern_lab_trend_risk import paint

    from agentic_alpha_lab.backtest.ma_ribbon import funding_per_bar, ribbon_target
    from agentic_alpha_lab.models.pattern_pipeline import daily_context, join_daily
    from agentic_alpha_lab.patterns.common import load_bars, load_funding
    from agentic_alpha_lab.signals.trend_advisor import advice, candidate_target

    try:
        bars, daily = load_bars("4h"), load_bars("1d")
    except FileNotFoundError:
        pytest.skip("local data not present")
    _, fc = funding_per_bar(bars, load_funding())
    lt = primary_trades(ribbon_target(bars["close"], 20, 200, "ribbon", "long", "EMA"), bars, fc)
    d = join_daily(bars, daily, daily_context(daily))["d_ribbon"].to_numpy()
    painted, _ = paint(len(bars), lt, d[lt.entry.to_numpy()] != -1, np.ones(len(lt)))
    live = candidate_target(bars, daily)
    last_closed_trade = int(lt.exit_decision.max())
    assert np.array_equal(painted[:last_closed_trade], live[:last_closed_trade])
    cut = len(bars) - 500
    dcut = daily[daily["close_time"] <= bars["close_time"].iloc[cut]]
    assert np.array_equal(candidate_target(bars.iloc[: cut + 1], dcut), live[: cut + 1])
    assert advice(bars, daily)["action"] in {"ENTER_LONG", "EXIT_TO_FLAT", "HOLD_LONG", "STAY_FLAT"}
