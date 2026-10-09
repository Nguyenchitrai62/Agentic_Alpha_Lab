"""oc_presamplebook: TV-indicator book member, pre-sample generality test.

Frozen by PLAN.md (read it first). Pipeline:
  1. build spot 4h bars per coin from data/raw/spot_1m_presample_20261007
     (standard 00/04/08/12/16/20 UTC grid; NaN minutes ignored);
  2. load perp 4h (BTC ma_ribbon_20260924, others xs_universe_20260924);
  3. per coin stitch spot (t < perp start) + perp, compute the 17 TV features
     (v231/tv_indicators.py, imported UNCHANGED) and the v92 42-bar
     vol-normalised label separately per segment;
  4. walk-forward pooled HGBR (v92 hyperparameters) over 7 anchors
     (2019-03-01, 2019-09-24, 2020-03-01, 2021-09-24 .. 2024-09-24),
     training rows obey label_end < A - 7d;
  5. write tmp/panel.json + preds_<anchor>.csv (metrics.py scores them).

Usage: .venv/Scripts/python.exe research/tournament/oc_presamplebook/presamplebook.py
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
SPOT = ROOT / "data/raw/spot_1m_presample_20261007"
BTC4H = ROOT / "data/raw/ma_ribbon_20260924/klines_4h.parquet"
XS = ROOT / "data/raw/xs_universe_20260924"

COINS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT")
H = 42  # 7-day horizon in 4h bars
BARH = pd.Timedelta(hours=4)
EMBARGO = pd.Timedelta(days=7)
LABEL_SPAN = (H + 1) * BARH  # label end = t + 43*4h
HGB = dict(max_depth=4, learning_rate=0.03, max_iter=400,
           min_samples_leaf=300, l2_regularization=1.0, random_state=0)
ANCHORS = ["2019-03-01", "2019-09-24", "2020-03-01",
           "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24"]
# Source rule (assignment: the member is "trained and tested on 2017-2020
# spot data"; reference = "same features on 2020-08..2025-09 from the
# existing 4h data"): pre-sample anchors use spot-built bars only for BOTH
# train and test; reference anchors train on everything before (spot+perp
# stitched) and test on perp (existing 4h) bars only.
PRESAMPLE = {"2019-03-01", "2019-09-24", "2020-03-01"}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_tv():
    return _load("tv_indicators",
                 ROOT / "research/parallel/rounds/parallel-20260906-r2/v231/tv_indicators.py")


def build_spot_4h(sym: str) -> pd.DataFrame:
    """Aggregate spot 1m -> 4h on the standard grid; NaN minutes ignored."""
    m = pd.read_parquet(SPOT / f"{sym}.parquet",
                        columns=["open_time", "o", "h", "l", "c", "volume"])
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m["bar"] = m["open_time"].dt.floor("4h")
    g = m.groupby("bar", sort=True)
    first_fin = lambda s: s.dropna().iloc[0] if s.notna().any() else np.nan
    last_fin = lambda s: s.dropna().iloc[-1] if s.notna().any() else np.nan
    bars = pd.DataFrame({
        "open_time": sorted(m["bar"].dropna().unique()),
    })
    bars = bars.set_index("open_time").sort_index()
    bars["open"] = g["o"].apply(first_fin).to_numpy()
    bars["high"] = g["h"].max().to_numpy()
    bars["low"] = g["l"].min().to_numpy()
    bars["close"] = g["c"].apply(last_fin).to_numpy()
    bars["volume"] = g["volume"].sum(min_count=1).to_numpy()
    bars = bars.reset_index().sort_values("open_time").reset_index(drop=True)
    del m
    return bars


def load_perp_4h(sym: str) -> pd.DataFrame:
    src = BTC4H if sym == "BTCUSDT" else XS / f"{sym}_4h.parquet"
    b = pd.read_parquet(src, columns=["open_time", "open", "high", "low",
                                      "close", "volume"])
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
    tvm = load_tv()
    print(f"TV features ({len(tvm.TV)}): {list(tvm.TV)}", flush=True)
    panel, stats = {}, {"coins": {}, "hgb": HGB, "H": H}
    for sym in COINS:
        print(f"-- {sym}: building spot 4h ...", flush=True)
        spot = build_spot_4h(sym)
        perp = load_perp_4h(sym)
        cut = perp["open_time"].iloc[0]
        n_spot_all = len(spot)
        # executable next-bar open-to-open return, computed WITHIN each price
        # source (never across the spot/perp seam): position set at the close
        # of bar t enters at o[t+1], exits at o[t+2].
        for seg in (spot, perp):
            seg["src"] = "spot" if seg is spot else "perp"
            o1 = seg["open"].shift(-1)
            o2 = seg["open"].shift(-2)
            rn = o2 / o1 - 1
            rn = rn.where(np.isfinite(o1) & np.isfinite(o2) & (o1 > 0))
            seg["r_next"] = rn.to_numpy()
        feat_spot, feat_perp = [], []
        for seg, acc in ((spot, feat_spot), (perp, feat_perp)):
            if len(seg) == 0:
                continue
            seg = seg.sort_values("open_time").reset_index(drop=True)
            # Gaps stay NaN on the full grid, but tv_features needs finite
            # prices (its POC histogram cannot see NaN): compress to finite
            # bars, compute features + label causally on real bars only,
            # then reindex back (gap bars keep NaN features/labels).
            seg_c = seg.dropna(
                subset=["open", "high", "low", "close"]).reset_index(drop=True)
            x = tvm.tv_features(seg_c[["open_time", "open", "high", "low",
                                       "close", "volume"]])
            seg_c = pd.concat([seg_c.reset_index(drop=True),
                               x.reset_index(drop=True)], axis=1)
            seg_c = add_label(seg_c)
            keep = ["open_time"] + list(tvm.TV) + ["label"]
            seg = seg.merge(seg_c[keep], on="open_time", how="left",
                            suffixes=("", "_c"))
            # merge brings TV/label columns (seg had none of them yet)
            acc.append(seg)
        full_spot = pd.concat(feat_spot, ignore_index=True)
        full_perp = pd.concat(feat_perp, ignore_index=True)
        # stitched history for reference-anchor training (spot before the
        # coin's perp start, perp after)
        stitched = pd.concat(
            [full_spot[full_spot["open_time"] < cut], full_perp],
            ignore_index=True).sort_values("open_time").reset_index(drop=True)
        panel[sym] = {"spot": full_spot, "stitched": stitched,
                      "perp": full_perp}
        stats["coins"][sym] = {
            "spot_4h_bars": int(n_spot_all),
            "perp_start": str(cut),
            "perp_4h_bars": int(len(full_perp)),
            "spot_labels_finite": int(full_spot["label"].notna().sum()),
            "perp_labels_finite": int(full_perp["label"].notna().sum()),
        }
        print(f"   spot={n_spot_all} perp={len(full_perp)} "
              f"spot_labels={int(full_spot['label'].notna().sum())} "
              f"perp_labels={int(full_perp['label'].notna().sum())}",
              flush=True)
    feats = list(tvm.TV)
    (TMP / "panel.json").write_text(json.dumps(stats, indent=1, default=str))
    for a in ANCHORS:
        A = pd.Timestamp(a, tz="UTC")
        E = A + pd.Timedelta(days=365)
        train_cut = A - EMBARGO - LABEL_SPAN  # t + 43*4h < A - 7d
        tr_parts, te_parts = [], []
        for sym in COINS:
            if a in PRESAMPLE:
                pool_tr = panel[sym]["spot"]
                pool_te = panel[sym]["spot"]
            else:
                pool_tr = panel[sym]["stitched"]
                pool_te = panel[sym]["perp"]
            tr = pool_tr[(pool_tr["open_time"] < train_cut)
                         & pool_tr["label"].notna()]
            te = pool_te[(pool_te["open_time"] >= A) & (pool_te["open_time"] < E)
                         & pool_te["label"].notna()]
            tr_parts.append(tr.assign(sym=sym))
            te_parts.append(te.assign(sym=sym))
        tr = pd.concat(tr_parts, ignore_index=True)
        te = pd.concat(te_parts, ignore_index=True)
        Xtr = tr[feats].to_numpy(dtype=float)
        ytr = tr["label"].to_numpy(dtype=float)
        mdl = HistGradientBoostingRegressor(**HGB).fit(Xtr, ytr)
        tr_pred = mdl.predict(Xtr)
        # POST-HOC diagnostic (added after seeing test outcomes; disclosed in
        # REPORT): in-sample pooled Spearman IC as a positive control that
        # the fit loop can detect signal. Does not alter any frozen choice.
        tr_ic = float(pd.Series(tr_pred).corr(pd.Series(ytr),
                                              method="spearman"))
        s_train = float(np.std(tr_pred))
        if not np.isfinite(s_train) or s_train <= 0:
            s_train = float(np.std(ytr))
        te = te.copy()
        te["pred"] = mdl.predict(te[feats].to_numpy(dtype=float))
        fn = HERE / f"preds_{a}.csv"
        te[["open_time", "sym", "open", "pred", "label", "src",
              "r_next"]].to_csv(fn, index=False)
        n_sp = int((te["src"] == "spot").sum())
        print(f"anchor {a}: train={len(tr)} (cut {train_cut.date()}), "
              f"test={len(te)} (spot rows {n_sp}), s_train={s_train:.4f} -> {fn.name}",
              flush=True)
        stats_row = {"anchor": a, "train_rows": int(len(tr)),
                     "test_rows": int(len(te)),
                     "test_spot_rows": n_sp, "s_train": s_train,
                     "train_ic": round(tr_ic, 4)}
        prev = json.loads((TMP / "fits.json").read_text()) \
            if (TMP / "fits.json").exists() else {}
        prev[a] = stats_row
        (TMP / "fits.json").write_text(json.dumps(prev, indent=1))
    print("done; panel stats -> tmp/panel.json", flush=True)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
