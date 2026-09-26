"""Ablation of the ML overlay: feature blocks and multi-year robustness, fixed config horizon=12 overlay, k=1."""
import numpy as np, pandas as pd, sys
from agentic_alpha_lab.research_vf import load_context, windows, ANCHORS
from agentic_alpha_lab.backtest.ma_ribbon import NORMAL, STRESS
from agentic_alpha_lab.backtest.portfolio import position_backtest, summarize_curve
from agentic_alpha_lab.models.pattern_pipeline import build_matrix
from agentic_alpha_lab import vf_families as F
ctx = __import__("agentic_alpha_lab.research_vf", fromlist=["x"]).load_context_extended("4h")
blocks_sets = {"base": (), "all": ("cdl", "chp", "ind")}
for name, blocks in blocks_sets.items():
    ctx.cache = {k: v for k, v in ctx.cache.items() if not (isinstance(k, tuple) and k[0] == "ml_pred") and k != "ml_x"}
    ctx.cache["ml_x"] = build_matrix(ctx.bars, ctx.daily, ctx.funding, blocks).to_numpy(np.float32)
    rows = []
    for anchor in ANCHORS:
        w = windows(ctx, anchor, None)
        tgt = F.ml_book(ctx, dict(horizon=12, mode="overlay", band=0.0), fit_end=w["fwd"][0])
        base = F._book(ctx, "trend")
        r = {}
        for lab, t in (("ml", tgt), ("trend", base)):
            for cn, c in (("n", NORMAL), ("s", STRESS)):
                s = summarize_curve(position_backtest(ctx.bars, t, *w["fwd"], c, ctx.fr, ctx.fc))
                r[f"{lab}_{cn}"] = round(s["net_pct"], 1)
            r[f"{lab}_dd"] = round(s["dd_intrabar_pct"], 1)
        rows.append(dict(anchor=anchor, **r))
    df = pd.DataFrame(rows)
    print(f"\n== features {name}\n", df.to_string(index=False))
    print(" mean ml_s - trend_s:", round((df.ml_s - df.trend_s).mean(), 2), "| years ml_s>0:", (df.ml_s > 0).sum(), "| years ml beats trend (stress):", (df.ml_s > df.trend_s).sum())
