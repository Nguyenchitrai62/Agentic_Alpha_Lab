"""v96: fixed 50/50 capital blend of the audited v92 long-only book and the audited v94 long/short book.

Each book keeps its own causal 20% vol target (cap 2x); combined weights are simulated with the
v92 execution/cost code. No new fitting. Registry parallel-20260906-r2 / v96 (track C).

  python research/parallel/rounds/parallel-20260906-r2/v96/v96_blend.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, HERE.parent / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v92 = _load("v92", "v92/v92_pooled_hgb_vt.py")
v94 = _load("v94", "v94/v94_long_short_ensemble.py")


def main():
    panel = v92.build()
    v92.FEATS = [c for c in panel.columns if c not in ("y", "t", "open", "sym", "bar")]
    lo_pred = pd.concat([v92.train_predict(panel, a)[0] for a in v92.ANCHORS], ignore_index=True)
    W_lo = v92.weights_from(lo_pred, "model")
    s_lo = v92.vol_target_scale(panel, W_lo)
    panel94 = v94.add_targets(v92.build())
    feats94 = [c for c in panel94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    ls_pred = pd.concat([v94.train_predict(panel94, a, feats94)[0] for a in v92.ANCHORS], ignore_index=True)
    W_ls = v94.weights_ls(ls_pred, True)
    s_ls = v94.vol_target_scale(panel94, W_ls)
    idx = W_lo.index.union(W_ls.index)
    W = 0.5 * W_lo.reindex(idx).fillna(0.0).mul(s_lo.reindex(idx).fillna(1.0), axis=0) \
        + 0.5 * W_ls.reindex(idx).fillna(0.0).mul(s_ls.reindex(idx).fillna(1.0), axis=0)
    out = {"version": "v96", "weights": "0.5 * v92 long-only (own vol target) + 0.5 * v94 long/short (own vol target)"}
    for sc, (fee, slip) in v92.SCEN.items():
        net, turn = v92.simulate(panel, W, 1.0, fee, slip)
        yearly = []
        for a in v92.ANCHORS:
            a0 = pd.Timestamp(a, tz="UTC")
            m = (net.index >= a0) & (net.index < a0 + pd.Timedelta(days=365))
            yearly.append(dict(anchor=a, **v92.stats(net[m], turn[m])))
        nets = [y["net_pct"] for y in yearly]
        geo = np.prod([1 + x / 100 for x in nets]) ** (1 / len(nets)) - 1
        out[sc] = dict(yearly=yearly, geometric_annual_pct=round(100 * geo, 2), monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3),
                       worst_year_dd=max(y["max_drawdown_percent"] for y in yearly))
        print(sc, {k: v for k, v in out[sc].items() if k != "yearly"}, [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in yearly], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v96_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
