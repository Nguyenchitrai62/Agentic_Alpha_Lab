"""Freeze the 3-book portfolio for prospective paper logging.

Books (capital thirds): (1) BTC regime_scaled 4h, (2) majors TSMOM 4h (per-asset Sharpe
selection, portfolio scale K from training DD 20%), (3) majors funding carry (long spot /
short perp). Trend books at 1.5x, carry at 3x. Selection uses all data before the freeze
anchor minus the 10-day embargo, exactly as in the out-of-sample evaluation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import agentic_alpha_lab.research_vf as V  # noqa: E402
from agentic_alpha_lab.backtest.ma_ribbon import NORMAL  # noqa: E402
from agentic_alpha_lab.backtest.portfolio import position_backtest, summarize_curve  # noqa: E402
from agentic_alpha_lab.oos_streams import context  # noqa: E402
from agentic_alpha_lab.vf_families import FAMILIES  # noqa: E402
import carry_lab as C  # noqa: E402

ANCHOR = "2026-09-24"
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
OUT = Path("artifacts/research/advisor_shadow/portfolio_v1.json")


def main():
    frozen = dict(anchor=ANCHOR, allocation=dict(regime_btc=1 / 3, tsmom_majors=1 / 3, carry=1 / 3), trend_leverage=1.5, carry_leverage=3.0)
    ctx = V.load_context_extended("4h")
    fn, grid = FAMILIES["regime_scaled"]
    r = V.run(ctx, fn, grid, anchors=(ANCHOR,), select_years=None)["per_anchor"][0]
    frozen["regime_btc"] = dict(params=r["selected"], scale=r["scale"])
    fn, grid = FAMILIES["tsmom"]
    ts, curves = {}, {}
    for s in MAJORS:
        c = context(s, "4h")
        w = V.windows(c, ANCHOR, None)
        best, score = None, -np.inf
        for p in grid:
            st = summarize_curve(position_backtest(c.bars, fn(c, p, fit_end=w["sel"][1]), *w["sel"], NORMAL, c.fr, c.fc))
            if st["changes"] >= 10 and st["sharpe"] > score:
                best, score = p, st["sharpe"]
        ts[s] = best
        res = position_backtest(c.bars, fn(c, best, fit_end=w["sel"][1]), *w["sel"], NORMAL, c.fr, c.fc)
        curves[s] = res["curve"]["equity"] / 100
    idx = sorted(set().union(*[c.index for c in curves.values()]))
    pr = pd.DataFrame({s: c.reindex(idx).ffill().pct_change().fillna(0.0) for s, c in curves.items()}).mean(axis=1)
    eq = (1 + pr).cumprod()
    dd = float(np.max(1 - eq / eq.cummax()))
    frozen["tsmom_majors"] = dict(params={s: {k: (list(v) if isinstance(v, tuple) else v) for k, v in p.items()} for s, p in ts.items()},
                                  K=float(np.floor(min(2.0, 0.20 / max(dd, 1e-6)) * 20) / 20), training_dd=round(dd, 4))
    carry = {}
    a = pd.Timestamp(ANCHOR, tz="UTC")
    for s in MAJORS:
        d = C.load(s)
        s0, s1 = d["idx"][0] + pd.Timedelta(days=30), a - pd.Timedelta(days=V.EMBARGO_DAYS)
        def score(q):
            rr = C.returns(d, C.position(d, q), 0.0004)
            rr = rr[(rr.index >= s0) & (rr.index <= s1)]
            return rr.mean() / rr.std() if rr.std() > 0 else -9
        carry[s] = max(C.GRID, key=score)
    frozen["carry"] = carry
    OUT.write_text(json.dumps(frozen, indent=1, default=str))
    print(json.dumps(frozen, indent=1, default=str))


if __name__ == "__main__":
    main()
