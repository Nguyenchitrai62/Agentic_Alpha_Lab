"""Leader evaluation of the v90 Kaggle export inside the audited v92 book framework.

Predictions: mean of three seeds per asset (y7 head), rescaled to the v92 target scale (v90 label =
7d return / 1-bar vol; v92 label = 7d return / (1-bar vol * sqrt(42))). Sizing rows:
- registered (v89 contract): v92 long-only weights with portfolio scale K from prior OOS years' DD (K=1 first year);
- reference (v92 contract): causal 20% vol target;
- reference: 50/50 average of v90 and v92 predictions with the v92 vol target.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("v92", HERE.parent / "v92" / "v92_pooled_hgb_vt.py")
v92 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v92)
PRED = Path("artifacts/kaggle/v90/output/v90_out/predictions")


def v90_preds(panel):
    rows = []
    for a in v92.ANCHORS:
        p = pd.read_parquet(PRED / f"pred_{a}.parquet")
        ct = pd.to_datetime(p["close_time"], utc=True)
        for s in v92.SYMS:
            rows.append(pd.DataFrame({"close_time": ct, "sym": s, "pred90": p[f"{s}_y7_mean"].to_numpy() / np.sqrt(42)}))
    pr = pd.concat(rows, ignore_index=True)
    bars = {}
    for s in v92.SYMS:
        b, _, _ = v92.load_asset(s)
        bars[s] = pd.DataFrame({"t": b["open_time"], "close_time": b["close_time"], "sym": s})
    key = pd.concat(bars.values(), ignore_index=True)
    pr = pr.merge(key, on=["close_time", "sym"], how="left")
    return panel.merge(pr[["t", "sym", "pred90"]], on=["t", "sym"], how="inner")


def evaluate(panel, oos, mode_label, scale_rule):
    W = v92.weights_from(oos, "model")
    if scale_rule == "vol":
        s = v92.vol_target_scale(panel, W)
    res, prev = {}, []
    for sc, (fee, slip) in v92.SCEN.items():
        yearly = []
        prev = []
        for a in v92.ANCHORS:
            a0 = pd.Timestamp(a, tz="UTC")
            Wy = W[(W.index >= a0) & (W.index < a0 + pd.Timedelta(days=365))]
            if scale_rule == "vol":
                K = s.reindex(Wy.index)
            else:
                if prev:
                    eq = (1 + pd.concat(prev)).cumprod()
                    K = float(np.floor(min(2.0, 0.20 / max(float(np.max(1 - eq / eq.cummax())), 1e-6)) * 20) / 20)
                else:
                    K = 1.0
                n1, _ = v92.simulate(panel, Wy, 1.0, *v92.SCEN["normal"])
                prev.append(n1)
            net, turn = v92.simulate(panel, Wy, K, fee, slip)
            yearly.append(dict(anchor=a, **v92.stats(net, turn)))
        nets = [y["net_pct"] for y in yearly]
        geo = np.prod([1 + x / 100 for x in nets]) ** (1 / len(nets)) - 1
        res[sc] = dict(yearly=yearly, monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3), worst_year_dd=max(y["max_drawdown_percent"] for y in yearly))
    n = res["normal"]
    print(mode_label, "| monthly", n["monthly_pct"], "worstDD", n["worst_year_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in n["yearly"]], flush=True)
    return res


def main():
    panel = v92.build()
    v92.FEATS = [c for c in panel.columns if c not in ("y", "t", "open", "sym", "bar")]
    oos92 = pd.concat([v92.train_predict(panel, a)[0] for a in v92.ANCHORS], ignore_index=True)
    joined = v90_preds(oos92)
    out = {"version": "v90-eval", "rows_joined": int(len(joined))}
    ics = {}
    for a in v92.ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        g = joined[(joined.t >= a0) & (joined.t < a0 + pd.Timedelta(days=365))].dropna(subset=["y"])
        ics[a] = dict(ic_v90=round(float(g[["pred90", "y"]].corr(method="spearman").iloc[0, 1]), 4),
                      ic_v92=round(float(g[["pred", "y"]].corr(method="spearman").iloc[0, 1]), 4),
                      corr_v90_v92=round(float(g[["pred90", "pred"]].corr(method="spearman").iloc[0, 1]), 4))
    out["ic"] = ics
    print("IC", ics)
    v90only = joined.assign(pred=joined["pred90"])
    blend = joined.assign(pred=0.5 * joined["pred90"] + 0.5 * joined["pred"])
    out["v90_registered_K_rule"] = evaluate(panel, v90only, "v90 K-rule (registered)", "K")
    out["v90_vol_target"] = evaluate(panel, v90only, "v90 vol-target (reference)", "vol")
    out["v90_v92_average_vol_target"] = evaluate(panel, blend, "v90+v92 average vol-target (reference)", "vol")
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v90_eval_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
