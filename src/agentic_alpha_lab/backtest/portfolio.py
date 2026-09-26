"""Fractional target-position backtest used by the virtual-forward (vf) research program.

``target[t]`` is the desired signed notional as a fraction of equity, decided at
the close of bar ``t`` and traded at the open of bar ``t + 1``. Quantity is held
fixed while the target is unchanged (no drift rebalancing). Fees are charged on
traded notional; long funding follows ``Costs``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from agentic_alpha_lab.backtest.ma_ribbon import Costs


def position_backtest(
    bars: pd.DataFrame,
    target: np.ndarray,
    start: int,
    end: int,
    costs: Costs,
    funding_rate: np.ndarray,
    funding_count: np.ndarray,
    tol: float = 1e-9,
) -> dict:
    o, h, lo, c = (bars[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    last = min(end + 1, len(bars) - 1)
    cash = 100.0  # equity = cash + q * price (q signed units; cash absorbs notional)
    q = 0.0
    held_target = 0.0
    gross = fees = fund = 0.0
    turnover = 0.0
    n_changes = 0
    eq_close, eq_worst, expo = [], [], []
    for i in range(start + 1, last + 1):
        desired = float(target[i - 1])
        if abs(desired - held_target) > tol:
            equity_open = cash + q * o[i]
            new_q = desired * equity_open / o[i]
            dq = new_q - q
            px = o[i] * (1 + costs.slippage * np.sign(dq))
            fee = costs.fee * abs(dq) * px
            cash -= dq * px + fee
            gross -= dq * (px - o[i])  # slippage is a price cost, booked in gross
            fees += fee
            turnover += abs(dq) * px
            q, held_target = new_q, desired
            n_changes += 1
        if q != 0:
            if costs.funding_mode == "normal":
                paid = costs.flat_funding_rate * funding_count[i] * max(q, 0.0) * c[i]
            else:
                paid = funding_rate[i] * q * c[i]
            cash -= paid
            fund += paid
        eq_close.append(cash + q * c[i])
        eq_worst.append(cash + q * (lo[i] if q > 0 else h[i]))
        expo.append(q * c[i] / max(eq_close[-1], 1e-9))
    if q != 0:  # liquidate at the final close
        px = c[last] * (1 - costs.slippage * np.sign(q))
        fee = costs.fee * abs(q) * px
        cash += q * px - fee
        fees += fee
        eq_close[-1] = cash
        eq_worst[-1] = min(eq_worst[-1], cash)
    equity = cash
    idx = pd.DatetimeIndex(bars["close_time"].iloc[start + 1 : last + 1])
    curve = pd.DataFrame({"equity": eq_close, "worst": eq_worst, "exposure": expo}, index=idx)
    # price PnL = equity change minus costs
    gross_total = equity - 100.0 + fees + fund
    return dict(equity=equity, gross=gross_total, fees=fees, funding=fund, turnover=turnover, changes=n_changes, curve=curve)


def summarize_curve(res: dict) -> dict:
    curve = res["curve"]
    eq = curve["equity"].to_numpy()
    peaks = np.maximum.accumulate(np.concatenate([[100.0], eq]))[1:]
    daily = curve["equity"].resample("1D").last().dropna()
    prev = np.concatenate([[100.0], daily.to_numpy()[:-1]])
    rets = daily.to_numpy() / prev - 1
    days = max((curve.index[-1] - curve.index[0]).total_seconds() / 86400, 1.0)
    growth = res["equity"] / 100
    return dict(
        net_pct=100 * (growth - 1), gross_pct=res["gross"], fees_pct=res["fees"], funding_pct=res["funding"],
        monthly_geo_pct=100 * (growth ** (30.4375 / days) - 1) if growth > 0 else -100.0,
        sharpe=float(rets.mean() / rets.std() * np.sqrt(365)) if rets.std() > 0 else 0.0,
        dd_close_pct=100 * float(np.max(1 - eq / peaks)),
        dd_intrabar_pct=100 * float(np.max(1 - curve["worst"].to_numpy() / peaks)),
        changes=res["changes"], exposure_mean=float(np.mean(np.abs(curve["exposure"]))),
        turnover_x=res["turnover"] / 100, days=days,
    )
