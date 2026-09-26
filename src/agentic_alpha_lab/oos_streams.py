"""Out-of-sample daily return streams for portfolio construction (five real anchors, expanding windows).

Each stream: for every anchor 2021..2025 the family's parameters and risk scale are chosen on data
before the anchor (10-day embargo), the next real year is traded, and the forward-year returns are
chained. Streams are cached under artifacts/research/streams/<name>.parquet.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

import agentic_alpha_lab.research_vf as V
from agentic_alpha_lab.backtest.ma_ribbon import NORMAL, funding_per_bar
from agentic_alpha_lab.backtest.portfolio import position_backtest, summarize_curve
from agentic_alpha_lab.vf_families import FAMILIES

CACHE = Path("artifacts/research/streams")
XS = Path("data/raw/xs_universe_20260924")
MAJORS_1H = Path("data/raw/majors_intraday_20260924")


def context(sym: str, tf: str) -> V.Context:
    if sym == "BTCUSDT":
        return V.load_context_extended(tf) if tf in ("4h", "1d", "1h") else V.load_context(tf)
    if tf == "1h":
        b = pd.read_parquet(MAJORS_1H / f"{sym}_1h.parquet")
    else:
        b = pd.read_parquet(XS / f"{sym}_{tf}.parquet")
    b["open_time"] = pd.to_datetime(b["open_time"], utc=True)
    b["close_time"] = pd.to_datetime(b["close_time"], utc=True)
    b = b.sort_values("open_time").reset_index(drop=True)
    d = pd.read_parquet(XS / f"{sym}_1d.parquet")
    f = pd.read_parquet(XS / f"{sym}_funding.parquet")
    fr, fc = funding_per_bar(b, f)
    return V.Context(tf, b, d, f, fr, fc)


def to_daily(r: pd.Series) -> pd.Series:
    return r.groupby(r.index.floor("D")).apply(lambda x: float(np.prod(1 + x) - 1))


def family_stream(sym: str, tf: str, fam: str, refresh: bool = False) -> pd.Series:
    """Chained forward-year returns of one family on one symbol (per-asset DD-targeted scale, cap 1)."""
    path = CACHE / f"{fam}_{sym}_{tf}.parquet"
    if path.exists() and not refresh:
        return pd.read_parquet(path)["r"]
    ctx = context(sym, tf)
    fn, grid = FAMILIES[fam]
    res = V.run(ctx, fn, grid, anchors=V.ANCHORS, select_years=None)
    parts = []
    for p in res["per_anchor"]:
        if p.get("selected") is None:
            continue
        c = p["_curves"]["normal"]
        parts.append(c.pct_change().fillna(c.iloc[0] - 1.0))
    s = to_daily(pd.concat(parts))
    CACHE.mkdir(parents=True, exist_ok=True)
    s.to_frame("r").to_parquet(path)
    return s


def metrics(r: pd.Series) -> dict:
    eq = (1 + r).cumprod()
    yrs = len(r) / 365
    g = float(eq.iloc[-1])
    cagr = g ** (1 / yrs) - 1 if g > 0 else -1.0
    dd = float(np.max(1 - eq / eq.cummax()))
    hid = r[r.index >= pd.Timestamp("2025-09-24", tz="UTC")]
    return dict(cagr=cagr, monthly=(1 + cagr) ** (1 / 12) - 1 if cagr > -1 else -1.0, dd=dd, sharpe=float(r.mean() / r.std() * np.sqrt(365)) if r.std() > 0 else 0.0,
                hidden=float(np.prod(1 + hid) - 1))
