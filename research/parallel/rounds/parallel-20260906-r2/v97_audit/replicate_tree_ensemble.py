"""Blind v97 audit reproduction from OPENCODE_V97_AUDIT.md spec.

Reads only raw data under data/raw/*, writes only under v97_audit/.
Does NOT read research/.../v97/* (blind until replication.json is saved).

Base: v92_audit/replicate_5asset_leader_run.py (same features, target,
cutoff/embargo, 5-asset universe, v92 long-only book with causal 20% vol
target). Change per v97 spec: per anchor, train on the v92 training rows an
ensemble of 16 models (15 x HistGradientBoostingRegressor + 1 x
ExtraTreesRegressor) fitted on features with NaN replaced by TRAINING-ROW
medians (same medians applied to prediction rows). Prediction = mean of all 16.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor

ROOT = Path(__file__).resolve().parents[5]
OUT_DIR = Path(__file__).resolve().parent
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
PD = 6
H = 42
EMBARGO_BARS = H + 10 * PD  # 102 bars = 408h, as in v92
BTC_DIR = ROOT / "data/raw/ma_ribbon_20260924"
XS_DIR = ROOT / "data/raw/xs_universe_20260924"
SPOT_DIR = ROOT / "data/raw/spot_majors_20260925"

HGB_DEPTHS = (3, 4, 6)
HGB_SEEDS = (0, 1, 2, 3, 4)


def load_asset(s):
    if s == "BTCUSDT":
        b = pd.read_parquet(BTC_DIR / "klines_4h.parquet")
        d = pd.read_parquet(BTC_DIR / "klines_1d.parquet")
        f = pd.read_parquet(BTC_DIR / "funding.parquet")
    else:
        b = pd.read_parquet(XS_DIR / f"{s}_4h.parquet")
        d = pd.read_parquet(XS_DIR / f"{s}_1d.parquet")
        f = pd.read_parquet(XS_DIR / f"{s}_funding.parquet")
    for x in (b, d):
        x["open_time"] = pd.to_datetime(x["open_time"], utc=True)
        x["close_time"] = pd.to_datetime(x["close_time"], utc=True)
    f["fundingTime"] = pd.to_datetime(f["fundingTime"], utc=True)
    b = b.sort_values("open_time").reset_index(drop=True)
    d = d.sort_values("open_time").reset_index(drop=True)
    f = f.sort_values("fundingTime").reset_index(drop=True)
    # Prefix Binance SPOT bars for open_time before first USD-M bar (funding NaN there).
    if not (SPOT_DIR / f"{s}_spot_4h_2017.parquet").exists():  # SOL has no spot prefix
        s4 = b.iloc[:0].copy()
        s1 = d.iloc[:0].copy()
    else:
        s4 = pd.read_parquet(SPOT_DIR / f"{s}_spot_4h_2017.parquet")
        s1 = pd.read_parquet(SPOT_DIR / f"{s}_spot_1d_2017.parquet")
    for x in (s4, s1):
        x["open_time"] = pd.to_datetime(x["open_time"], utc=True)
        x["close_time"] = pd.to_datetime(x["close_time"], utc=True)
    first_4h = b["open_time"].min()
    first_1d = d["open_time"].min()
    pre4 = s4[s4["open_time"] < first_4h].copy()
    pre1 = s1[s1["open_time"] < first_1d].copy()
    b = pd.concat([pre4, b], ignore_index=True).sort_values("open_time").reset_index(drop=True)
    d = pd.concat([pre1, d], ignore_index=True).sort_values("open_time").reset_index(drop=True)
    return b, d, f


def features(b, d, f):
    c = b["close"].astype(float)
    lc = np.log(c)
    r1 = lc.diff()
    x = pd.DataFrame(index=b.index)
    vol42 = r1.rolling(42).std()  # ddof=1, min_periods=42
    for k in (6, 42, 90, 180, 540):
        dk = lc.diff(k)
        x[f"ret{k}"] = dk
        x[f"snr{k}"] = dk / (vol42 * np.sqrt(k))
    x["vol42"] = vol42
    x["vol180"] = r1.rolling(180).std()
    x["vol_ratio"] = x["vol42"] / x["vol180"]
    for sp in (20, 200):
        x[f"ema{sp}"] = np.log(c / c.ewm(span=sp, adjust=False, min_periods=sp).mean())
    dc = d["close"].astype(float)
    sma50 = dc.rolling(50).mean()
    sma200 = dc.rolling(200).mean()
    dfe = pd.DataFrame({
        "t": d["close_time"],
        "d50": np.log(dc / sma50),
        "d200": np.log(dc / sma200),
        "rib": np.where((dc > sma50) & (sma50 > sma200), 1.0,
                        np.where((dc < sma50) & (sma50 < sma200), -1.0, 0.0)),
    })
    j = pd.merge_asof(pd.DataFrame({"t": b["close_time"]}), dfe.sort_values("t"), on="t", direction="backward")
    x[["d50", "d200", "rib"]] = j[["d50", "d200", "rib"]].to_numpy()
    fr = f.set_index("fundingTime")["fundingRate"].astype(float)
    fm = pd.DataFrame({"t": fr.index,
                       "f7": fr.rolling(21, min_periods=3).mean().to_numpy(),
                       "f30": fr.rolling(90, min_periods=9).mean().to_numpy()})
    jf = pd.merge_asof(pd.DataFrame({"t": b["close_time"]}), fm.sort_values("t"), on="t", direction="backward")
    x["f7"] = jf["f7"].to_numpy() * 1e4
    x["f30"] = jf["f30"].to_numpy() * 1e4
    lv = np.log(b["quote_volume"].astype(float).clip(lower=1))
    x["volz"] = (lv - lv.rolling(180).mean()) / lv.rolling(180).std()
    o = b["open"].astype(float).to_numpy()
    n = len(b)
    fwd = np.full(n, np.nan)
    if n > 1 + H:
        fwd[: n - 1 - H] = np.log(o[1 + H:] / o[1: n - H])
    y = np.clip(fwd / (vol42.to_numpy() * np.sqrt(H)), -4, 4)
    return x, y


def build():
    rows = []
    for i, s in enumerate(SYMS):
        b, d, f = load_asset(s)
        x, y = features(b, d, f)
        x["asset"] = i
        x["y"] = y
        x["t"] = b["open_time"]
        x["open"] = b["open"].astype(float).to_numpy()
        x["sym"] = s
        x["bar"] = np.arange(len(b))
        rows.append(x)
    panel = pd.concat(rows, ignore_index=True)
    btc = panel[panel.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    panel = panel.join(btc, on="t")
    return panel


FEATS = None


def train_predict(panel, anchor):
    """v92 training rows + 16-model mean with TRAINING-ROW median imputation."""
    a = pd.Timestamp(anchor, tz="UTC")
    end = a + pd.Timedelta(days=365)
    cutoff = a - pd.Timedelta(hours=4 * EMBARGO_BARS)
    tr = panel[(panel.t < cutoff) & panel.y.notna()]
    tr = tr[tr.t + pd.Timedelta(hours=4 * (H + 1)) < cutoff]
    te = panel[(panel.t >= a) & (panel.t < end)].copy()
    medians = tr[FEATS].median(numeric_only=True)
    medians = medians.fillna(0.0)
    tr_imp = tr[FEATS].fillna(medians).to_numpy()
    te_imp = te[FEATS].fillna(medians).to_numpy()
    ytr = tr["y"].to_numpy()
    preds = np.zeros(len(te))
    n_models = 0
    for depth in HGB_DEPTHS:
        for seed in HGB_SEEDS:
            m = HistGradientBoostingRegressor(
                max_depth=depth, learning_rate=0.03, max_iter=400,
                min_samples_leaf=300, l2_regularization=1.0,
                max_features=0.7, random_state=seed)
            m.fit(tr_imp, ytr)
            preds += m.predict(te_imp)
            n_models += 1
    et = ExtraTreesRegressor(n_estimators=300, min_samples_leaf=300,
                             max_features=0.5, random_state=0, n_jobs=-1)
    et.fit(tr_imp, ytr)
    preds += et.predict(te_imp)
    n_models += 1
    assert n_models == 16
    te["pred"] = preds / 16.0
    return te, len(tr), {k: float(v) for k, v in medians.items()}


def weights_from(df, mode="model"):
    """v92 long-only book weights (per-asset fraction of equity)."""
    W = {}
    for s, g in df.groupby("sym"):
        g = g.set_index("t").sort_index()
        if mode == "model":
            sig = g["pred"].clip(lower=0) / 0.5
        else:  # pragma: no cover - audit uses model only
            sig = (np.sign(g["ret42"]) + np.sign(g["ret180"])).clip(lower=0) / 2
        sig = sig.where(g["rib"] != -1, 0.0).clip(upper=1.0)
        W[s] = sig / (g["vol42"] * np.sqrt(PD * 365))
    W = pd.DataFrame(W).sort_index().fillna(0.0)
    n_assets = W.gt(0).sum(axis=1).clip(lower=1)
    W = W.div(W.abs().sum(axis=1).clip(lower=1e-9), axis=0).mul(W.abs().sum(axis=1).gt(0), axis=0)
    W = W.mul((n_assets / len(SYMS)).clip(upper=1.0), axis=0)
    keep = pd.Series(np.arange(len(W)) % PD == 0, index=W.index)
    return W.where(keep, np.nan).ffill().fillna(0.0)


def vol_target_scale(panel, W, target=0.20, cap=2.0, lookback_days=60):
    """Causal per-bar scale from trailing realized vol of the unscaled book."""
    o = panel.pivot_table(index="t", columns="sym", values="open").reindex(W.index)
    realized = (W.shift(2) * (o / o.shift(1) - 1)).sum(axis=1)
    vol = realized.rolling(lookback_days * PD, min_periods=20 * PD).std() * np.sqrt(PD * 365)
    return (target / vol).clip(upper=cap).fillna(1.0)


def simulate(panel, W, scale, fee=0.0002, slip=0.0):
    o = panel.pivot_table(index="t", columns="sym", values="open").reindex(W.index)
    r = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    Wk = W.mul(scale, axis=0) if isinstance(scale, pd.Series) else W * scale
    turn = Wk.diff().abs().sum(axis=1).fillna(Wk.abs().sum(axis=1))
    long_funding = Wk.clip(lower=0).sum(axis=1) * 0.0001 * (1 / 2)
    net = (Wk * r).sum(axis=1) - turn * (fee + slip) - long_funding
    return net, turn


def stats(net, turn):
    eq = (1 + net).cumprod()
    days = len(net) / PD
    g = float(eq.iloc[-1]) if len(eq) else float("nan")
    dd = float(np.max(1 - eq / eq.cummax())) if len(eq) else float("nan")
    return dict(net_pct=round(100 * (g - 1), 2),
                monthly_geometric_net_percent=round(100 * (g ** (30.4375 / days) - 1), 3) if days > 0 else float("nan"),
                max_drawdown_percent=round(100 * dd, 2),
                fills=int((turn > 1e-6).sum()),
                months=round(days / 30.4375, 1),
                bars=int(len(net)))


def main():
    global FEATS
    panel = build()
    FEATS = [c for c in panel.columns if c not in ("y", "t", "open", "sym", "bar")]
    anchors_rec = []
    oos_parts = []
    median_check = {}
    for anchor in ANCHORS:
        te, ntr, med = train_predict(panel, anchor)
        median_check[anchor] = {"n_median_finite": int(np.isfinite(list(med.values())).sum()),
                                "n_features": len(med)}
        ev = te.dropna(subset=["y"])
        rho = float(te[["pred", "y"]].corr(method="spearman").iloc[0, 1]) if len(ev) > 2 else float("nan")
        anchors_rec.append(dict(anchor=anchor, train_rows=int(ntr),
                                n_pred_rows=int(len(te)),
                                n_pred_rows_with_y=int(len(ev)),
                                ic=round(rho, 4)))
        oos_parts.append(te)
        print(anchor, "train", ntr, "pred", len(te), "with_y", len(ev), "IC", round(rho, 4), flush=True)
    oos = pd.concat(oos_parts, ignore_index=True)
    Wfull = weights_from(oos, "model")
    Kfull = vol_target_scale(panel, Wfull)
    yearly = []
    net_parts, turn_parts = [], []
    for anchor in ANCHORS:
        a0 = pd.Timestamp(anchor, tz="UTC")
        a1 = a0 + pd.Timedelta(days=365)
        W = Wfull[(Wfull.index >= a0) & (Wfull.index < a1)]
        K = Kfull.reindex(W.index)
        n2, t2 = simulate(panel, W, K, 0.0002, 0.0)
        s = stats(n2, t2)
        s["anchor"] = anchor
        s["K_mean"] = round(float(K.mean()), 3)
        yearly.append(s)
        net_parts.append(n2)
        turn_parts.append(t2)
        print(anchor, "yearly_normal", s, flush=True)
    net = pd.concat(net_parts).sort_index()
    turn = pd.concat(turn_parts).sort_index()
    result = {
        "anchors": anchors_rec,
        "yearly_normal": yearly,
        "model": {
            "ensemble": 16,
            "hgb": {"count": 15, "max_depth": [3, 4, 6], "learning_rate": 0.03,
                    "max_iter": 400, "min_samples_leaf": 300,
                    "l2_regularization": 1.0, "max_features": 0.7,
                    "random_state": [0, 1, 2, 3, 4]},
            "extra_trees": {"count": 1, "n_estimators": 300, "min_samples_leaf": 300,
                            "max_features": 0.5, "random_state": 0, "n_jobs": -1},
            "imputation": "TRAINING-ROW medians; same medians applied to prediction rows; all-NaN median -> 0.0",
            "prediction": "mean of all 16",
        },
        "features": FEATS,
        "assets": list(SYMS),
        "data": {
            "usdm_btc": "data/raw/ma_ribbon_20260924",
            "usdm_others": "data/raw/xs_universe_20260924",
            "spot_prefix": "data/raw/spot_majors_20260925/{SYM}_spot_{4h,1d}_2017.parquet open_time < first USD-M bar (SOL: no file, no prefix)",
        },
        "execution": {
            "fee_per_unit_turnover": 0.0002,
            "slip": 0.0,
            "long_funding_per_4h_bar": 0.00005,
            "weight": "v92 model long-only: s=min(max(pred,0)/0.5,1) zeroed when rib==-1; raw=s/(vol42*sqrt(2190)); normalise to 1 then *min(1,count/5); every 6th bar ffill",
            "vol_target": "causal 20%: realized=(W.shift(2)*(o/o.shift(1)-1)).sum; vol=rolling360(min120)std*sqrt(2190); scale=min(0.20/vol,2) NaN->1",
            "realisation": "per-year v92 simulate: W_t*scale_t earns open_{t+2}/open_{t+1}-1; fee 0.0002; funding 0.00005",
        },
        "assumptions": [
            "anchors 2021-09-24..2025-09-24; cutoff=A-408h; train t<cutoff and t+172h<cutoff and y not NaN; predict [A,A+365d); 5 forward sets concatenated.",
            "same v92 features/target: 26 feats; y=clip(log(open[t+43]/open[t+1])/(vol42*sqrt(42)),+-4).",
            "leader NaN: ribbon 0 when SMA unavailable (np.where); funding rolling21/min3 and rolling90/min9 x1e4 via merge_asof backward.",
            "spot 4h/1d prefix for open_time < first USD-M bar per asset (SOL: no prefix file); funding from USD-M only.",
            "yearly windows cut from one continuous OOS prediction series; W/K from full span, per-year normal simulate.",
        ],
        "median_check": median_check,
    }
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(result, f, indent=2)
    oos[["t", "sym", "open", "pred", "y", "vol42", "rib"]].to_csv(OUT_DIR / "predictions.csv", index=False)
    pd.DataFrame({"t": net.index, "net": net.values, "turnover": turn.values,
                  "scale": Kfull.reindex(net.index).values}).to_csv(OUT_DIR / "equity.csv", index=False)
    print(json.dumps({"anchors": anchors_rec, "yearly": yearly}, indent=2))


if __name__ == "__main__":
    main()
