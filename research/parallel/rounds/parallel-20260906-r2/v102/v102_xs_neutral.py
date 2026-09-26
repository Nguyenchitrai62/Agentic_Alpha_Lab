"""v102: market-neutral majors book from a cross-sectional HGB, blended with v99 (registry parallel-20260906-r2 / v102, track C).

Target: v92 y (7-day vol-normalized forward return) minus its same-bar mean over the majors with a label.
Features: the audited v92 features plus same-bar cross-sectionally demeaned copies of snr42, snr180, ret42, ret180,
d50, d200, f7, vol_ratio, volz (fixed in advance). HGB hyperparameters as v92; v92 anchors/embargo.
Book: at each bar, demeaned predictions / annualized vol42, scaled to gross 1 (dollar-neutral), daily rebalance,
own causal 10% vol target (cap 2x, same form as v92.vol_target_scale). Blend: 0.75 * v99 net + 0.25 * neutral net
(weights fixed before running; costs charged on each stream's own turnover, so netting is ignored = conservative).
Neutral legs pay long funding on the long side like the other books.

  python research/parallel/rounds/parallel-20260906-r2/v102/v102_xs_neutral.py
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


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, HERE.parent / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v92 = _load("v92", "v92/v92_pooled_hgb_vt.py")
v94 = _load("v94", "v94/v94_long_short_ensemble.py")
v99 = _load("v99", "v99/v99_candidate.py")
PD = v92.PD
XS_COLS = ("snr42", "snr180", "ret42", "ret180", "d50", "d200", "f7", "vol_ratio", "volz")
W_V99, W_XS, XS_TARGET = 0.75, 0.25, 0.10


def add_xs(panel):
    p = panel.copy()
    for c in XS_COLS:
        p[f"xs_{c}"] = p[c] - p.groupby("t")[c].transform("mean")
    lab = p["y"].notna()
    p["y_xs"] = np.where(lab, p["y"] - p["y"].where(lab).groupby(p["t"]).transform("mean"), np.nan)
    p.loc[p.groupby("t")["y"].transform("count") < 2, "y_xs"] = np.nan
    return p


def train_predict_xs(p, anchor, feats):
    a = pd.Timestamp(anchor, tz="UTC")
    cutoff = a - pd.Timedelta(hours=4 * v92.EMBARGO_BARS)
    tr = p[(p.t < cutoff) & p.y_xs.notna()]
    tr = tr[tr.t + pd.Timedelta(hours=4 * (v92.H + 1)) < cutoff]
    te = p[(p.t >= a) & (p.t < a + pd.Timedelta(days=365))].copy()
    m = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300, l2_regularization=1.0, random_state=0)
    m.fit(tr[feats], tr["y_xs"])
    te["pred"] = m.predict(te[feats])
    return te, len(tr)


def weights_neutral(df):
    pred = df.pivot_table(index="t", columns="sym", values="pred").sort_index()
    vol = df.pivot_table(index="t", columns="sym", values="vol42").reindex(pred.index) * np.sqrt(PD * 365)
    raw = pred.sub(pred.mean(axis=1), axis=0) / vol
    W = raw.sub(raw.mean(axis=1), axis=0).fillna(0.0)  # re-centre over available assets -> dollar-neutral
    W = W.mul(pred.notna().sum(axis=1) >= 2, axis=0)
    W = W.div(W.abs().sum(axis=1).clip(lower=1e-9), axis=0)
    keep = pd.Series(np.arange(len(W)) % PD == 0, index=W.index)
    return W.where(keep, np.nan).ffill().fillna(0.0)


def v99_nets(panel):
    """Rebuild the audited v99 portfolio (same code path as v99_candidate.main) and return per-scenario nets."""
    lo = pd.concat([v92.train_predict(panel, a)[0] for a in v92.ANCHORS], ignore_index=True)
    W_lo = v92.weights_from(lo, "model")
    panel94 = v94.add_targets(v92.build())
    f94 = [c for c in panel94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    ls = pd.concat([v94.train_predict(panel94, a, f94)[0] for a in v92.ANCHORS], ignore_index=True)
    W_ls = v94.weights_ls(ls, True)
    idx = W_lo.index.union(W_ls.index)
    books = 0.5 * W_lo.reindex(idx).fillna(0.0).mul(v92.vol_target_scale(panel, W_lo).reindex(idx).fillna(1.0), axis=0) \
        + 0.5 * W_ls.reindex(idx).fillna(0.0).mul(v94.vol_target_scale(panel94, W_ls).reindex(idx).fillna(1.0), axis=0)
    carry = pd.read_parquet("artifacts/research/carry/carry_oos_fee0.0004.parquet")["carry"].reindex(idx).fillna(0.0)
    o = panel.pivot_table(index="t", columns="sym", values="open").reindex(idx)
    realized = v99.W_BOOKS * (books.shift(2) * (o / o.shift(1) - 1)).sum(axis=1) + v99.W_CARRY * v99.CARRY_LEV * carry.shift(1)
    vol = realized.rolling(60 * PD, min_periods=20 * PD).std() * np.sqrt(PD * 365)
    s = (v99.TARGET / vol).clip(upper=v99.CAP).fillna(1.0)
    Wt = books.mul(v99.W_BOOKS * s, axis=0)
    r_next = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    carry_exp = v99.W_CARRY * v99.CARRY_LEV * s
    out = {}
    for sc, (fee, slip) in v92.SCEN.items():
        turn = Wt.diff().abs().sum(axis=1).fillna(Wt.abs().sum(axis=1))
        net = (Wt * r_next).sum(axis=1) - turn * (fee + slip) - Wt.clip(lower=0).sum(axis=1) * 0.00005 \
            + carry_exp * carry - carry_exp.diff().abs().fillna(0.0) * 2 * 0.0004 / 1.2
        out[sc] = (net, turn)
    return out


def yearly_stats(net, turn):
    yearly = []
    for a in v92.ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        mk = (net.index >= a0) & (net.index < a0 + pd.Timedelta(days=365))
        yearly.append(dict(anchor=a, **v92.stats(net[mk], turn[mk])))
    geo = np.prod([1 + y["net_pct"] / 100 for y in yearly]) ** (1 / 5) - 1
    return dict(yearly=yearly, monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3), worst_year_dd=max(y["max_drawdown_percent"] for y in yearly))


def main():
    panel = v92.build()
    v92.FEATS = [c for c in panel.columns if c not in ("y", "t", "open", "sym", "bar")]
    p = add_xs(panel)
    feats = v92.FEATS + [f"xs_{c}" for c in XS_COLS]
    preds, ics = [], {}
    for a in v92.ANCHORS:
        te, ntr = train_predict_xs(p, a, feats)
        preds.append(te)
        g = te.dropna(subset=["y_xs"])
        ics[a] = dict(train_rows=ntr, ic_pooled=round(float(g[["pred", "y_xs"]].corr(method="spearman").iloc[0, 1]), 4),
                      ic_per_bar_mean=round(float(g.groupby("t").apply(lambda x: x["pred"].corr(x["y_xs"], method="spearman") if len(x) > 2 else np.nan).mean()), 4))
        print(a, ics[a], flush=True)
    oos = pd.concat(preds, ignore_index=True)
    W = weights_neutral(oos)
    s = v92.vol_target_scale(panel, W, target=XS_TARGET)
    base = v99_nets(panel)
    out = {"version": "v102", "ic": ics, "fixed": dict(W_V99=W_V99, W_XS=W_XS, XS_TARGET=XS_TARGET, XS_COLS=XS_COLS)}
    for sc, (fee, slip) in v92.SCEN.items():
        n_xs, t_xs = v92.simulate(panel, W, s, fee, slip)
        n99, t99 = base[sc]
        idx = n99.index.union(n_xs.index)
        n_xs, t_xs = n_xs.reindex(idx).fillna(0.0), t_xs.reindex(idx).fillna(0.0)
        n99, t99 = n99.reindex(idx).fillna(0.0), t99.reindex(idx).fillna(0.0)
        oos_mask = idx >= pd.Timestamp(v92.ANCHORS[0], tz="UTC")
        out[sc] = dict(neutral=yearly_stats(n_xs, t_xs), v99=yearly_stats(n99, t99),
                       blend=yearly_stats(W_V99 * n99 + W_XS * n_xs, W_V99 * t99 + W_XS * t_xs),
                       corr_neutral_v99_daily=round(float(n_xs[oos_mask].groupby(idx[oos_mask].floor("D")).sum().corr(n99[oos_mask].groupby(idx[oos_mask].floor("D")).sum())), 3))
        for k in ("neutral", "v99", "blend"):
            r = out[sc][k]
            print(sc, k, r["monthly_pct"], r["worst_year_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in r["yearly"]], flush=True)
        print(sc, "corr", out[sc]["corr_neutral_v99_daily"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v102_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
