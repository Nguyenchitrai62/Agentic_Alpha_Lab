"""v105: ablation of v103 (registry parallel-20260906-r2 / v105, track C).

Primary: v103 exactly (1d/3d targets, v94 long/short book, 20% vol target) but WITHOUT the order-flow features
(v92 features only) -> isolates the horizon effect. Secondary: v92 7-day model and long-only book WITH the v103 flow
features added -> does flow help the weekly model? Everything else unchanged from the audited code.

  python research/parallel/rounds/parallel-20260906-r2/v105/v105_flow_ablation.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

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


def main():
    panel = v103.build()
    allf = [c for c in panel.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    noflow = [c for c in allf if c not in v103.FLOW]
    out = {"version": "v105"}
    oos, ic = [], {}
    for a in v92.ANCHORS:
        te, _ = v103.train_predict(panel, a, noflow)
        oos.append(te)
        ic[a] = {f"ic_y{h}": round(float(te[["pred", f"y{h}"]].corr(method="spearman").iloc[0, 1]), 4) for h in v103.HS}
    print("no-flow short-horizon IC", ic, flush=True)
    out["primary_noflow_ls"] = dict(ic=ic, **v103.evaluate(panel, v94.weights_ls(pd.concat(oos, ignore_index=True), True), "v103 without flow LS"))
    v92.FEATS = allf  # v92 features + flow
    preds, ic2 = [], {}
    for a in v92.ANCHORS:
        te, _ = v92.train_predict(panel, a)
        preds.append(te)
        ic2[a] = round(float(te[["pred", "y"]].corr(method="spearman").iloc[0, 1]), 4)
    print("v92 + flow IC", ic2, flush=True)
    W = v92.weights_from(pd.concat(preds, ignore_index=True), "model")
    out["secondary_v92_plus_flow_lo"] = dict(ic=ic2, **v103.evaluate(panel, W, "v92+flow LO", scale=v92.vol_target_scale(panel, W)))
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v105_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
