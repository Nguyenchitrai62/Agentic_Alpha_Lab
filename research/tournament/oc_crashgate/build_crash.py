"""oc_crashgate build_crash: trailing-30d BTC max-DD-depth per shift (CPU-only).

Input (read-only): research/tournament/oc_kronoshidden/bars_4h_4shift.parquet
  (BTCUSDT closes, existing 4h closes, no new data).
Definition (frozen PLAN.md): at holding-bar open T on shift s, window = BTC closes
  with close_time in (T - 30d, T] on that shift's grid (= closes[i-180:i] with
  i = index of bar open T). depth(T) = max peak-to-trough, floored at 0.
  NaN when < 2 closes (early history only).
Output: crash_depth_4shift.parquet (sym, shift, T, close_time, close, depth).
CPU-only, tiny (4 x ~13.5k rows).
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BARS = ROOT / "research/tournament/oc_kronoshidden/bars_4h_4shift.parquet"
OUT = HERE / "crash_depth_4shift.parquet"

WINDOW_BARS = 180  # 30d of 4h bars

sys.path.insert(0, str(HERE))
from tilt_rule import depth_of_window  # noqa: E402


def main() -> None:
    t0 = time.time()
    print(f"[build_crash {datetime.now(timezone.utc):%H:%M:%S}Z] start", flush=True)
    df = pd.read_parquet(BARS, columns=["sym", "shift", "T", "close"])
    df = df[df["sym"] == "BTCUSDT"].copy()
    df["T"] = pd.to_datetime(df["T"], utc=True)
    parts = []
    for shift in (0, 1, 2, 3):
        sub = df[df["shift"] == shift].sort_values("T").reset_index(drop=True)
        closes = sub["close"].to_numpy(dtype=float)
        Ts = pd.to_datetime(sub["T"], utc=True)
        depths = np.empty(len(sub), dtype=float)
        for i in range(len(sub)):
            lo = max(0, i - WINDOW_BARS)
            depths[i] = depth_of_window(closes[lo:i])
        part = pd.DataFrame({
            "sym": "BTCUSDT",
            "shift": np.int64(shift),
            "T": Ts.values,
            "close_time": (Ts + pd.Timedelta(hours=4)).values,
            "close": closes,
            "depth": depths,
        })
        parts.append(part)
        finite = np.isfinite(depths)
        print(f"shift {shift}: n={len(sub)} finite={int(finite.sum())} "
              f"depth p50={float(np.quantile(depths[finite], 0.5)):.4f} "
              f"p90={float(np.quantile(depths[finite], 0.9)):.4f} "
              f"max={float(np.nanmax(depths)):.4f} "
              f"share>=15%={float((depths >= 0.15).mean()):.4f} "
              f"share>=10%={float((depths >= 0.10).mean()):.4f}", flush=True)
    out = pd.concat(parts, ignore_index=True).sort_values(["shift", "T"]).reset_index(drop=True)
    out.to_parquet(OUT, index=False)
    print(f"wrote {OUT} rows={len(out)} elapsed={(time.time()-t0):.1f}s", flush=True)


if __name__ == "__main__":
    main()
