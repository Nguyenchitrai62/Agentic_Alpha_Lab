"""Causal moving-average ribbon signals and a trade-level position backtest.

A target position decided at the close of bar ``t`` is filled at the open of
bar ``t + 1``. Protocol: ``configs/ma_ribbon_r1_protocol.json``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Costs:
    fee: float = 0.0002
    slippage: float = 0.0
    funding_mode: str = "normal"  # "normal": long pays flat rate, short 0; "actual": historical rate
    flat_funding_rate: float = 0.0001


NORMAL = Costs()
STRESS = Costs(fee=0.0006, slippage=0.0005)
ACTUAL_FUNDING = Costs(funding_mode="actual")


def moving_average(close: pd.Series, period: int, kind: str = "SMA") -> pd.Series:
    if kind == "SMA":
        return close.rolling(period, min_periods=period).mean()
    if kind == "EMA":
        ema = close.ewm(span=period, adjust=False, min_periods=period).mean()
        return ema
    raise ValueError(kind)


def ribbon_target(
    close: pd.Series,
    fast: int,
    slow: int,
    rule: str,
    direction: str,
    kind: str = "SMA",
) -> np.ndarray:
    """Target position decided at each bar close; 0 during warm-up."""
    f = moving_average(close, fast, kind)
    s = moving_average(close, slow, kind)
    ready = (f.notna() & s.notna()).to_numpy()
    c, f, s = close.to_numpy(), f.to_numpy(), s.to_numpy()
    with np.errstate(invalid="ignore"):
        if rule == "cross":
            up, down = f > s, f < s
        elif rule == "close_above_slow":
            up, down = c > s, c < s
        elif rule == "ribbon":
            up, down = (c > f) & (f > s), (c < f) & (f < s)
        else:
            raise ValueError(rule)
    target = np.where(up, 1, 0)
    if direction == "long_short":
        target = np.where(down, -1, target)
    elif direction != "long":
        raise ValueError(direction)
    return np.where(ready, target, 0).astype(int)


def funding_per_bar(bars: pd.DataFrame, funding: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Sum of funding rates and event counts whose time falls in [open_i, open_{i+1})."""
    opens = bars["open_time"].to_numpy()
    times = funding["fundingTime"].to_numpy()
    idx = np.searchsorted(opens, times, side="right") - 1
    ok = (idx >= 0) & (idx < len(bars))
    rate = np.zeros(len(bars))
    count = np.zeros(len(bars))
    np.add.at(rate, idx[ok], funding["fundingRate"].to_numpy()[ok])
    np.add.at(count, idx[ok], 1)
    return rate, count


def backtest(
    bars: pd.DataFrame,
    target: np.ndarray,
    start: int,
    end: int,
    costs: Costs,
    funding_rate: np.ndarray,
    funding_count: np.ndarray,
    size: np.ndarray | None = None,
) -> dict:
    """Run decisions ``start..end`` (inclusive bar indices).

    The position decided at bar ``t`` is held over bar ``t + 1``. Any open
    position is liquidated at the close of bar ``end + 1`` (costs charged).
    ``size`` (fraction of equity, <= 1) is read at the entry decision and held
    until the position side changes.
    """
    o = bars["open"].to_numpy(float)
    h = bars["high"].to_numpy(float)
    lo = bars["low"].to_numpy(float)
    c = bars["close"].to_numpy(float)
    last = min(end + 1, len(bars) - 1)
    equity = 100.0
    pos, qty, entry = 0, 0.0, 0.0
    gross = fees = fund = 0.0
    trades: list[dict] = []
    close_eq, worst_eq, held = [], [], []

    def mark(price: float) -> float:
        return equity + pos * qty * (price - entry)

    for i in range(start + 1, last + 1):
        desired = int(target[i - 1])
        if desired != pos:
            if pos != 0:
                px = o[i] * (1 - costs.slippage * pos)
                pnl = pos * qty * (px - entry)
                fee = costs.fee * qty * px
                equity += pnl - fee
                gross += pnl
                fees += fee
                trades[-1].update(exit_index=i, exit_price=px, pnl=pnl)
                pos, qty = 0, 0.0
            if desired != 0:
                px = o[i] * (1 + costs.slippage * desired)
                frac = 1.0 if size is None else float(np.clip(size[i - 1], 0.0, 1.0))
                fee = costs.fee * equity * frac
                equity -= fee
                fees += fee
                pos, qty, entry = desired, frac * equity / px, px
                trades.append(dict(side=desired, entry_index=i, entry_price=px))
        if pos != 0:
            if costs.funding_mode == "normal":
                paid = costs.flat_funding_rate * funding_count[i] if pos > 0 else 0.0
            else:
                paid = pos * funding_rate[i]
            f = paid * qty * c[i]
            equity -= f
            fund += f
        close_eq.append(mark(c[i]))
        worst_eq.append(mark(lo[i] if pos > 0 else h[i]) if pos != 0 else mark(c[i]))
        held.append(pos)

    if pos != 0:
        px = c[last] * (1 - costs.slippage * pos)
        pnl = pos * qty * (px - entry)
        fee = costs.fee * qty * px
        equity += pnl - fee
        gross += pnl
        fees += fee
        trades[-1].update(exit_index=last, exit_price=px, pnl=pnl, forced=True)
        close_eq[-1] = equity
        worst_eq[-1] = min(worst_eq[-1], equity)

    times = bars["close_time"].iloc[start + 1 : last + 1]
    curve = pd.DataFrame({"equity": close_eq, "worst": worst_eq, "pos": held}, index=times.to_numpy())
    return dict(equity=equity, gross=gross, fees=fees, funding=fund, trades=trades, curve=curve)


