"""Triple-barrier outcomes and a one-position bracket backtest (protocol pattern_lab_r1).

A decision at the close of bar ``t`` enters at ``open[t+1]``. Take-profit and
stop are ATR multiples from the entry; when both are touched in one bar the
stop wins. Unfilled barriers exit at the close of bar ``t + horizon``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from agentic_alpha_lab.backtest.ma_ribbon import Costs


def atr(bars: pd.DataFrame, period: int = 14) -> np.ndarray:
    h, lo, c = bars["high"].to_numpy(float), bars["low"].to_numpy(float), bars["close"].to_numpy(float)
    prev = np.concatenate([[np.nan], c[:-1]])
    tr = np.nanmax(np.vstack([h - lo, np.abs(h - prev), np.abs(lo - prev)]), axis=0)
    out = pd.Series(tr).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    return out.to_numpy()


@dataclass
class Outcomes:
    exit_index: np.ndarray  # shape (2, n): row 0 long, row 1 short
    exit_kind: np.ndarray  # 1 take-profit, -1 stop, 0 timeout, -9 unavailable
    exit_price: np.ndarray
    entry_price: np.ndarray
    stop_price: np.ndarray

    def label(self, side: int) -> np.ndarray:
        """1 if the trade is a winner (TP, or timeout above entry in the trade direction)."""
        r = 0 if side > 0 else 1
        kind = self.exit_kind[r]
        move = side * (self.exit_price[r] - self.entry_price)
        y = np.where(kind == 1, 1.0, np.where(kind == -1, 0.0, (move > 0).astype(float)))
        return np.where(kind == -9, np.nan, y)

    def gross_return(self, side: int) -> np.ndarray:
        r = 0 if side > 0 else 1
        return np.where(self.exit_kind[r] == -9, np.nan, side * (self.exit_price[r] / self.entry_price - 1))


def triple_barrier(bars: pd.DataFrame, tp_mult: float = 2.0, sl_mult: float = 1.0, horizon: int = 12, atr_period: int = 14) -> Outcomes:
    o, h, lo, c = (bars[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    a = atr(bars, atr_period)
    n = len(bars)
    exit_index = np.full((2, n), -1, dtype=int)
    exit_kind = np.full((2, n), -9, dtype=int)
    exit_price = np.full((2, n), np.nan)
    entry = np.full(n, np.nan)
    stop = np.full((2, n), np.nan)
    for t in range(n - 1 - horizon):
        if not np.isfinite(a[t]):
            continue
        e = o[t + 1]
        entry[t] = e
        for r, side in ((0, 1), (1, -1)):
            tp, sl = e + side * tp_mult * a[t], e - side * sl_mult * a[t]
            stop[r, t] = sl
            for j in range(t + 1, t + 1 + horizon):
                hit_sl = lo[j] <= sl if side > 0 else h[j] >= sl
                hit_tp = h[j] >= tp if side > 0 else lo[j] <= tp
                if hit_sl:
                    # a gap through the stop fills at the open
                    px = min(sl, o[j]) if side > 0 else max(sl, o[j])
                    exit_index[r, t], exit_kind[r, t], exit_price[r, t] = j, -1, px
                    break
                if hit_tp:
                    px = max(tp, o[j]) if side > 0 else min(tp, o[j])
                    exit_index[r, t], exit_kind[r, t], exit_price[r, t] = j, 1, px
                    break
            else:
                j = t + horizon
                exit_index[r, t], exit_kind[r, t], exit_price[r, t] = j, 0, c[j]
    return Outcomes(exit_index, exit_kind, exit_price, entry, stop)


def bracket_backtest(
    bars: pd.DataFrame,
    signal: np.ndarray,
    outcomes: Outcomes,
    start: int,
    end: int,
    costs: Costs,
    funding_count: np.ndarray,
) -> dict:
    """Take ``signal[t]`` in {-1,0,1} for decisions ``start..end`` while flat; one position at a time."""
    h, lo = bars["high"].to_numpy(float), bars["low"].to_numpy(float)
    c = bars["close"].to_numpy(float)
    equity = 100.0
    gross = fees = fund = 0.0
    trades = []
    curve_t, curve_eq, curve_worst = [], [], []
    t = start
    while t <= end:
        s = int(signal[t])
        r = 0 if s > 0 else 1
        if s == 0 or outcomes.exit_kind[r, t] == -9:
            t += 1
            continue
        kind, j = outcomes.exit_kind[r, t], outcomes.exit_index[r, t]
        entry = outcomes.entry_price[t] * (1 + costs.slippage * s)
        exit_px = outcomes.exit_price[r, t]
        if kind != 1:  # stop and timeout exits are market-like
            exit_px *= 1 - costs.slippage * s
        fee_in = costs.fee * equity
        equity_after_fee = equity - fee_in
        qty = equity_after_fee / entry
        f_paid = 0.0
        for k in range(t + 1, j + 1):
            if costs.funding_mode == "normal" and s > 0:
                f_paid += costs.flat_funding_rate * funding_count[k] * qty * c[k]
            worst = equity_after_fee - f_paid + s * qty * ((lo[k] if s > 0 else h[k]) - entry)
            mark = equity_after_fee - f_paid + s * qty * (c[k] - entry)
            curve_t.append(k)
            curve_worst.append(worst)
            curve_eq.append(mark)
        pnl = s * qty * (exit_px - entry)
        fee_out = costs.fee * qty * exit_px
        equity = equity_after_fee - f_paid + pnl - fee_out
        curve_eq[-1] = equity
        curve_worst[-1] = min(curve_worst[-1], equity)
        gross += pnl
        fees += fee_in + fee_out
        fund += f_paid
        trades.append(dict(side=s, decision=t, exit_index=int(j), kind=int(kind), pnl=pnl))
        t = j  # next decision at the close of the exit bar
    return dict(equity=equity, gross=gross, fees=fees, funding=fund, trades=trades,
                curve_index=np.array(curve_t, dtype=int), curve_equity=np.array(curve_eq), curve_worst=np.array(curve_worst))


def summarize_bracket(res: dict, bars: pd.DataFrame, start: int, end: int) -> dict:
    ot = bars["open_time"]
    days = (ot.iloc[min(end + 1, len(bars) - 1)] - ot.iloc[start]).total_seconds() / 86400
    growth = res["equity"] / 100
    eq = np.concatenate([[100.0], res["curve_equity"]])
    peaks = np.maximum.accumulate(eq)[1:]
    dd_close = float(np.max(1 - res["curve_equity"] / peaks)) if len(peaks) else 0.0
    dd_intra = float(np.max(1 - res["curve_worst"] / peaks)) if len(peaks) else 0.0
    # daily equity series for Sharpe (flat days carry equity forward)
    daily = pd.Series(100.0, index=pd.DatetimeIndex(ot.iloc[start : end + 2]).floor("D").unique())
    if len(res["curve_index"]):
        s = pd.Series(res["curve_equity"], index=pd.DatetimeIndex(ot.iloc[res["curve_index"]]).floor("D"))
        s = s.groupby(level=0).last()
        daily = s.reindex(daily.index).ffill().fillna(100.0)
    rets = daily.pct_change().dropna().to_numpy()
    tr = res["trades"]
    return dict(
        net_pct=100 * (growth - 1), gross_pct=res["gross"], fees_pct=res["fees"], funding_pct=res["funding"],
        monthly_geo_pct=100 * (growth ** (30.4375 / days) - 1) if growth > 0 and days > 0 else -100.0,
        sharpe=float(rets.mean() / rets.std() * np.sqrt(365)) if len(rets) > 1 and rets.std() > 0 else 0.0,
        dd_close_pct=100 * dd_close, dd_intrabar_pct=100 * dd_intra, trades=len(tr),
        long_trades=sum(t["side"] > 0 for t in tr), short_trades=sum(t["side"] < 0 for t in tr),
        win_rate=float(np.mean([t["pnl"] > 0 for t in tr])) if tr else float("nan"),
        tp_rate=float(np.mean([t["kind"] == 1 for t in tr])) if tr else float("nan"),
        days=days,
    )
