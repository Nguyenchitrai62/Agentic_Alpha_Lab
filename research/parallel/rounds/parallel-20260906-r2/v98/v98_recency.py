"""v98: v92 pooled HGB with exponential recency sample weights (half-life 2y primary, 1y secondary).

Weight of a training row = 0.5 ** (age / half_life), age = anchor cutoff - row time. Everything else is the
audited v92 pipeline (features, target, embargo, long-only book, causal 20% vol target, execution/costs).

  python research/parallel/rounds/parallel-20260906-r2/v98/v98_recency.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("v92", HERE.parent / "v92" / "v92_pooled_hgb_vt.py")
v92 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v92)


def train_predict_weighted(panel, anchor, feats, half_life_years):
    a = pd.Timestamp(anchor, tz="UTC")
    cutoff = a - pd.Timedelta(hours=4 * v92.EMBARGO_BARS)
    tr = panel[(panel.t < cutoff) & panel.y.notna()]
    tr = tr[tr.t + pd.Timedelta(hours=4 * (v92.H + 1)) < cutoff]
    age_years = (cutoff - tr.t).dt.total_seconds() / (365.25 * 86400)
    w = 0.5 ** (age_years / half_life_years)
    te = panel[(panel.t >= a) & (panel.t < a + pd.Timedelta(days=365))].copy()
    m = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300, l2_regularization=1.0, random_state=0)
    m.fit(tr[feats], tr["y"], sample_weight=w.to_numpy())
    te["pred"] = m.predict(te[feats])
    return te


def run(panel, feats, hl):
    preds, ics = [], []
    for a in v92.ANCHORS:
        te = train_predict_weighted(panel, a, feats, hl)
        preds.append(te)
        ics.append(round(float(te[["pred", "y"]].corr(method="spearman").iloc[0, 1]), 4))
    oos = pd.concat(preds, ignore_index=True)
    W = v92.weights_from(oos, "model")
    s = v92.vol_target_scale(panel, W)
    res = {"ic_by_anchor": ics}
    for sc, (fee, slip) in v92.SCEN.items():
        net, turn = v92.simulate(panel, W, s, fee, slip)
        yearly = []
        for a in v92.ANCHORS:
            a0 = pd.Timestamp(a, tz="UTC")
            mask = (net.index >= a0) & (net.index < a0 + pd.Timedelta(days=365))
            yearly.append(dict(anchor=a, **v92.stats(net[mask], turn[mask])))
        geo = np.prod([1 + y["net_pct"] / 100 for y in yearly]) ** (1 / 5) - 1
        res[sc] = dict(yearly=yearly, monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3), worst_year_dd=max(y["max_drawdown_percent"] for y in yearly))
    n = res["normal"]
    print(f"half-life {hl}y IC", ics, "| monthly", n["monthly_pct"], "worstDD", n["worst_year_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in n["yearly"]], flush=True)
    return res


def main():
    panel = v92.build()
    feats = [c for c in panel.columns if c not in ("y", "t", "open", "sym", "bar")]
    v92.FEATS = feats
    out = {"version": "v98", "primary_half_life_2y": run(panel, feats, 2.0), "secondary_half_life_1y": run(panel, feats, 1.0)}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v98_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
