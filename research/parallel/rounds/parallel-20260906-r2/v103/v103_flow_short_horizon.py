"""v103: pooled majors HGB on short horizons (1d, 3d) with order-flow features (registry parallel-20260906-r2 / v103).

Rationale: IR ~ IC * sqrt(breadth). The 7-day model makes ~52 independent bets/asset/year; a 1-day horizon with daily
rebalance makes ~365, so a lower IC can still give a higher Sharpe if costs allow.

Features = audited v92 features + flow features from the 4h klines (all computed from bars closed at t):
  tbr_k  = rolling-k mean of taker_buy_quote_volume/quote_volume - 0.5, k in 1, 6, 42
  flow_k = sum_k((2*tbr1-1)*quote_volume) / sum_k(quote_volume), k in 6, 42
  tbr_z  = (tbr_6 - rolling-180 mean of tbr_1) / rolling-180 std of tbr_1
  tsize_z, ntr_z = 180-bar z-scores of log(quote_volume/num_trades) and log(num_trades)
  rng6   = rolling-6 mean of log(high/low) / vol42 ; clv6 = rolling-6 mean of (close-low)/(high-low) - 0.5
Targets: y6 and y18 = clip(log(open[t+1+h]/open[t+1]) / (vol42*sqrt(h)), +-4). Prediction = mean of the two HGBs (v92
hyperparameters). Embargo 18 + 60 bars. Book (primary): audited v94 weights_ls(shorts=True) (daily rebalance, ribbon
gating) with causal 20% vol target cap 2. Secondary rows: long-only (shorts=False); 50/50 with the audited v96 books.
Costs: v92 scenarios. Everything fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v103/v103_flow_short_horizon.py
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
PD = v92.PD
HS = (6, 18)
EMBARGO = max(HS) + 10 * PD
FLOW = ("tbr_1", "tbr_6", "tbr_42", "flow_6", "flow_42", "tbr_z", "tsize_z", "ntr_z", "rng6", "clv6")


def flow_features(b: pd.DataFrame, vol42: pd.Series) -> pd.DataFrame:
    qv = b["quote_volume"].astype(float).clip(lower=1.0)
    tbr1 = (b["taker_buy_quote_volume"].astype(float) / qv).clip(0, 1)
    x = pd.DataFrame(index=b.index)
    for k in (1, 6, 42):
        x[f"tbr_{k}"] = tbr1.rolling(k).mean() - 0.5
    signed = (2 * tbr1 - 1) * qv
    for k in (6, 42):
        x[f"flow_{k}"] = signed.rolling(k).sum() / qv.rolling(k).sum()
    x["tbr_z"] = (tbr1.rolling(6).mean() - tbr1.rolling(180).mean()) / tbr1.rolling(180).std()
    ts = np.log(qv / b["num_trades"].astype(float).clip(lower=1))
    nt = np.log(b["num_trades"].astype(float).clip(lower=1))
    x["tsize_z"] = (ts - ts.rolling(180).mean()) / ts.rolling(180).std()
    x["ntr_z"] = (nt - nt.rolling(180).mean()) / nt.rolling(180).std()
    x["rng6"] = np.log(b["high"] / b["low"]).rolling(6).mean() / vol42
    x["clv6"] = ((b["close"] - b["low"]) / (b["high"] - b["low"]).replace(0, np.nan)).rolling(6).mean() - 0.5
    return x


def build():
    rows = []
    for i, s in enumerate(v92.SYMS):
        b, d, f = v92.load_asset(s)
        x, y = v92.features(b, d, f)
        x = pd.concat([x, flow_features(b, x["vol42"])], axis=1)
        x["asset"], x["y"], x["t"], x["open"], x["sym"], x["bar"] = i, y, b["open_time"], b["open"].to_numpy(), s, np.arange(len(b))
        o = b["open"].to_numpy()
        n = len(b)
        for h in HS:
            fwd = np.full(n, np.nan)
            fwd[: n - 1 - h] = np.log(o[1 + h:] / o[1: n - h])
            x[f"y{h}"] = np.clip(fwd / (x["vol42"].to_numpy() * np.sqrt(h)), -4, 4)
        rows.append(x)
    panel = pd.concat(rows, ignore_index=True)
    btc = panel[panel.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    return panel.join(btc, on="t")


def train_predict(panel, anchor, feats):
    a = pd.Timestamp(anchor, tz="UTC")
    cutoff = a - pd.Timedelta(hours=4 * EMBARGO)
    te = panel[(panel.t >= a) & (panel.t < a + pd.Timedelta(days=365))].copy()
    preds, rows = [], {}
    for h in HS:
        tr = panel[(panel.t < cutoff) & panel[f"y{h}"].notna()]
        tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
        m = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300, l2_regularization=1.0, random_state=0)
        m.fit(tr[feats], tr[f"y{h}"])
        preds.append(m.predict(te[feats]))
        rows[h] = len(tr)
    te["pred"] = np.mean(preds, axis=0)
    return te, rows


def evaluate(panel, W, label, scale=None):
    s = v94.vol_target_scale(panel, W) if scale is None else scale
    res = {}
    for sc, (fee, slip) in v92.SCEN.items():
        net, turn = v92.simulate(panel, W, s, fee, slip)
        yearly = []
        for a in v92.ANCHORS:
            a0 = pd.Timestamp(a, tz="UTC")
            mk = (net.index >= a0) & (net.index < a0 + pd.Timedelta(days=365))
            yearly.append(dict(anchor=a, **v92.stats(net[mk], turn[mk])))
        geo = np.prod([1 + y["net_pct"] / 100 for y in yearly]) ** (1 / 5) - 1
        res[sc] = dict(yearly=yearly, monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3), worst_year_dd=max(y["max_drawdown_percent"] for y in yearly))
        print(label, sc, res[sc]["monthly_pct"], res[sc]["worst_year_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in yearly], flush=True)
    return res


def main():
    panel = build()
    base = [c for c in panel.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    feats = base  # v92 features + FLOW
    assert all(f in feats for f in FLOW)
    oos, ic = [], {}
    for a in v92.ANCHORS:
        te, rows = train_predict(panel, a, feats)
        oos.append(te)
        ic[a] = dict(train_rows=rows, **{f"ic_y{h}": round(float(te[["pred", f"y{h}"]].corr(method="spearman").iloc[0, 1]), 4) for h in HS},
                     ic_y42=round(float(te[["pred", "y"]].corr(method="spearman").iloc[0, 1]), 4))
        print(a, ic[a], flush=True)
    oos = pd.concat(oos, ignore_index=True)
    out = {"version": "v103", "ic": ic, "features": feats}
    W_ls = v94.weights_ls(oos, True)
    out["primary_long_short"] = evaluate(panel, W_ls, "v103 LS")
    out["secondary_long_only"] = evaluate(panel, v94.weights_ls(oos, False), "v103 LO")
    # secondary: 50/50 with the audited v96 books (v92 LO + v94 LS, own vol targets)
    p92 = v92.build()
    v92.FEATS = [c for c in p92.columns if c not in ("y", "t", "open", "sym", "bar")]
    W_lo = v92.weights_from(pd.concat([v92.train_predict(p92, a)[0] for a in v92.ANCHORS], ignore_index=True), "model")
    p94 = v94.add_targets(v92.build())
    f94 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    W94 = v94.weights_ls(pd.concat([v94.train_predict(p94, a, f94)[0] for a in v92.ANCHORS], ignore_index=True), True)
    idx = W_lo.index.union(W94.index).union(W_ls.index)
    v96 = 0.5 * W_lo.reindex(idx).fillna(0.0).mul(v92.vol_target_scale(p92, W_lo).reindex(idx).fillna(1.0), axis=0) \
        + 0.5 * W94.reindex(idx).fillna(0.0).mul(v94.vol_target_scale(p94, W94).reindex(idx).fillna(1.0), axis=0)
    W103 = W_ls.reindex(idx).fillna(0.0).mul(v94.vol_target_scale(panel, W_ls).reindex(idx).fillna(1.0), axis=0)
    out["secondary_blend_v96"] = evaluate(p92, 0.5 * v96 + 0.5 * W103, "0.5 v96 + 0.5 v103", scale=1.0)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v103_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
