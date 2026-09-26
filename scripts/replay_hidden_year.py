"""Bar-by-bar replay of a frozen family config over the hidden year using truncated data only.

At each 4h decision bar t the strategy sees only bars[:t+1], daily bars closed by
then and funding published by then. The decision fills at open[t+1]. Outputs a
trade log and checks equality with the vectorized target.

  python scripts/replay_hidden_year.py combo '{"fast":20,"entry":55,"exit":10,"gate":"none","w":0.5}' --scale 0.65
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from agentic_alpha_lab.backtest.ma_ribbon import NORMAL, STRESS
from agentic_alpha_lab.backtest.portfolio import position_backtest, summarize_curve
from agentic_alpha_lab.research_vf import Context, HIDDEN_YEAR, load_context, windows
from agentic_alpha_lab.vf_families import FAMILIES

OUT = Path("artifacts/research/vf/replay")


def truncated(ctx: Context, t: int) -> Context:
    close_t = ctx.bars["close_time"].iloc[t]
    bars = ctx.bars.iloc[: t + 1]
    daily = ctx.daily.loc[ctx.daily["close_time"] <= close_t]
    funding = ctx.funding.loc[ctx.funding["fundingTime"] <= close_t]
    return Context(ctx.tf, bars, daily, funding, ctx.fr[: t + 1], ctx.fc[: t + 1])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("family")
    ap.add_argument("params")
    ap.add_argument("--scale", type=float, required=True)
    ap.add_argument("--stride", type=int, default=1, help="check every Nth bar (1 = every bar)")
    a = ap.parse_args()
    fn, _ = FAMILIES[a.family]
    params = json.loads(a.params)
    ctx = load_context("4h")
    w = windows(ctx, HIDDEN_YEAR[0], None)
    s, e = w["fwd"]
    full = fn(ctx, params, fit_end=s) * a.scale
    replay = full.copy()
    t0 = time.time()
    mismatches = []
    for t in range(s, e + 1, a.stride):
        v = fn(truncated(ctx, t), params, fit_end=s)[-1] * a.scale
        replay[t] = v
        if abs(v - full[t]) > 1e-9:
            mismatches.append(dict(t=int(t), time=str(ctx.bars["close_time"].iloc[t]), replay=float(v), full=float(full[t])))
    OUT.mkdir(parents=True, exist_ok=True)
    rows = {}
    for cn, c in (("normal", NORMAL), ("stress", STRESS)):
        res = position_backtest(ctx.bars, replay, s, e, c, ctx.fr, ctx.fc)
        rows[cn] = {k: round(v, 4) if isinstance(v, float) else v for k, v in summarize_curve(res).items()}
        if cn == "normal":
            curve = res["curve"]
    # trade log from position changes
    b = ctx.bars
    log, prev = [], 0.0
    for t in range(s, e + 1):
        if abs(replay[t] - prev) > 1e-9:
            log.append(dict(decision_close=str(b["close_time"].iloc[t]), fill_open_time=str(b["open_time"].iloc[t + 1]),
                            fill_price=float(b["open"].iloc[t + 1]), from_pos=round(prev, 3), to_pos=round(float(replay[t]), 3)))
            prev = replay[t]
    tag = f"{a.family}_{abs(hash(a.params)) % 10**6}"
    pd.DataFrame(log).to_csv(OUT / f"{tag}_trades.csv", index=False)
    curve["equity"].resample("1D").last().to_csv(OUT / f"{tag}_equity_daily.csv")
    summary = dict(family=a.family, params=params, scale=a.scale, window=[str(b["open_time"].iloc[s]), str(b["open_time"].iloc[e])],
                   bars_checked=len(range(s, e + 1, a.stride)), mismatches=len(mismatches), first_mismatches=mismatches[:5],
                   results=rows, position_changes=len(log), seconds=round(time.time() - t0, 1))
    (OUT / f"{tag}_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps({k: v for k, v in summary.items() if k != "first_mismatches"}, indent=1))
    if mismatches:
        print("MISMATCHES", mismatches[:5])


if __name__ == "__main__":
    main()
