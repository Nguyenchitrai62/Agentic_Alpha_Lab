"""Live targets for the frozen 3-book portfolio (advisory only, no orders).

Inputs are closed bars fetched at run time. Output: per-asset perp weight (fraction of total
equity, signed) and spot weight (carry leg), plus each book's contribution.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from agentic_alpha_lab.backtest.ma_ribbon import funding_per_bar
from agentic_alpha_lab.research_vf import Context
from agentic_alpha_lab.vf_families import FAMILIES

FROZEN = Path("artifacts/research/advisor_shadow/portfolio_v1.json")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")


def _params(p: dict) -> dict:
    return {k: tuple(v) if isinstance(v, list) else v for k, v in p.items()}


def carry_on(funding: pd.DataFrame, q: dict) -> float:
    """Replays the carry state machine on published funding prints; returns 1.0 if in the trade now."""
    rates = funding.sort_values("fundingTime")["fundingRate"].astype(float)
    m = rates.rolling(q["win"] * 3, min_periods=3).mean().to_numpy()
    on = False
    for v in m:
        if not np.isfinite(v):
            continue
        if not on and v > q["enter"]:
            on = True
        elif on and v < q["exit"]:
            on = False
    return 1.0 if on else 0.0


def targets(data: dict[str, dict]) -> dict:
    """data[sym] = dict(bars4h=DataFrame, daily=DataFrame, funding=DataFrame[fundingTime, fundingRate])."""
    cfg = json.loads(FROZEN.read_text())
    alloc, lt, lc = cfg["allocation"], cfg["trend_leverage"], cfg["carry_leverage"]
    perp = {s: 0.0 for s in MAJORS}
    spot = {s: 0.0 for s in MAJORS}
    books = {}
    # book 1: BTC regime_scaled
    d = data["BTCUSDT"]
    b = d["bars4h"].reset_index(drop=True)
    fr, fc = funding_per_bar(b, d["funding"])
    ctx = Context("4h", b, d["daily"], d["funding"], fr, fc)
    fn, _ = FAMILIES["regime_scaled"]
    rs = float(fn(ctx, _params(cfg["regime_btc"]["params"]))[-1]) * cfg["regime_btc"]["scale"]
    books["regime_btc"] = rs
    perp["BTCUSDT"] += alloc["regime_btc"] * lt * rs
    # book 2: majors TSMOM, equal capital across assets, portfolio scale K
    fn, _ = FAMILIES["tsmom"]
    ts = {}
    for s in MAJORS:
        d = data[s]
        b = d["bars4h"].reset_index(drop=True)
        fr, fc = funding_per_bar(b, d["funding"])
        c = Context("4h", b, d["daily"], d["funding"], fr, fc)
        ts[s] = float(fn(c, _params(cfg["tsmom_majors"]["params"][s]))[-1])
        perp[s] += alloc["tsmom_majors"] * lt * cfg["tsmom_majors"]["K"] * ts[s] / len(MAJORS)
    books["tsmom_majors"] = ts
    # book 3: carry, long spot / short perp, equal capital across assets; capital per notional 1.2
    cr = {}
    for s in MAJORS:
        on = carry_on(data[s]["funding"], cfg["carry"][s])
        cr[s] = on
        notional = alloc["carry"] * lc * on / len(MAJORS) / 1.2
        perp[s] -= notional
        spot[s] += notional
    books["carry"] = cr
    return dict(perp_weight={k: round(v, 4) for k, v in perp.items()}, spot_weight={k: round(v, 4) for k, v in spot.items()},
                gross_perp=round(sum(abs(v) for v in perp.values()), 4), books=books)
