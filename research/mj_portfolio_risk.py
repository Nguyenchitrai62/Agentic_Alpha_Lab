"""Majors 4h trend portfolio with portfolio-level risk targeting (selection strictly before each anchor)."""
import json, sys
import numpy as np, pandas as pd
import agentic_alpha_lab.research_vf as V
from agentic_alpha_lab.backtest.ma_ribbon import NORMAL, STRESS, funding_per_bar
from agentic_alpha_lab.backtest.portfolio import position_backtest, summarize_curve
from agentic_alpha_lab.vf_families import FAMILIES
XS = "data/raw/xs_universe_20260924"
def ctx_for(sym):
    if sym == "BTCUSDT": return V.load_context("4h")
    b = pd.read_parquet(f"{XS}/{sym}_4h.parquet"); d = pd.read_parquet(f"{XS}/{sym}_1d.parquet"); f = pd.read_parquet(f"{XS}/{sym}_funding.parquet")
    fr, fc = funding_per_bar(b, f); return V.Context("4h", b, d, f, fr, fc)
syms = sys.argv[1].split(",") if len(sys.argv) > 1 else ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
fam = sys.argv[2] if len(sys.argv) > 2 else "combo"
fn, grid = FAMILIES[fam]
ctxs = {s: ctx_for(s) for s in syms}
def curve(ctx, tgt, rng, costs):
    r = position_backtest(ctx.bars, tgt, *rng, costs, ctx.fr, ctx.fc)
    return r["curve"]["equity"] / 100.0
for anchor in V.ANCHORS:
    sel_curves, fwd = {}, {"normal": {}, "stress": {}}
    for s, ctx in ctxs.items():
        w = V.windows(ctx, anchor, None)
        best, score = None, -np.inf
        for p in grid:
            st = summarize_curve(position_backtest(ctx.bars, fn(ctx, p, fit_end=w["sel"][1]), *w["sel"], NORMAL, ctx.fr, ctx.fc))
            if st["changes"] >= 10 and st["sharpe"] > score: best, score = p, st["sharpe"]
        sel_curves[s] = curve(ctx, fn(ctx, best, fit_end=w["sel"][1]), w["sel"], NORMAL)
        t = fn(ctx, best, fit_end=w["fwd"][0])
        for cn, c in (("normal", NORMAL), ("stress", STRESS)):
            fwd[cn][s] = curve(ctx, t, w["fwd"], c)
    def port(curves):
        idx = sorted(set().union(*[c.index for c in curves.values()]))
        rets = pd.DataFrame({s: c.reindex(idx).ffill().pct_change().fillna(0.0) for s, c in curves.items()})
        return rets.mean(axis=1)  # equal capital, rebalanced each bar (approximation)
    pr = port(sel_curves)
    eq = (1 + pr).cumprod(); dd1 = float(np.max(1 - eq / eq.cummax()))
    K = np.floor(min(float(__import__("os").environ.get("KCAP", "2.0")), 0.20 / max(dd1, 1e-6)) * 20) / 20
    out = []
    for cn in ("normal", "stress"):
        fr_ = port(fwd[cn]) * K
        e = (1 + fr_).cumprod(); dd = float(np.max(1 - e / e.cummax()))
        out.append(f"{cn} {100*(e.iloc[-1]-1):.1f}% DD {100*dd:.1f}% mo {100*(e.iloc[-1]**(1/12)-1):.2f}%")
    print(f"{anchor} train port DD@1x {100*dd1:.1f}% -> K={K} | " + " | ".join(out), flush=True)
