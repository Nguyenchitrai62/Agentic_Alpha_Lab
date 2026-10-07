"""oc_filltime feature builder: f, age24, n_weak for majors R2 rungs.

One coin in memory at a time (float32). Pass 1 per coin C:
  - age24 for fills OF coin C (own 1m highs, window [m-1439, m], m = bar+f-1)
  - needles for coin C: close_C(m), O_C(bar), sigma_C(bar) for ALL fills' m
Pass 2 (needles only, tiny): n_weak per fill from the 4 other coins' needles.

Causality: every feature for a fill uses only 1m minutes with t <= m
(bar-open O/sigma use 4h opens up to the holding bar, v293 definition).
No outcome (y*) is read here.

  .venv/Scripts/python.exe research/tournament/oc_filltime/build_features.py
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OC = ROOT / "research/tournament/oc_filltime"
FILLS = ROOT / "research/tournament/ext/fills_U_ext.parquet"

MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)
START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24", tz="UTC")
K_WEAK = 2.5


def load_1m(sym: str) -> pd.DataFrame:
    if sym == "BTCUSDT":
        files = sorted((ROOT / "data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    else:
        files = sorted((ROOT / "data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))
    parts = [pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"]) for f in files]
    m = pd.concat(parts, ignore_index=True)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").set_index("open_time").sort_index()
    m = m[(m.index >= START) & (m.index < END)]
    full = pd.date_range(START, END - pd.Timedelta(minutes=1), freq="1min", tz="UTC")
    m = m.reindex(full)
    for c in ("open", "high", "low", "close"):
        m[c] = m[c].astype("float32")
    return m


def bar_opens_sigma(m: pd.DataFrame) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray]:
    """4h bar opens O (offset-0 1m open) and v293 sigma on the common grid."""
    n = len(m)
    nb = n // 240
    t0 = m.index[: nb * 240: 240]
    opens = m["open"].to_numpy(dtype=float)[: nb * 240: 240]
    sigma = pd.Series(opens).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy(dtype=float)
    return t0, opens, sigma


def grid_j(tt: pd.Series) -> np.ndarray:
    """Bar index j for bar-open times on the START-anchored 4h grid."""
    mins = (tt - START).dt.total_seconds().to_numpy() / 60.0
    return np.round(mins / 240.0).astype(int)


def age24_of(highs: np.ndarray, mpos: int) -> float:
    """Minutes since the trailing 1440-min high at position mpos (NaN if any gap)."""
    if mpos < 1439:
        return np.nan
    w = np.asarray(highs[mpos - 1439: mpos + 1], dtype=float)
    if not np.all(np.isfinite(w)):
        return np.nan
    last_in_w = int(np.max(np.where(w == w.max())[0]))
    return float(1439 - last_in_w)


def main() -> None:
    t0 = time.time()
    d = pd.read_parquet(FILLS)
    d["TT"] = d["t_fill"] - pd.to_timedelta(d["f"], unit="min")
    d["k"] = d["x1"]
    m = d[d["sym"].isin(MAJORS) & d["k"].isin(R2)].copy().reset_index(drop=True)
    m["fill_idx"] = np.arange(len(m))
    m["m_time"] = m["TT"] + pd.to_timedelta(m["f"] - 1, unit="min")
    m["j"] = grid_j(m["TT"])
    m.to_parquet(OC / "universe.parquet")
    print(f"universe majors-R2 rows: {len(m)}", flush=True)

    full = pd.date_range(START, END - pd.Timedelta(minutes=1), freq="1min", tz="UTC")
    pos = pd.Series(np.arange(len(full)), index=full)  # minute -> position
    mpos_all = pos.reindex(m["m_time"]).to_numpy(dtype=float)

    age24 = np.full(len(m), np.nan)
    needles = {}
    for sym in MAJORS:
        c0 = time.time()
        px = load_1m(sym)
        assert len(px) == len(full) and (px.index == full).all()
        t0grid, opens, sigma = bar_opens_sigma(px)
        jmap = pd.Series(np.arange(len(t0grid)), index=t0grid)
        H = px["high"].to_numpy(dtype=float)
        C = px["close"].to_numpy(dtype=float)
        # age24 for fills OF this coin
        own = (m["sym"] == sym).to_numpy()
        for i in np.where(own)[0]:
            mp = mpos_all[i]
            if not np.isfinite(mp):
                continue
            age24[i] = age24_of(H, int(mp))
        # needles for ALL fills: close(m), O(bar), sigma(bar) of this coin
        jj = m["j"].to_numpy()
        ok_j = (jj >= 0) & (jj < len(t0grid))
        O_bar = np.full(len(m), np.nan)
        S_bar = np.full(len(m), np.nan)
        O_bar[ok_j] = opens[jj[ok_j]]
        S_bar[ok_j] = sigma[jj[ok_j]]
        close_m = np.full(len(m), np.nan)
        valid_m = np.isfinite(mpos_all)
        close_m[valid_m] = C[mpos_all[valid_m].astype(int)]
        needles[sym] = pd.DataFrame({"fill_idx": m["fill_idx"].to_numpy(),
                                     "close_m": close_m, "O_bar": O_bar, "S_bar": S_bar})
        del px, H, C, opens, sigma
        print(f"{sym}: done in {time.time() - c0:.0f}s", flush=True)

    n_weak = np.full(len(m), np.nan)
    weak_detail = np.full((len(m), 4), np.nan)
    for i in range(len(m)):
        s = m["sym"].iloc[i]
        others = [c for c in MAJORS if c != s]
        vals = []
        ok = True
        for k, c in enumerate(others):
            nd = needles[c].iloc[i]
            cl, O, Sg = float(nd["close_m"]), float(nd["O_bar"]), float(nd["S_bar"])
            if not (np.isfinite(cl) and np.isfinite(O) and np.isfinite(Sg) and Sg > 0):
                ok = False
                break
            w = 1.0 if cl <= O * (1 - K_WEAK * Sg) else 0.0
            vals.append(w)
            weak_detail[i, k] = w
        if ok:
            n_weak[i] = float(sum(vals))

    feats = pd.DataFrame({"fill_idx": m["fill_idx"].to_numpy(),
                          "TT": m["TT"], "sym": m["sym"], "k": m["k"].to_numpy(),
                          "f": m["f"].to_numpy(dtype=float),
                          "t_fill": m["t_fill"], "t_exit": m["t_exit"],
                          "y1.0": m["y1.0"].to_numpy(dtype=float),
                          "age24": age24, "n_weak": n_weak})
    feats.to_parquet(OC / "features_filltime.parquet")
    meta = {"n": int(len(feats)),
            "TT_min": str(feats["TT"].min()), "TT_max": str(feats["TT"].max()),
            "f_min": float(feats["f"].min()), "f_max": float(feats["f"].max()),
            "age24_coverage": float(np.isfinite(age24).mean()),
            "n_weak_coverage": float(np.isfinite(n_weak).mean()),
            "runtime_s": round(time.time() - t0)}
    (OC / "features_meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main()
