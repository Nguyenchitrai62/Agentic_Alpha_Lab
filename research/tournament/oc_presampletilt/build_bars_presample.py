"""oc_presampletilt: build 4h OHLC bars from the spot pre-sample 1m store.

Frozen grid (see PLAN.md): ORIGIN = 2020-01-01 00:00 UTC, bar j of phase s covers
[ORIGIN + s h + 4h*j, +4h) for ALL integer j (negative j extends back to 2017),
phases s in {0,1,2,3}. Per (sym, shift): open = first finite open, high = max high,
low = min low, close = last finite close, nmin = finite-minute count; a 4h bar with
zero finite minutes is NaN (never traded).

Output: bars_4h_presample.parquet (sym, shift, T, open, high, low, close, nmin).
CPU-only, one coin at a time. Heartbeat every 600 s.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SPOT = ROOT / "data/raw/spot_1m_presample_20261007"
OUT = HERE / "bars_4h_presample.parquet"
TMP = HERE / "tmp"

ORIGIN = pd.Timestamp("2020-01-01", tz="UTC")
PHASES = (0, 1, 2, 3)
SYMS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT")
HB_S = 600


def build_one(sym: str) -> pd.DataFrame:
    m = pd.read_parquet(SPOT / f"{sym}.parquet")
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.sort_values("open_time").reset_index(drop=True)
    # finite-minute mask (all four OHLC finite)
    fin = (np.isfinite(m["o"].to_numpy(dtype=float))
           & np.isfinite(m["h"].to_numpy(dtype=float))
           & np.isfinite(m["l"].to_numpy(dtype=float))
           & np.isfinite(m["c"].to_numpy(dtype=float)))
    out = []
    for s in PHASES:
        sh = pd.Timedelta(hours=s)
        secs = ((m["open_time"] - (ORIGIN + sh)).dt.total_seconds() // 14400 * 14400)
        T = (ORIGIN + sh) + pd.to_timedelta(secs.to_numpy(dtype="float64"), unit="s")
        T = pd.DatetimeIndex(T, tz="UTC")
        g = m.assign(_T=T, _fin=fin).groupby("_T", sort=True)
        o = g.apply(lambda d: d.loc[d["_fin"], "o"].iloc[0]
                    if d["_fin"].any() else np.nan, include_groups=False)
        h = g.apply(lambda d: d.loc[d["_fin"], "h"].max()
                    if d["_fin"].any() else np.nan, include_groups=False)
        lo = g.apply(lambda d: d.loc[d["_fin"], "l"].min()
                     if d["_fin"].any() else np.nan, include_groups=False)
        c = g.apply(lambda d: d.loc[d["_fin"], "c"].iloc[-1]
                    if d["_fin"].any() else np.nan, include_groups=False)
        n = g["_fin"].sum()
        df = pd.DataFrame({"T": o.index, "open": o.to_numpy(dtype=float),
                           "high": h.to_numpy(dtype=float),
                           "low": lo.to_numpy(dtype=float),
                           "close": c.to_numpy(dtype=float),
                           "nmin": n.to_numpy(dtype=np.int64)})
        df["sym"], df["shift"] = sym, s
        out.append(df)
    del m
    return pd.concat(out, ignore_index=True)


def main() -> None:
    t0 = time.time()
    last_hb = t0
    TMP.mkdir(parents=True, exist_ok=True)
    res = []
    done: set = set()
    if OUT.exists():
        prev = pd.read_parquet(OUT)
        res.append(prev)
        done = set(zip(prev["sym"], prev["shift"]))
        print("resume: groups already done", sorted(done), flush=True)
    for sym in SYMS:
        need = [s for s in PHASES if (sym, s) not in done]
        if not need:
            continue
        df = build_one(sym)
        df = df[df["shift"].isin(need)].reset_index(drop=True)
        res.append(df)
        pd.concat(res, ignore_index=True).to_parquet(OUT)
        print(f"coin done {sym} n={len(df)} elapsed {(time.time() - t0) / 60:.1f}min",
              flush=True)
        if time.time() - last_hb >= HB_S:
            last_hb = time.time()
            print(f"[hb] build_bars_presample alive elapsed {last_hb - t0:.0f}s",
                  flush=True)
    out = pd.concat(res, ignore_index=True)
    out.to_parquet(OUT)
    print(f"saved {OUT} rows={len(out)} range={out['T'].min()}..{out['T'].max()} "
          f"runtime {(time.time() - t0) / 60:.1f}min", flush=True)


if __name__ == "__main__":
    main()
