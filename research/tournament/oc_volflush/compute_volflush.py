"""oc_volflush feature builder: capitulation volume at the fill minute.

For each majors R2 rung fill: at minute f-1 (last closed minute before the
fill minute t_fill), from own-coin 1m klines (volume + taker_buy_volume):
  vol_ratio  = (V15/15) / MU24   (V15 = 15-min summed volume, MU24 = trailing
                                  24h per-minute mean ending at f-1)
  sell_share = 1 - sum(taker_buy_volume over 15) / V15

Causality: only 1m bars with bar END <= t_fill are used. One coin in memory
at a time (float32). See PLAN.md (frozen before any outcome was computed).
"""
import glob
import os
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "research" / "tournament" / "oc_volflush"
FILLS = ROOT / "research" / "tournament" / "ext" / "fills_U_ext.parquet"
BTC_DIR = ROOT / "data" / "raw" / "btc_intraday_20260924"
MAJ_DIR = ROOT / "data" / "raw" / "majors_intraday_20260924"
CUTOFF = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
R2 = [2.5, 3.0, 3.5, 4.0, 5.0]
ONE_MIN = np.timedelta64(1, "m")


def coin_files(sym: str) -> list[str]:
    if sym == "BTCUSDT":
        return sorted(glob.glob(str(BTC_DIR / "klines_1m_*.parquet")))
    return sorted(glob.glob(str(MAJ_DIR / f"{sym}_1m_*.parquet")))


def load_coin(sym: str) -> pd.DataFrame:
    frames = []
    for f in coin_files(sym):
        d = pd.read_parquet(f, columns=["open_time", "volume", "taker_buy_volume"])
        frames.append(d)
    k = pd.concat(frames, ignore_index=True)
    k = k.loc[k["open_time"] < CUTOFF].sort_values("open_time").reset_index(drop=True)
    k["volume"] = k["volume"].astype("float32")
    k["taker_buy_volume"] = k["taker_buy_volume"].astype("float32")
    return k


def compute_for_coin(k: pd.DataFrame, fills: pd.DataFrame) -> pd.DataFrame:
    ot = k["open_time"].to_numpy(dtype="datetime64[m]")
    vol = k["volume"].to_numpy(dtype="float64")
    tbv = k["taker_buy_volume"].to_numpy(dtype="float64")
    tf = fills["t_fill"].to_numpy(dtype="datetime64[m]")
    n = len(fills)
    vr = np.full(n, np.nan)
    ss = np.full(n, np.nan)
    for a in range(n):
        want = tf[a] - ONE_MIN  # f-1 bar start
        i = int(np.searchsorted(ot, want))
        if i >= len(ot) or ot[i] != want:
            continue
        if i < 14:
            continue
        if ot[i] - ot[i - 14] != np.timedelta64(14, "m"):
            continue
        v15 = vol[i - 14:i + 1]
        t15 = tbv[i - 14:i + 1]
        if not np.all(np.isfinite(v15)):
            continue
        s15 = float(v15.sum())
        # 24h window by time: [t_fill - 24h, t_fill - 1m]
        lo = tf[a] - np.timedelta64(24 * 60, "m")
        j = int(np.searchsorted(ot, lo))
        w = vol[j:i + 1]
        w = w[np.isfinite(w)]
        if len(w) < 1200:
            continue
        mu = float(w.mean())
        if not np.isfinite(mu) or mu <= 0 or not np.isfinite(s15):
            continue
        vr[a] = (s15 / 15.0) / mu
        if s15 > 0 and np.all(np.isfinite(t15)):
            ss[a] = 1.0 - float(t15.sum()) / s15
    out = fills.copy()
    out["vol_ratio"] = vr
    out["sell_share"] = ss
    return out


def main() -> None:
    df = pd.read_parquet(FILLS)
    m = df.loc[df["sym"].isin(MAJORS) & df["x1"].isin(R2)].copy()
    m["T"] = m["t_fill"] - pd.to_timedelta(m["f"], unit="m")
    m = m.sort_values(["sym", "T", "t_fill"]).reset_index(drop=True)
    parts = []
    for sym in MAJORS:
        sub = m.loc[m["sym"] == sym].reset_index(drop=True)
        if len(sub) == 0:
            continue
        k = load_coin(sym)
        print(f"{sym}: {len(k)} 1m bars, {len(sub)} fills", flush=True)
        parts.append(compute_for_coin(k, sub))
        del k
    feat = pd.concat(parts, ignore_index=True).sort_values(
        ["T", "sym", "t_fill"]).reset_index(drop=True)
    cols = ["sym", "T", "t_fill", "f", "x1", "y0.5", "y1.0", "y1.5",
            "vol_ratio", "sell_share"]
    feat = feat[cols]
    os.makedirs(OUT_DIR, exist_ok=True)
    feat.to_parquet(OUT_DIR / "features_volflush.parquet", index=False)
    print(f"wrote {len(feat)} rows; vol_ratio valid {(feat['vol_ratio'].notna()).sum()}, "
          f"sell_share valid {(feat['sell_share'].notna()).sum()}", flush=True)


if __name__ == "__main__":
    main()
