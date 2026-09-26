"""Secondary track: combo family on BTC and ETH, 50/50 capital, params/scale selected per asset before the anchor."""
import numpy as np, pandas as pd
from agentic_alpha_lab.research_vf import Context, run, ANCHORS, HIDDEN_YEAR
from agentic_alpha_lab.backtest.ma_ribbon import funding_per_bar
from agentic_alpha_lab.vf_families import FAMILIES
from agentic_alpha_lab.research_vf import load_context

def eth_ctx():
    D = "data/raw/xasset_20260924"
    b = pd.read_parquet(f"{D}/ETHUSDT_4h.parquet"); d = pd.read_parquet(f"{D}/ETHUSDT_1d.parquet"); f = pd.read_parquet(f"{D}/ETHUSDT_funding.parquet")
    fr, fc = funding_per_bar(b, f)
    return Context("4h", b, d, f, fr, fc)

fn, grid = FAMILIES["combo"]
for label, anchors in (("hidden_year", HIDDEN_YEAR), ("multi_expanding", ANCHORS)):
    res = {name: run(ctx, fn, grid, anchors=anchors, select_years=None) for name, ctx in (("BTC", load_context("4h")), ("ETH", eth_ctx()))}
    print("==", label)
    for cn in ("normal", "stress"):
        yearly = []
        for i, a in enumerate(anchors):
            cb = res["BTC"]["per_anchor"][i]["_curves"][cn]; ce = res["ETH"]["per_anchor"][i]["_curves"][cn]
            ce = ce.reindex(cb.index, method="ffill").fillna(1.0)
            port = 0.5 * cb + 0.5 * ce
            dd = float(np.max(1 - port / np.maximum.accumulate(port.clip(lower=0).combine(pd.Series(1.0, index=port.index), max))))
            yearly.append((a, round(100 * (port.iloc[-1] - 1), 1), round(100 * dd, 1),
                           res["BTC"]["per_anchor"][i]["forward"][cn]["net_pct"], res["ETH"]["per_anchor"][i]["forward"][cn]["net_pct"]))
        print(cn, "(anchor, portfolio net%, portfolio DD%, BTC net, ETH net):", yearly)
