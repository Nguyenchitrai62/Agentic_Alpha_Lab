"""v108: rebalance frequency of the v103 order-flow long/short book (registry parallel-20260906-r2 / v108).

The v103 predictions (1d/3d order-flow HGB, audited code path) are unchanged; the book is the v94 weights_ls rule
with the rebalance step changed from every 6th 4h bar (daily, v103) to every bar (4h, primary) and every 3rd bar
(12h, secondary). Own causal 20% vol target, cap 2; v92 cost scenarios. Also reported: the daily v103 reference.
Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v108/v108_rebalance_freq.py
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
v103 = _load("v103", "v103/v103_flow_short_horizon.py")
PD = v92.PD


def weights_ls_every(df: pd.DataFrame, every: int) -> pd.DataFrame:
    """v94.weights_ls (shorts on) with the rebalance step as a parameter."""
    W = {}
    for s, g in df.groupby("sym"):
        g = g.set_index("t").sort_index()
        long_ = (g["pred"].clip(lower=0) / 0.5).clip(upper=1.0).where(g["rib"] != -1, 0.0)
        short = ((-g["pred"]).clip(lower=0) / 0.5).clip(upper=1.0).where(g["rib"] != 1, 0.0)
        W[s] = (long_ - short) / (g["vol42"] * np.sqrt(PD * 365))
    W = pd.DataFrame(W).sort_index().fillna(0.0)
    gross = W.abs().sum(axis=1)
    active = W.ne(0).sum(axis=1)
    W = W.div(gross.where(gross > 0, 1.0), axis=0).mul((active / len(v92.SYMS)).clip(upper=1.0), axis=0)
    keep = pd.Series(np.arange(len(W)) % every == 0, index=W.index)
    return W.where(keep, np.nan).ffill().fillna(0.0)


def main():
    panel = v103.build()
    feats = [c for c in panel.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    oos = pd.concat([v103.train_predict(panel, a, feats)[0] for a in v92.ANCHORS], ignore_index=True)
    ref = weights_ls_every(oos, PD)
    assert np.allclose(ref.to_numpy(), v94.weights_ls(oos, True).to_numpy())
    out = {"version": "v108"}
    out["primary_every_4h"] = v103.evaluate(panel, weights_ls_every(oos, 1), "LS every 4h")
    out["secondary_every_12h"] = v103.evaluate(panel, weights_ls_every(oos, 3), "LS every 12h")
    out["reference_daily_v103"] = v103.evaluate(panel, ref, "LS daily (v103)")
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v108_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
