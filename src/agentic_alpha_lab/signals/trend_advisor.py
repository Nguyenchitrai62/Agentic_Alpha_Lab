"""Frozen advisory candidate from pattern_lab_r4 (variant R0 = r3 B, size 0.65).

Rule, decided at each closed 4h bar:
- a long starts when the 4h close > EMA20 > EMA200 condition turns on, but only
  if the last closed daily bar is not in a bearish ribbon (close < SMA50 < SMA200);
- the long is held until the 4h condition turns off; otherwise flat.
Entry/exit fill at the next 4h open. Advisory only: no order code.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from agentic_alpha_lab.backtest.ma_ribbon import ribbon_target
from agentic_alpha_lab.models.pattern_pipeline import daily_context, join_daily

CANDIDATE_ID = "pattern_lab_r4_R0_scaled_0.65"
SIZE = 0.65


def candidate_target(bars4h: pd.DataFrame, daily: pd.DataFrame) -> np.ndarray:
    primary = ribbon_target(bars4h["close"], 20, 200, "ribbon", "long", "EMA")
    d_rib = join_daily(bars4h, daily, daily_context(daily))["d_ribbon"].to_numpy()
    out = np.zeros(len(primary), dtype=int)
    holding = False
    for t in range(len(primary)):
        started = primary[t] == 1 and (t == 0 or primary[t - 1] != 1)
        if primary[t] != 1:
            holding = False
        elif started:
            holding = d_rib[t] != -1
        out[t] = 1 if holding else 0
    return out


def advice(bars4h: pd.DataFrame, daily: pd.DataFrame) -> dict:
    """State at the last closed 4h bar."""
    tgt = candidate_target(bars4h, daily)
    c = bars4h["close"]
    e20 = c.ewm(span=20, adjust=False, min_periods=20).mean().iloc[-1]
    e200 = c.ewm(span=200, adjust=False, min_periods=200).mean().iloc[-1]
    ctx = join_daily(bars4h, daily, daily_context(daily)).iloc[-1]
    prev = int(tgt[-2]) if len(tgt) > 1 else 0
    now = int(tgt[-1])
    action = {(0, 1): "ENTER_LONG", (1, 0): "EXIT_TO_FLAT", (1, 1): "HOLD_LONG", (0, 0): "STAY_FLAT"}[(prev, now)]
    return dict(
        candidate=CANDIDATE_ID, decision_bar_close=str(bars4h["close_time"].iloc[-1]), action=action,
        target_position=now, size_fraction_of_equity=SIZE if now else 0.0, fill="next 4h open",
        close_4h=float(c.iloc[-1]), ema20_4h=float(e20), ema200_4h=float(e200),
        daily_ribbon=None if np.isnan(ctx["d_ribbon"]) else int(ctx["d_ribbon"]),
        daily_dist_sma50=float(ctx["d_dist_sma50"]), daily_dist_sma200=float(ctx["d_dist_sma200"]),
    )
