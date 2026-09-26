"""Secondary track: combo family on a 5-coin basket (equal capital), params+scale per coin chosen before the anchor."""
import numpy as np, pandas as pd
from agentic_alpha_lab.research_vf import Context, run, ANCHORS, HIDDEN_YEAR, load_context
from agentic_alpha_lab.backtest.ma_ribbon import funding_per_bar
from agentic_alpha_lab.vf_families import FAMILIES
D = "data/raw/xasset_20260924"
def ctx_for(sym):
    if sym == "BTCUSDT": return load_context("4h")
    b = pd.read_parquet(f"{D}/{sym}_4h.parquet"); d = pd.read_parquet(f"{D}/{sym}_1d.parquet"); f = pd.read_parquet(f"{D}/{sym}_funding.parquet")
    fr, fc = funding_per_bar(b, f); return Context("4h", b, d, f, fr, fc)
syms = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]
fn, grid = FAMILIES["combo"]
ctxs = {s: ctx_for(s) for s in syms}
for label, anchors in (("hidden_year", HIDDEN_YEAR), ("multi_expanding", ANCHORS)):
    res = {s: run(c, fn, grid, anchors=anchors, select_years=None) for s, c in ctxs.items()}
    print("==", label)
    for cn in ("normal", "stress"):
        out = []
        for i, a in enumerate(anchors):
            curves = []
            for s in syms:
                p = res[s]["per_anchor"][i]
                if p.get("selected") is None: continue
                curves.append(p["_curves"][cn])
            idx = curves[0].index
            port = sum(c.reindex(idx, method="ffill").fillna(1.0) for c in curves) / len(curves)
            dd = float(np.max(1 - port / np.maximum.accumulate(np.maximum(port.to_numpy(), 1.0))))
            out.append((a, len(curves), round(100 * (port.iloc[-1] - 1), 1), round(100 * dd, 1)))
        print(cn, "(anchor, coins, basket net%, basket DD%):", out)
