"""v94 (successor of v92): pooled majors HGB ensemble on 3d/7d/14d targets with long/short sizing.

Reuses the audited v92 data, features, vol-target and execution code; only the registered changes differ:
three targets averaged, embargo = 14d label + 10d, shorts allowed when the daily ribbon is not +1.

  python research/parallel/rounds/parallel-20260906-r2/v94/v94_long_short_ensemble.py
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

PD = v92.PD
HORIZONS = (18, 42, 84)  # 3d, 7d, 14d in 4h bars
EMBARGO_BARS = max(HORIZONS) + 10 * PD


def add_targets(panel: pd.DataFrame) -> pd.DataFrame:
    out = []
    for s, g in panel.groupby("sym", sort=False):
        g = g.sort_values("t").copy()
        o = g["open"].to_numpy()
        n = len(g)
        for h in HORIZONS:
            fwd = np.full(n, np.nan)
            fwd[: n - 1 - h] = np.log(o[1 + h:] / o[1: n - h])
            g[f"y{h}"] = np.clip(fwd / (g["vol42"].to_numpy() * np.sqrt(h)), -4, 4)
        out.append(g)
    return pd.concat(out, ignore_index=True)


def train_predict(panel, anchor, feats):
    a = pd.Timestamp(anchor, tz="UTC")
    cutoff = a - pd.Timedelta(hours=4 * EMBARGO_BARS)
    te = panel[(panel.t >= a) & (panel.t < a + pd.Timedelta(days=365))].copy()
    preds, n_rows = [], {}
    for h in HORIZONS:
        tr = panel[(panel.t < cutoff) & panel[f"y{h}"].notna()]
        tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
        m = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300, l2_regularization=1.0, random_state=0)
        m.fit(tr[feats], tr[f"y{h}"])
        preds.append(m.predict(te[feats]))
        n_rows[h] = len(tr)
    te["pred"] = np.mean(preds, axis=0)
    te["y"] = te["y42"]
    return te, n_rows


def weights_ls(df: pd.DataFrame, shorts: bool) -> pd.DataFrame:
    W = {}
    for s, g in df.groupby("sym"):
        g = g.set_index("t").sort_index()
        long_ = (g["pred"].clip(lower=0) / 0.5).clip(upper=1.0).where(g["rib"] != -1, 0.0)
        short = (((-g["pred"]).clip(lower=0) / 0.5).clip(upper=1.0).where(g["rib"] != 1, 0.0)) if shorts else 0.0 * long_
        W[s] = (long_ - short) / (g["vol42"] * np.sqrt(PD * 365))
    W = pd.DataFrame(W).sort_index().fillna(0.0)
    gross = W.abs().sum(axis=1)
    active = W.ne(0).sum(axis=1)
    W = W.div(gross.where(gross > 0, 1.0), axis=0).mul((active / len(v92.SYMS)).clip(upper=1.0), axis=0)
    keep = pd.Series(np.arange(len(W)) % PD == 0, index=W.index)
    return W.where(keep, np.nan).ffill().fillna(0.0)


def vol_target_scale(panel, W, target=0.20, cap=2.0):
    o = panel.pivot_table(index="t", columns="sym", values="open").reindex(W.index)
    realized = (W.shift(2) * (o / o.shift(1) - 1)).sum(axis=1)
    vol = realized.rolling(60 * PD, min_periods=20 * PD).std() * np.sqrt(PD * 365)
    return (target / vol).clip(upper=cap).fillna(1.0)


def main():
    panel = add_targets(v92.build())
    feats = [c for c in panel.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    oos, info = [], {}
    for a in v92.ANCHORS:
        te, n_rows = train_predict(panel, a, feats)
        oos.append(te)
        info[a] = dict(ic7=round(float(te[["pred", "y42"]].corr(method="spearman").iloc[0, 1]), 4), train_rows=n_rows)
    oos = pd.concat(oos, ignore_index=True)
    out = {"version": "v94", "anchors": info}
    for book, shorts in (("long_short", True), ("long_only_ensemble", False)):
        W = weights_ls(oos, shorts)
        s = vol_target_scale(panel, W)
        res = {}
        for sc, (fee, slip) in v92.SCEN.items():
            net, turn = v92.simulate(panel, W, s, fee, slip)
            yearly = []
            for a in v92.ANCHORS:
                a0 = pd.Timestamp(a, tz="UTC")
                m = (net.index >= a0) & (net.index < a0 + pd.Timedelta(days=365))
                yearly.append(dict(anchor=a, **v92.stats(net[m], turn[m])))
            nets = [y["net_pct"] for y in yearly]
            geo = np.prod([1 + x / 100 for x in nets]) ** (1 / len(nets)) - 1
            res[sc] = dict(yearly=yearly, geometric_annual_pct=round(100 * geo, 2), monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3),
                           worst_year_dd=max(y["max_drawdown_percent"] for y in yearly))
            print(book, sc, {k: v for k, v in res[sc].items() if k != "yearly"}, [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in yearly], flush=True)
        out[book] = res
    print("ICs", {a: v["ic7"] for a, v in info.items()})
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v94_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
