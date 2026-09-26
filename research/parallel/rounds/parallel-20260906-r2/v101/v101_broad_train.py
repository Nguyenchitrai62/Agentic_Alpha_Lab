"""v101: v92 pooled HGB trained on the 5 majors plus 13 established large-cap perps (TRAINING ROWS ONLY).

The 13 extra assets were fixed in advance by pre-2021-09 median 4h quote volume among perps listed before
2021 (no forward information): ADA DOGE LINK LTC BCH DOT AVAX TRX ETC XLM UNI AAVE FIL. The audited v92
feature/target definitions, embargo and hyperparameters are unchanged; extra assets get asset ids 5..17 and the
same BTC context join. Test rows, the book, vol target and costs are exactly v92 (majors only; the extra assets
are never traded, per the majors-only universe rule).

Primary: extra rows at sample weight 1. Sensitivity: extra rows at sample weight 0.5.

  python research/parallel/rounds/parallel-20260906-r2/v101/v101_broad_train.py
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
EXTRA = ("ADAUSDT", "DOGEUSDT", "LINKUSDT", "LTCUSDT", "BCHUSDT", "DOTUSDT", "AVAXUSDT", "TRXUSDT", "ETCUSDT", "XLMUSDT", "UNIUSDT", "AAVEUSDT", "FILUSDT")
EXCL = ("y", "t", "open", "sym", "bar", "extra")


def build_extra(panel):
    rows = []
    for i, s in enumerate(EXTRA):
        b, d, f = v92.load_asset(s)
        x, y = v92.features(b, d, f)
        x["asset"], x["y"], x["t"], x["open"], x["sym"], x["bar"] = 5 + i, y, b["open_time"].to_numpy(), b["open"].to_numpy(), s, np.arange(len(b))
        rows.append(x)
    p = pd.concat(rows, ignore_index=True)
    btc = panel[panel.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    return p.join(btc, on="t").assign(extra=1)


def train_predict(panel, extra, anchor, feats, w_extra):
    a = pd.Timestamp(anchor, tz="UTC")
    cutoff = a - pd.Timedelta(hours=4 * v92.EMBARGO_BARS)
    pool = pd.concat([panel.assign(extra=0), extra], ignore_index=True)
    tr = pool[(pool.t < cutoff) & pool.y.notna()]
    tr = tr[tr.t + pd.Timedelta(hours=4 * (v92.H + 1)) < cutoff]
    te = panel[(panel.t >= a) & (panel.t < a + pd.Timedelta(days=365))].copy()
    m = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300, l2_regularization=1.0, random_state=0)
    m.fit(tr[feats], tr["y"], sample_weight=np.where(tr["extra"] == 1, w_extra, 1.0))
    te["pred"] = m.predict(te[feats])
    return te, dict(majors=int((tr.extra == 0).sum()), extra=int((tr.extra == 1).sum()))


def run(panel, extra, feats, w_extra):
    preds, ics = [], {}
    for a in v92.ANCHORS:
        te, rows = train_predict(panel, extra, a, feats, w_extra)
        preds.append(te)
        ics[a] = dict(ic=round(float(te[["pred", "y"]].corr(method="spearman").iloc[0, 1]), 4), train_rows=rows)
    oos = pd.concat(preds, ignore_index=True)
    W = v92.weights_from(oos, "model")
    s = v92.vol_target_scale(panel, W)
    res = {"ic": ics}
    for sc, (fee, slip) in v92.SCEN.items():
        net, turn = v92.simulate(panel, W, s, fee, slip)
        yearly = []
        for a in v92.ANCHORS:
            a0 = pd.Timestamp(a, tz="UTC")
            mk = (net.index >= a0) & (net.index < a0 + pd.Timedelta(days=365))
            yearly.append(dict(anchor=a, **v92.stats(net[mk], turn[mk])))
        geo = np.prod([1 + y["net_pct"] / 100 for y in yearly]) ** (1 / 5) - 1
        res[sc] = dict(yearly=yearly, monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3), worst_year_dd=max(y["max_drawdown_percent"] for y in yearly))
    n = res["normal"]
    print(f"w_extra {w_extra} IC", [v["ic"] for v in ics.values()], "| monthly", n["monthly_pct"], "worstDD", n["worst_year_dd"],
          [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in n["yearly"]], flush=True)
    return res


def main():
    panel = v92.build()
    feats = [c for c in panel.columns if c not in EXCL]
    v92.FEATS = feats
    extra = build_extra(panel)
    print("extra rows", len(extra), flush=True)
    out = {"version": "v101", "extra_assets": EXTRA, "primary_w1": run(panel, extra, feats, 1.0), "sensitivity_w05": run(panel, extra, feats, 0.5)}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v101_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
