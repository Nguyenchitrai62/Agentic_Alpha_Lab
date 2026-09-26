"""Human-readable advice for the vf combo candidate (4h EMA20/200 ribbon long + Donchian 55/10 L/S).

Advisory only: no order code. Levels are computed from closed bars; a decision at
the 4h close is executed at the next 4h open (limit at the open price, market
after 15 minutes if not traded through).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from agentic_alpha_lab.models.pattern_pipeline import daily_context, join_daily
from agentic_alpha_lab.research_vf import Context
from agentic_alpha_lab.vf_families import combo, donchian, trend_ribbon

CANDIDATE_ID = "vf_combo_fast20_don55_10_w0.5_k0.65"
PARAMS = dict(fast=20, entry=55, exit=10, gate="none", w=0.5)
SCALE = 0.65


def report(bars4h: pd.DataFrame, daily: pd.DataFrame) -> dict:
    bars4h = bars4h.reset_index(drop=True)
    ctx = Context("4h", bars4h, daily, pd.DataFrame(), np.zeros(len(bars4h)), np.zeros(len(bars4h)))
    trend = trend_ribbon(ctx, dict(fast=20, slow=200, gate="not_against"))
    don = donchian(ctx, dict(entry=55, exit=10, gate="none", shorts=True))
    tgt = combo(ctx, PARAMS) * SCALE
    c = bars4h["close"]
    e20 = float(c.ewm(span=20, adjust=False, min_periods=20).mean().iloc[-1])
    e200 = float(c.ewm(span=200, adjust=False, min_periods=200).mean().iloc[-1])
    hi55 = float(bars4h["high"].iloc[-55:].max())
    lo55 = float(bars4h["low"].iloc[-55:].min())
    hi10 = float(bars4h["high"].iloc[-10:].max())
    lo10 = float(bars4h["low"].iloc[-10:].min())
    d = join_daily(bars4h, daily, daily_context(daily)).iloc[-1]
    rib = int(d["d_ribbon"]) if np.isfinite(d["d_ribbon"]) else 0
    close = float(c.iloc[-1])
    t_state, d_state = int(trend[-1]), int(don[-1])
    notes = []
    if t_state == 1:
        notes.append(f"Trend book LONG; exits if a 4h close < EMA20 ({e20:,.0f}) or EMA20 < EMA200 ({e200:,.0f}).")
    else:
        cond = "EMA20 > EMA200" if e20 > e200 else f"EMA20 ({e20:,.0f}) back above EMA200 ({e200:,.0f})"
        notes.append(f"Trend book FLAT; enters on a fresh 4h close > EMA20 ({e20:,.0f}) with {cond}, if the daily ribbon is not bearish (now {rib:+d}).")
    if d_state == 1:
        notes.append(f"Donchian book LONG; exits if a 4h close <= 10-bar low ({lo10:,.0f}).")
    elif d_state == -1:
        notes.append(f"Donchian book SHORT; exits if a 4h close >= 10-bar high ({hi10:,.0f}).")
    else:
        short_ok = "allowed (daily ribbon bearish)" if rib == -1 else "blocked (daily ribbon not bearish)"
        notes.append(f"Donchian book FLAT; long on a 4h close > 55-bar high ({hi55:,.0f}); short on a close < 55-bar low ({lo55:,.0f}) {short_ok}.")
    prev = float(tgt[-2])
    now = float(tgt[-1])
    action = "HOLD" if abs(now - prev) < 1e-9 else ("INCREASE" if abs(now) > abs(prev) else "REDUCE") + (" LONG" if now > 0 or prev > 0 else " SHORT")
    return dict(
        candidate=CANDIDATE_ID, decision_bar_close=str(bars4h["close_time"].iloc[-1]), close_4h=close,
        target_fraction=round(now, 4), previous_target_fraction=round(prev, 4), action=action,
        books=dict(trend=t_state, donchian=d_state), daily_ribbon=rib,
        levels=dict(ema20_4h=round(e20, 1), ema200_4h=round(e200, 1), high55=round(hi55, 1), low55=round(lo55, 1), high10=round(hi10, 1), low10=round(lo10, 1)),
        notes=notes, execution="limit at next 4h open price; market after 15 minutes if not traded through",
        expectation="hidden-year check +13.0% (limit execution ~+12.8%), DD 9.0%; family expectation about +5% to +13% per year; not a guarantee",
    )
