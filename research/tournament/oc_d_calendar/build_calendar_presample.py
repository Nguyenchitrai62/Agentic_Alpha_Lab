"""Build frozen calendar mult panels on the pre-sample 4h grid (CPU-only, timestamps only).

Reads read-only oc_presampletilt/bars_4h_presample.parquet (uses ONLY the T column;
no price is read for the trigger) and writes calendar_mult_presample.parquet
(shift, T, mult_V1, mult_V2) with V1 = 1.25 Sat/Sun UTC else 1.0 and
V2 = 1.2 00-08 UTC else 1.0.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PST = ROOT / "research/tournament/oc_presampletilt"

sys.path.insert(0, str(HERE))
from calendar_rule import mult_V1, mult_V2  # noqa: E402


def main() -> None:
    bars = pd.read_parquet(PST / "bars_4h_presample.parquet", columns=["shift", "T"])
    bars["T"] = pd.to_datetime(bars["T"], utc=True)
    print(f"grid rows={len(bars)} shifts={sorted(bars['shift'].unique())}", flush=True)
    out = bars[["shift", "T"]].copy()
    out["mult_V1"] = [mult_V1(t) for t in out["T"]]
    out["mult_V2"] = [mult_V2(t) for t in out["T"]]
    out = out.sort_values(["shift", "T"]).reset_index(drop=True)
    out.to_parquet(HERE / "calendar_mult_presample.parquet", index=False)
    for v in ("mult_V1", "mult_V2"):
        print(f"{v}: boosted time-bar share={float((out[v] > 1.0).mean()):.4f}", flush=True)
    print("wrote calendar_mult_presample.parquet", flush=True)


if __name__ == "__main__":
    main()
