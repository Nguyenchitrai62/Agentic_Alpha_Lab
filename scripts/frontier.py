"""Risk/return frontier from out-of-sample years only.

For each candidate family: five real anchors (2021..2025, expanding training windows, selection
and risk scale fixed before each year), forward-year curves chained into one 5-year
out-of-sample equity curve (normal costs). Then the book is rescaled by lambda (fractional
positions scale linearly) to find the lambda that reaches the user's target of 5% per month
(1.05^12 - 1 = +79.6%/yr), and the drawdown that lambda implies. Lowest implied drawdown = the
least risky way to the target that the evidence supports.

  python scripts/frontier.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import agentic_alpha_lab.research_vf as V
from agentic_alpha_lab.vf_families import FAMILIES

TARGET = 1.05 ** 12 - 1


def oos_returns(ctx, fam):
    fn, grid = FAMILIES[fam]
    r = V.run(ctx, fn, grid, anchors=V.ANCHORS, select_years=None)
    parts = []
    for p in r["per_anchor"]:
        c = p["_curves"]["normal"]
        parts.append(c.pct_change().fillna(c.iloc[0] - 1.0))
    s = pd.concat(parts)
    return s.groupby(s.index.floor("D")).apply(lambda x: float(np.prod(1 + x) - 1)), r


def metrics(ret):
    eq = (1 + ret).cumprod()
    yrs = len(ret) / 365
    cagr = eq.iloc[-1] ** (1 / yrs) - 1 if eq.iloc[-1] > 0 else -1
    dd = float(np.max(1 - eq / eq.cummax()))
    yearly = [float(np.prod(1 + g) - 1) for _, g in ret.groupby(np.arange(len(ret)) // 365)]
    return cagr, dd, yearly


def main():
    ctx = V.load_context_extended("4h")
    rows = []
    for fam in ("combo", "breadth", "regime_scaled", "tsmom", "pyramid", "trend_long", "donchian_long_short"):
        ret, _ = oos_returns(ctx, fam)
        cagr, dd, yearly = metrics(ret)
        lam_lo, lam_hi = 0.0, 20.0
        for _ in range(60):  # bisection on lambda for CAGR = target
            lam = (lam_lo + lam_hi) / 2
            c, d, _ = metrics(ret * lam)
            lam_lo, lam_hi = (lam, lam_hi) if c < TARGET else (lam_lo, lam)
        c_t, d_t, y_t = metrics(ret * lam)
        rows.append(dict(family=fam, oos_cagr=round(100 * cagr, 1), oos_maxdd=round(100 * dd, 1), calmar=round(cagr / dd, 2) if dd > 0 else np.nan,
                         yearly=[round(100 * y, 1) for y in yearly], lambda_for_5pct=round(lam, 2), dd_at_5pct=round(100 * d_t, 1),
                         worst_year_at_5pct=round(100 * min(y_t), 1)))
        print(rows[-1], flush=True)
    df = pd.DataFrame(rows).sort_values("dd_at_5pct")
    print("\n", df.to_string(index=False))
    df.to_csv("artifacts/research/vf/frontier.csv", index=False)


if __name__ == "__main__":
    main()
