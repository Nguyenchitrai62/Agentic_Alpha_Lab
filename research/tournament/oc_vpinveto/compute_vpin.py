"""Compute causal VPIN-50 gates per coin (one coin at a time, float32, resume-safe).

Usage:
  python compute_vpin.py --coin BTCUSDT   (via heavy_slot; one job at a time)
  python compute_vpin.py --coin ALL        (sequential, one coin at a time)
  python compute_vpin.py --norms           (after all coins: per-anchor mu/sd + gates)

Frozen (PLAN.md): trailing 24h, 50 equal-volume buckets, z>2, 1y norm [A-372d,A-7d],
7d embargo, rows < 2021-09-24 never gated. 1m bars with open in [T-24h, T-1m].
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TMP = HERE / "tmp"
COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
RAW = ROOT / "data/raw/aggflow_20260929_orders_1m"
ANCH = ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
GRID0 = pd.Timestamp("2020-09-01 00:00", tz="UTC")
GRID1 = pd.Timestamp("2026-09-24 00:00", tz="UTC")

sys.path.insert(0, str(HERE))
from vpin_rule import N_BUCKETS, anchor_of, bucketed_vpin, gate_z

HEARTBEAT_S = 600
_stop_hb = threading.Event()


def heartbeat(tag):
    while not _stop_hb.wait(HEARTBEAT_S):
        print(f"[hb {datetime.now(timezone.utc):%H:%M:%S}Z] {tag} alive", flush=True)


def buy_sell_cols(df: pd.DataFrame):
    bcols = [c for c in df.columns if c.startswith("buy_")]
    scols = [c for c in df.columns if c.startswith("sell_")]
    return bcols, scols


def load_coin_minutes(coin: str) -> pd.DataFrame:
    """Per-minute B/S/V float32, sorted, deduped. One coin at a time."""
    fs = sorted((RAW / coin).glob("*.parquet"))
    assert fs, f"no files for {coin}"
    parts = []
    for f in fs:
        df = pd.read_parquet(f)
        bcols, scols = buy_sell_cols(df)
        idx = pd.to_datetime(df.index, utc=True)
        b = df[bcols].to_numpy(dtype=np.float32).sum(axis=1)
        s = df[scols].to_numpy(dtype=np.float32).sum(axis=1)
        parts.append(pd.DataFrame(
            {"B": b.astype(np.float32), "S": s.astype(np.float32)},
            index=idx))
    m = pd.concat(parts).sort_index()
    m = m[~m.index.duplicated(keep="last")]
    return m


def grid_4h() -> pd.DatetimeIndex:
    return pd.date_range(GRID0, GRID1, freq="4h", tz="UTC")


def compute_coin(coin: str) -> Path:
    out = TMP / f"vpin_{coin}.parquet"
    if out.exists():
        print(f"{coin}: cached {out}", flush=True)
        return out
    print(f"{coin}: loading 1m ...", flush=True)
    m = load_coin_minutes(coin)
    print(f"{coin}: {len(m)} minutes {m.index.min()} .. {m.index.max()}", flush=True)
    t_ns = m.index.values.astype("datetime64[ns]").astype(np.int64)
    B = m["B"].to_numpy(dtype=np.float32)
    S = m["S"].to_numpy(dtype=np.float32)
    V = (B.astype(np.float64) + S.astype(np.float64))
    D = (B.astype(np.float64) - S.astype(np.float64))
    cumV = np.cumsum(V)
    cumD = np.cumsum(D)
    g = grid_4h()
    g_ns = g.values.astype("datetime64[ns]").astype(np.int64)
    win_ns = np.int64(24 * 3600 * 1_000_000_000)
    vp = np.full(len(g), np.nan)
    nwin = np.zeros(len(g), dtype=np.int32)
    for j, T in enumerate(g_ns):
        # 1m bars with open in [T-24h, T-1m]: t < T and t >= T-24h
        lo = int(np.searchsorted(t_ns, T - win_ns, side="left"))
        hi = int(np.searchsorted(t_ns, T, side="left"))  # t < T
        n = hi - lo
        nwin[j] = n
        if n < 1200:
            continue
        tot = float(cumV[hi - 1] - (cumV[lo - 1] if lo > 0 else 0.0))
        if not np.isfinite(tot) or tot <= 0:
            continue
        # 50 equal-volume buckets over [lo, hi)
        target = tot / float(N_BUCKETS)
        base = float(cumV[lo - 1]) if lo > 0 else 0.0
        baseD = float(cumD[lo - 1]) if lo > 0 else 0.0
        imb = 0.0
        edge = base + target
        start = lo
        # walk 1m bars, cut buckets at volume edges
        for i in range(lo, hi):
            if cumV[i] >= edge or i == hi - 1:
                seg = float(cumD[i]) - (float(cumD[start - 1]) if start > 0 else 0.0)
                # NOTE: cumD[start-1] is D before start; correct segment sum:
                # recompute via base to avoid double-subtract: seg = cumD[i]-cumD[start-1]
                imb += abs(seg)
                start = i + 1
                edge += target
                if start >= hi:
                    break
        vp[j] = imb / tot
        if (j + 1) % 2000 == 0:
            print(f"{coin}: {j+1}/{len(g)} vp mean={np.nanmean(vp[max(0,j-2000):j+1]):.4f}",
                  flush=True)
    df = pd.DataFrame({"T": g, "vpin": vp.astype(np.float64), "nwin": nwin})
    # per-anchor norms + gates (frozen windows)
    df["anchor"] = [anchor_of(t) for t in df["T"]]
    df["mu"] = np.nan
    df["sd"] = np.nan
    df["z"] = np.nan
    df["gate"] = False
    for y, A in enumerate(ANCH):
        a0 = pd.Timestamp(A, tz="UTC")
        w0, w1 = a0 - pd.Timedelta(days=372), a0 - pd.Timedelta(days=7)
        w = df[(df["T"] >= w0) & (df["T"] < w1)]["vpin"].to_numpy(dtype=np.float64)
        w = w[np.isfinite(w)]
        if w.size < 1000:
            print(f"{coin} anchor {A}: only {w.size} norm samples -> never gate", flush=True)
            continue
        mu, sd = float(w.mean()), float(w.std(ddof=1))
        m = (df["anchor"].to_numpy() == y)
        df.loc[m, "mu"] = mu
        df.loc[m, "sd"] = sd
        vv = df.loc[m, "vpin"].to_numpy(dtype=np.float64)
        zz = (vv - mu) / sd if sd > 1e-12 else np.full_like(vv, np.nan)
        df.loc[m, "z"] = zz
        df.loc[m, "gate"] = np.where(np.isfinite(zz), zz > 2.0, False)
    # rows before first anchor never gated (frozen)
    df.loc[df["T"] < pd.Timestamp(ANCH[0], tz="UTC"), "gate"] = False
    df.to_parquet(out, index=False)
    print(f"{coin}: saved {out} gates/yr=" +
          str(df.groupby("anchor")["gate"].sum().to_dict()), flush=True)
    del m, B, S, V, D, cumV, cumD
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coin", default="ALL")
    args = ap.parse_args()
    TMP.mkdir(parents=True, exist_ok=True)
    hb = threading.Thread(target=heartbeat, args=("compute_vpin",), daemon=True)
    hb.start()
    try:
        if args.coin == "ALL":
            for c in COINS:
                compute_coin(c)
        elif args.coin == "NORMS":
            pass
        else:
            compute_coin(args.coin)
        # summary across coins
        total = {}
        for c in COINS:
            p = TMP / f"vpin_{c}.parquet"
            if p.exists():
                d = pd.read_parquet(p, columns=["anchor", "gate"])
                total[c] = d.groupby("anchor")["gate"].sum().to_dict()
        print("GATE SUMMARY (per coin, per anchor-year):", total, flush=True)
    finally:
        _stop_hb.set()


if __name__ == "__main__":
    main()
