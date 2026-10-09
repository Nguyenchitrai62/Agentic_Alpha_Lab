"""oc_presampleflow: whale-flow vs Coinbase-premium family skill, pre-sample generality test.

Frozen by PLAN.md (read it first). Pipeline:
  1. build stitched SPOT 4h bars per coin (presample 1m-built for t < 2020-10-01,
     spot_majors_20260925 SPOT 4h after; standard 00/04/08/12/16/20 UTC grid);
  2. FLOW features: v236/flow_features.py imported UNCHANGED, D repointed at
     data/raw/aggflow_spot_20260929_orders (order-level SPOT table; v240 pattern);
  3. PREMIUM features: v111/v111_coinbase_premium.py premium()/add_cb imported
     UNCHANGED (market-wide 5 features, joined by t to every coin);
  4. v92 H=42 vol-normalised label + r_next on the stitched spot series;
  5. walk-forward pooled HGBR (v92 hyperparameters) per family over 7 anchors
     (2019-03-01, 2019-09-24, 2020-03-01, 2021-09-24 .. 2024-09-24),
     training rows obey label_end < A - 7d; BLEND = 0.8*FLOW + 0.2*PREM;
  6. write preds_<anchor>.csv (pred_flow/pred_prem/pred_blend) + tmp/fits.json
     (metrics.py scores them).

Usage: .venv/Scripts/python.exe research/tournament/oc_presampleflow/presampleflow.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
TMP = HERE / "tmp"
TMP.mkdir(exist_ok=True)
SPOT1M = ROOT / "data/raw/spot_1m_presample_20261007"
SPOT4H = ROOT / "data/raw/spot_majors_20260925"
STITCH_CUT = pd.Timestamp("2020-10-01", tz="UTC")

COINS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT")
H = 42  # 7-day horizon in 4h bars
BARH = pd.Timedelta(hours=4)
EMBARGO = pd.Timedelta(days=7)
LABEL_SPAN = (H + 1) * BARH  # label end = t + 43*4h
HGB = dict(max_depth=4, learning_rate=0.03, max_iter=400,
           min_samples_leaf=300, l2_regularization=1.0, random_state=0)
ANCHORS = ["2019-03-01", "2019-09-24", "2020-03-01",
           "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24"]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_flow():
    flo = _load("flow_features_spot",
                ROOT / "research/parallel/rounds/parallel-20260906-r2/v236/flow_features.py")
    flo.D = ROOT / "data/raw/aggflow_spot_20260929_orders"
    return flo


def load_cb():
    return _load("v111_cb",
                 ROOT / "research/parallel/rounds/parallel-20260906-r2/v111/v111_coinbase_premium.py")


def build_spot_4h(sym: str) -> pd.DataFrame:
    """Presample 1m -> 4h on the standard grid; NaN minutes ignored, gaps stay NaN."""
    m = pd.read_parquet(SPOT1M / f"{sym}.parquet",
                        columns=["open_time", "o", "h", "l", "c", "volume"])
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m["bar"] = m["open_time"].dt.floor("4h")
    g = m.groupby("bar", sort=True)
    first_fin = lambda s: s.dropna().iloc[0] if s.notna().any() else np.nan
    last_fin = lambda s: s.dropna().iloc[-1] if s.notna().any() else np.nan
    bars = pd.DataFrame({"open_time": sorted(m["bar"].dropna().unique())})
    bars = bars.set_index("open_time").sort_index()
    bars["open"] = g["o"].apply(first_fin).to_numpy()
    bars["high"] = g["h"].max().to_numpy()
    bars["low"] = g["l"].min().to_numpy()
    bars["close"] = g["c"].apply(last_fin).to_numpy()
    bars["volume"] = g["volume"].sum(min_count=1).to_numpy()
    bars = bars.reset_index().sort_values("open_time").reset_index(drop=True)
    del m
    return bars


def load_spot4h_after(sym: str) -> pd.DataFrame:
    b = pd.read_parquet(SPOT4H / f"{sym}_spot_4h.parquet",
                        columns=["open_time", "open", "high", "low", "close", "volume"])
    b["open_time"] = pd.to_datetime(b["open_time"], utc=True)
    return b.sort_values("open_time").reset_index(drop=True)


def add_label(seg: pd.DataFrame) -> pd.DataFrame:
    """v92 label copy: fwd[i] = log(o[i+1+H]/o[i+1]); y = clip(fwd/(vol42*sqrt(H)), -4, 4)."""
    seg = seg.sort_values("open_time").reset_index(drop=True)
    c, o = seg["close"].to_numpy(dtype=float), seg["open"].to_numpy(dtype=float)
    r1 = pd.Series(np.log(c)).diff()
    vol42 = r1.rolling(H).std()
    n = len(seg)
    fwd = np.full(n, np.nan)
    if n > H + 1:
        with np.errstate(divide="ignore", invalid="ignore"):
            fwd[: n - 1 - H] = np.log(o[1 + H:] / o[1: n - H])
    seg["label"] = np.clip(fwd / (vol42.to_numpy() * np.sqrt(H)), -4, 4)
    return seg


def main():
    flo = load_flow()
    v111 = load_cb()
    print(f"FLOW features (unchanged {list(flo.FL)} from {flo.D})", flush=True)
    print(f"PREMIUM features (unchanged {list(v111.CB)})", flush=True)
    # Market-wide premium frame once (v111 code reads coinbase + spot internally).
    cb_feat = v111.add_cb(pd.DataFrame(
        {"t": pd.date_range("2017-08-01", "2026-10-01", freq="4h", tz="UTC")}))
    cb_feat = cb_feat.drop_duplicates("t").sort_values("t").reset_index(drop=True)
    panel, stats = {}, {"coins": {}, "hgb": HGB, "H": H,
                        "flow_src": str(flo.D), "flow_FL": list(flo.FL),
                        "premium_CB": list(v111.CB)}
    for sym in COINS:
        print(f"-- {sym}: building stitched spot 4h ...", flush=True)
        pre = build_spot_4h(sym)
        post = load_spot4h_after(sym)
        pre = pre[pre["open_time"] < STITCH_CUT]
        post = post[post["open_time"] >= STITCH_CUT]
        st = pd.concat([pre, post], ignore_index=True)
        st = st.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
        # executable next-bar open-to-open return on the single stitched series.
        o1 = st["open"].shift(-1)
        o2 = st["open"].shift(-2)
        rn = o2 / o1 - 1
        st["r_next"] = rn.where(np.isfinite(o1) & np.isfinite(o2) & (o1 > 0)).to_numpy()
        st = add_label(st)
        # FLOW (causal inside the module; NaN before archive/warm-up).
        bar_open = pd.DatetimeIndex(st["open_time"])
        xf = flo.flow_features(sym, bar_open).reset_index(drop=True)
        # PREMIUM (market-wide, joined by t).
        xp = st[["open_time"]].merge(cb_feat[["t"] + list(v111.CB)],
                                     left_on="open_time", right_on="t", how="left")
        st = pd.concat([st.reset_index(drop=True), xf.reset_index(drop=True),
                        xp[list(v111.CB)].reset_index(drop=True)], axis=1)
        panel[sym] = st
        stats["coins"][sym] = {
            "spot_4h_bars": int(len(st)),
            "first_bar": str(st["open_time"].iloc[0]),
            "last_bar": str(st["open_time"].iloc[-1]),
            "labels_finite": int(st["label"].notna().sum()),
            "flow_finite": int(st[list(flo.FL)].notna().all(axis=1).sum()),
            "premium_finite": int(st[list(v111.CB)].notna().all(axis=1).sum()),
        }
        print(f"   bars={len(st)} labels={int(st['label'].notna().sum())} "
              f"flow_ok={int(st[list(flo.FL)].notna().all(axis=1).sum())} "
              f"prem_ok={int(st[list(v111.CB)].notna().all(axis=1).sum())}", flush=True)
    feats_flow = list(flo.FL)
    feats_prem = list(v111.CB)
    (TMP / "panel.json").write_text(json.dumps(stats, indent=1, default=str))
    fits = {}
    for a in ANCHORS:
        A = pd.Timestamp(a, tz="UTC")
        E = A + pd.Timedelta(days=365)
        train_cut = A - EMBARGO - LABEL_SPAN  # t + 43*4h < A - 7d
        tr_parts, te_parts = [], []
        for sym in COINS:
            pool = panel[sym]
            tr = pool[(pool["open_time"] < train_cut) & pool["label"].notna()]
            te = pool[(pool["open_time"] >= A) & (pool["open_time"] < E)
                      & pool["label"].notna()]
            tr_parts.append(tr.assign(sym=sym))
            te_parts.append(te.assign(sym=sym))
        tr = pd.concat(tr_parts, ignore_index=True)
        te = pd.concat(te_parts, ignore_index=True)
        row = {"anchor": a, "train_rows": int(len(tr)), "test_rows": int(len(te))}
        tr_preds = {}
        for variant, feats in (("flow", feats_flow), ("prem", feats_prem)):
            Xtr = tr[feats].to_numpy(dtype=float)
            ytr = tr["label"].to_numpy(dtype=float)
            mdl = HistGradientBoostingRegressor(**HGB).fit(Xtr, ytr)
            tr_pred = mdl.predict(Xtr)
            tr_preds[variant] = tr_pred
            tr_ic = float(pd.Series(tr_pred).corr(pd.Series(ytr), method="spearman"))
            s = float(np.std(tr_pred))
            if not np.isfinite(s) or s <= 0:
                s = float(np.std(ytr))
            te[f"pred_{variant}"] = mdl.predict(te[feats].to_numpy(dtype=float))
            row[f"s_{variant}"] = s
            row[f"train_ic_{variant}"] = round(tr_ic, 4)
        # BLEND (fixed 0.8/0.2 deployed family weighting, prediction level).
        te["pred_blend"] = 0.8 * te["pred_flow"] + 0.2 * te["pred_prem"]
        s_blend = 0.8 * row["s_flow"] + 0.2 * row["s_prem"]
        bl_tr = 0.8 * tr_preds["flow"] + 0.2 * tr_preds["prem"]
        bl_ic = float(pd.Series(bl_tr).corr(
            pd.Series(tr["label"].to_numpy(dtype=float)), method="spearman"))
        row["s_blend"] = s_blend
        row["train_ic_blend"] = round(bl_ic, 4)
        fn = HERE / f"preds_{a}.csv"
        te[["open_time", "sym", "open", "pred_flow", "pred_prem", "pred_blend",
            "label", "r_next"]].to_csv(fn, index=False)
        print(f"anchor {a}: train={len(tr)} (cut {train_cut.date()}), test={len(te)}, "
              f"s_flow={row['s_flow']:.4f} s_prem={row['s_prem']:.4f} -> {fn.name}",
              flush=True)
        fits[a] = row
    (TMP / "fits.json").write_text(json.dumps(fits, indent=1))
    print("done; panel stats -> tmp/panel.json", flush=True)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
