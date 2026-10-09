"""Build DD-rank mult panel on pre-sample 4h closes (CPU-only).

Frozen rule (PLAN.md): DD-depth[j] at bar open T[j] from closes C[j-180..j-1]
(180 bars = 30d, min 60 finite), DD=(max-cur)/max; rank finite-DD coins per
(shift, T) deepest-first (ties: sym alpha); V1 deepest 1.25/shallowest 0.75/mid 1.0
(N==1 -> 1.0); V2 top-2 1.25 else 1.0 (N==1 -> 1.0); missing DD -> 1.0.
Reads ONLY the close column of bars_4h_presample.parquet (read-only).
Output: ddrank_mult_presample.parquet (sym,shift,T,dd,mult_V1,mult_V2).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PST = ROOT / "research/tournament/oc_presampletilt"

sys.path.insert(0, str(HERE))
from ddrank_rule import dd_depth_series, rank_mults  # noqa: E402

HB_S = 600


def main() -> None:
    t0 = time.time()
    last_hb = t0
    bars = pd.read_parquet(PST / "bars_4h_presample.parquet",
                           columns=["sym", "shift", "T", "close"])
    bars["T"] = pd.to_datetime(bars["T"], utc=True)
    print(f"loaded bars {len(bars)} syms={sorted(bars['sym'].unique())}", flush=True)
    # per (sym, shift) DD series in T order
    bars = bars.sort_values(["sym", "shift", "T"]).reset_index(drop=True)
    bars["dd"] = np.nan
    for (sym, sh), idx in bars.groupby(["sym", "shift"]).groups.items():
        ii = np.array(sorted(idx))
        closes = bars.loc[ii, "close"].to_numpy(dtype=float)
        bars.loc[ii, "dd"] = dd_depth_series(closes)
        if time.time() - last_hb > HB_S:
            print(f"[hb] dd {sym} s{sh} elapsed={time.time()-t0:.0f}s", flush=True)
            last_hb = time.time()
    n_fin = int(np.isfinite(bars["dd"].to_numpy()).sum())
    print(f"DD finite {n_fin}/{len(bars)} ({n_fin/len(bars):.3f})", flush=True)
    # per (shift, T) ranking
    bars["mult_V1"] = 1.0
    bars["mult_V2"] = 1.0
    for (sh, t), idx in bars.groupby(["shift", "T"]).groups.items():
        ii = list(idx)
        dd = {str(bars.loc[i, "sym"]): float(bars.loc[i, "dd"]) for i in ii}
        m = rank_mults(dd)
        for i in ii:
            v1, v2 = m[str(bars.loc[i, "sym"])]
            bars.at[i, "mult_V1"] = v1
            bars.at[i, "mult_V2"] = v2
        if time.time() - last_hb > HB_S:
            print(f"[hb] rank s{sh} {t} elapsed={time.time()-t0:.0f}s", flush=True)
            last_hb = time.time()
    vals1 = sorted(bars["mult_V1"].unique().tolist())
    vals2 = sorted(bars["mult_V2"].unique().tolist())
    print(f"V1 values {vals1} V2 values {vals2}", flush=True)
    print(f"V1 boosted share {(bars['mult_V1']==1.25).mean():.4f} "
          f"deweighted {(bars['mult_V1']==0.75).mean():.4f}; "
          f"V2 boosted {(bars['mult_V2']==1.25).mean():.4f}", flush=True)
    out = bars[["sym", "shift", "T", "dd", "mult_V1", "mult_V2"]].copy()
    out.to_parquet(HERE / "ddrank_mult_presample.parquet", index=False)
    print(f"wrote ddrank_mult_presample.parquet {len(out)} rows "
          f"elapsed={(time.time()-t0)/60:.1f}min", flush=True)


if __name__ == "__main__":
    main()
