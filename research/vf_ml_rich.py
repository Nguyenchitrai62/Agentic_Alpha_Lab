"""ML overlay with all information sources; hidden year + 5 real years (expanding), vs trend book."""
import numpy as np, pandas as pd
from agentic_alpha_lab.research_vf import load_context, windows, ANCHORS
from agentic_alpha_lab.backtest.ma_ribbon import NORMAL, STRESS
from agentic_alpha_lab.backtest.portfolio import position_backtest, summarize_curve
from agentic_alpha_lab.models.pattern_pipeline import build_matrix
from agentic_alpha_lab import vf_families as F
ctx = load_context("4h")
for name, blocks, daily_blocks in (("new_sources_only", ("pos", "brd", "mac", "dvol", "sea"), False), ("everything", ("cdl", "chp", "ind", "pos", "brd", "mac", "dvol", "sea"), False)):
    ctx.cache = {k: v for k, v in ctx.cache.items() if not (isinstance(k, tuple) and k[0] == "ml_pred") and k != "ml_x"}
    ctx.cache["ml_x"] = build_matrix(ctx.bars, ctx.daily, ctx.funding, blocks, daily_blocks=daily_blocks).to_numpy(np.float32)
    rows = []
    for anchor in ANCHORS:
        w = windows(ctx, anchor, None)
        for h in (12, 42):
            tgt = F.ml_book(ctx, dict(horizon=h, mode="overlay", band=0.0), fit_end=w["fwd"][0]) * 0.65
            base = F._book(ctx, "trend") * 0.65
            r = dict(anchor=anchor, h=h)
            for lab, t in (("ml", tgt), ("trend", base)):
                for cn, c in (("n", NORMAL), ("s", STRESS)):
                    r[f"{lab}_{cn}"] = round(summarize_curve(position_backtest(ctx.bars, t, *w["fwd"], c, ctx.fr, ctx.fc))["net_pct"], 1)
            rows.append(r)
    df = pd.DataFrame(rows)
    print(f"\n== {name} (n_features={ctx.cache['ml_x'].shape[1]})\n", df.to_string(index=False))
    for h in (12, 42):
        d = df[df.h == h]
        print(f" h={h}: mean(ml_s - trend_s) = {(d.ml_s - d.trend_s).mean():.2f} pp; years ml beats trend (stress) {(d.ml_s > d.trend_s).sum()}/5; hidden-year ml_s {d.ml_s.iloc[-1]}")
