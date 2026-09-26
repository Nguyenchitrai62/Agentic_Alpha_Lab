"""Virtual-forward (vf) evaluation: five hidden years, selection strictly before each anchor.

For each anchor A in ANCHORS the family's parameters and its risk scale are
chosen using only bars whose decisions end EMBARGO_DAYS before A; the chosen
configuration then trades the hidden year [A, A + 365d). Families expose
``targets(ctx, params, fit_end) -> np.ndarray`` (signed fraction of equity per
decision bar, causal; ML families may only use labels realized before fit_end).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from agentic_alpha_lab.backtest.ma_ribbon import NORMAL, STRESS, funding_per_bar
from agentic_alpha_lab.backtest.portfolio import position_backtest, summarize_curve
from agentic_alpha_lab.patterns.common import load_bars, load_funding

ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
FORWARD_DAYS = 365
EMBARGO_DAYS = 10
SELECT_YEARS = 3
DD_TARGET = 0.20


@dataclass
class Context:
    tf: str
    bars: pd.DataFrame
    daily: pd.DataFrame
    funding: pd.DataFrame
    fr: np.ndarray
    fc: np.ndarray
    cache: dict = field(default_factory=dict)


def load_context(tf: str = "4h") -> Context:
    bars = load_bars(tf, include_opened_year=True)
    daily = load_bars("1d", include_opened_year=True)
    funding = load_funding(include_opened_year=True)
    fr, fc = funding_per_bar(bars, funding)
    return Context(tf, bars, daily, funding, fr, fc)


def _idx(bars: pd.DataFrame, ts: pd.Timestamp, side: str) -> int:
    ot = bars["open_time"]
    if side == "first":
        return int(np.flatnonzero(ot >= ts)[0])
    return int(np.flatnonzero(ot < ts)[-1])


def windows(ctx: Context, anchor: str, select_years: int | None = SELECT_YEARS) -> dict:
    a = pd.Timestamp(anchor, tz="UTC")
    b = ctx.bars
    sel_end = _idx(b, a - pd.Timedelta(days=EMBARGO_DAYS), "last")
    earliest = b["open_time"].iloc[0] + pd.Timedelta(days=60)
    sel_start = _idx(b, earliest if select_years is None else max(a - pd.Timedelta(days=365 * select_years), earliest), "first")
    fwd_start = _idx(b, a, "first")
    fwd_end = min(_idx(b, a + pd.Timedelta(days=FORWARD_DAYS), "last"), len(b) - 2)
    return dict(sel=(sel_start, sel_end), fwd=(fwd_start, fwd_end))


HIDDEN_YEAR = ("2025-09-24",)  # primary protocol (user 2026-09-24): train/select on all earlier data, hide one year


def run(ctx: Context, target_fn: Callable, grid: list[dict], cap: float = 1.0, select_metric: str = "sharpe", min_changes: int = 10,
        anchors: tuple[str, ...] = HIDDEN_YEAR, select_years: int | None = None) -> dict:
    """Nested evaluation of one family: select on data before each anchor, trade the hidden year after it."""
    per_anchor = []
    for anchor in anchors:
        w = windows(ctx, anchor, select_years)
        best, best_score, best_sel = None, -np.inf, None
        for params in grid:
            tgt = target_fn(ctx, params, fit_end=w["sel"][1])
            s = summarize_curve(position_backtest(ctx.bars, tgt, *w["sel"], NORMAL, ctx.fr, ctx.fc))
            if s["changes"] < min_changes:
                continue
            score = s[select_metric]
            if score > best_score:
                best, best_score, best_sel = params, score, s
        if best is None:
            per_anchor.append(dict(anchor=anchor, selected=None))
            continue
        k = math.floor(min(cap, DD_TARGET / max(best_sel["dd_intrabar_pct"] / 100, 1e-6)) * 20) / 20
        tgt = target_fn(ctx, best, fit_end=w["fwd"][0]) * k
        rows = {}
        curves = {}
        for cname, costs in (("normal", NORMAL), ("stress", STRESS)):
            res = position_backtest(ctx.bars, tgt, *w["fwd"], costs, ctx.fr, ctx.fc)
            rows[cname] = {m: round(v, 4) if isinstance(v, float) else v for m, v in summarize_curve(res).items()}
            curves[cname] = res["curve"]["equity"] / 100.0
        bh = summarize_curve(position_backtest(ctx.bars, np.ones(len(ctx.bars)), *w["fwd"], NORMAL, ctx.fr, ctx.fc))
        per_anchor.append(dict(anchor=anchor, selected=best, scale=k, select_sharpe=round(best_score, 3),
                               select_dd=round(best_sel["dd_intrabar_pct"], 2), forward=rows,
                               buy_hold_net=round(bh["net_pct"], 2), _curves=curves))
    return dict(per_anchor=per_anchor, aggregate=aggregate(per_anchor))


def aggregate(per_anchor: list[dict]) -> dict:
    out = {}
    done = [p for p in per_anchor if p.get("selected") is not None]
    for cname in ("normal", "stress"):
        if not done:
            continue
        chained, level = [], 1.0
        for p in done:
            c = p["_curves"][cname]
            chained.append(c * level)
            level *= float(c.iloc[-1])
        eq = pd.concat(chained)
        dd = float(np.max(1 - eq / np.maximum.accumulate(np.concatenate([[1.0], eq.to_numpy()]))[1:]))
        years = len(done)
        nets = [p["forward"][cname]["net_pct"] for p in done]
        out[cname] = dict(total_pct=round(100 * (level - 1), 2), cagr_pct=round(100 * (level ** (1 / years) - 1), 2),
                          monthly_geo_pct=round(100 * (level ** (1 / (12 * years)) - 1), 3), max_dd_close_pct=round(100 * dd, 2),
                          worst_year_intrabar_dd=round(max(p["forward"][cname]["dd_intrabar_pct"] for p in done), 2),
                          years_positive=sum(n > 0 for n in nets), years=years, yearly_net=[round(n, 2) for n in nets])
    bh = [p["buy_hold_net"] for p in done]
    out["buy_hold_yearly"] = bh
    out["buy_hold_total_pct"] = round(100 * (np.prod([1 + x / 100 for x in bh]) - 1), 2) if bh else None
    return out


def strip(result: dict) -> dict:
    return dict(per_anchor=[{k: v for k, v in p.items() if not k.startswith("_")} for p in result["per_anchor"]], aggregate=result["aggregate"])


def accept(agg: dict) -> bool:
    """Hidden-year acceptance: every hidden year positive under stress and intrabar DD <= 20% in normal and stress."""
    s = agg.get("stress")
    return bool(s and s["years_positive"] == s["years"] and s["worst_year_intrabar_dd"] <= 20)


SPOT_DIR = "data/raw/btc_spot_2017_20260924"


def load_context_extended(tf: str = "4h") -> Context:
    """USD-M history prefixed with Binance spot BTCUSDT bars from 2017-08-17 (before the perp existed).

    The spot period has no funding; a flat 0.0001 per 8h schedule is synthesized so long costs match
    the normal-cost assumption.
    """
    base = load_context(tf)
    spot = pd.read_parquet(f"{SPOT_DIR}/spot_{tf}.parquet")
    spot_d = pd.read_parquet(f"{SPOT_DIR}/spot_1d.parquet")
    first = base.bars["open_time"].iloc[0]
    bars = pd.concat([spot[spot["open_time"] < first], base.bars]).reset_index(drop=True)
    first_d = base.daily["open_time"].iloc[0]
    daily = pd.concat([spot_d[spot_d["open_time"] < first_d], base.daily]).reset_index(drop=True)
    synth_t = pd.date_range(spot["open_time"].iloc[0].ceil("8h"), base.funding["fundingTime"].iloc[0] - pd.Timedelta("1s"), freq="8h")
    funding = pd.concat([pd.DataFrame({"fundingTime": synth_t, "fundingRate": 0.0001}), base.funding[["fundingTime", "fundingRate"]]]).reset_index(drop=True)
    fr, fc = funding_per_bar(bars, funding)
    return Context(tf, bars, daily, funding, fr, fc)