def max_drawdown(values: np.ndarray, peaks_from: np.ndarray | None = None) -> float:
    peaks = np.maximum.accumulate(np.concatenate([[100.0], peaks_from if peaks_from is not None else values]))[1:]
    return float(np.max(1 - values / peaks)) if len(values) else 0.0


def summarize(result: dict) -> dict:
    curve = result["curve"]
    eq = curve["equity"].to_numpy()
    days = (curve.index[-1] - curve.index[0]) / np.timedelta64(1, "D") + (curve.index[1] - curve.index[0]) / np.timedelta64(1, "D")
    daily = curve["equity"].resample("1D").last().dropna()
    rets = np.diff(np.concatenate([[100.0], daily.to_numpy()])) / np.concatenate([[100.0], daily.to_numpy()[:-1]])
    months = days / 30.4375
    growth = result["equity"] / 100.0
    trades = result["trades"]
    longs = [t for t in trades if t["side"] > 0]
    shorts = [t for t in trades if t["side"] < 0]
    return dict(
        net_pct=100 * (growth - 1),
        gross_pct=result["gross"],
        fees_pct=result["fees"],
        funding_pct=result["funding"],
        cagr_pct=100 * (growth ** (365.25 / days) - 1) if growth > 0 else -100.0,
        monthly_geo_pct=100 * (growth ** (1 / months) - 1) if growth > 0 else -100.0,
        sharpe=float(np.mean(rets) / np.std(rets) * np.sqrt(365)) if np.std(rets) > 0 else 0.0,
        dd_close_pct=100 * max_drawdown(eq),
        dd_intrabar_pct=100 * max_drawdown(curve["worst"].to_numpy(), eq),
        trades=len(trades),
        long_trades=len(longs),
        short_trades=len(shorts),
        long_pnl=float(sum(t.get("pnl", 0.0) for t in longs)),
        short_pnl=float(sum(t.get("pnl", 0.0) for t in shorts)),
        win_rate=float(np.mean([t.get("pnl", 0) > 0 for t in trades])) if trades else float("nan"),
        exposure=float(np.mean(curve["pos"].to_numpy() != 0)),
        days=float(days),
    )


def daily_returns(result: dict) -> pd.Series:
    daily = result["curve"]["equity"].resample("1D").last().dropna()
    prev = np.concatenate([[100.0], daily.to_numpy()[:-1]])
    return pd.Series(daily.to_numpy() / prev - 1, index=daily.index)


def block_bootstrap_mean(x: np.ndarray, block: int = 20, reps: int = 2000, seed: int = 0) -> tuple[float, float]:
    """Circular block bootstrap 90% CI of the mean."""
    rng = np.random.default_rng(seed)
    n = len(x)
    nb = int(np.ceil(n / block))
    means = np.empty(reps)
    for r in range(reps):
        starts = rng.integers(0, n, nb)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:n] % n
        means[r] = x[idx].mean()
    return float(np.quantile(means, 0.05)), float(np.quantile(means, 0.95))
