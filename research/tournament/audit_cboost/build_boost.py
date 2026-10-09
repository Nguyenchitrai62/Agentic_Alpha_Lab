"""audit_cboost build_boost: CPU-only 4h closes -> boost_mult_4shift.parquet.

Independent rebuild from the frozen spec. Prints progress.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import boost_rule as br

BARS = ROOT / "research/tournament/oc_kronoshidden/bars_4h_4shift.parquet"
OUT = HERE / "boost_mult_4shift.parquet"
COUNTS = HERE / "tmp" / "trigger_counts.json"

ANCH = [pd.Timestamp(a, tz="UTC") for a in br.ANCH5]
DEV0 = pd.Timestamp("2021-09-24", tz="UTC")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")


def main() -> None:
    t0 = time.time()
    print(f"[audit_cboost {datetime.now(timezone.utc):%H:%M:%S}Z] loading bars", flush=True)
    df = pd.read_parquet(BARS, columns=["sym", "shift", "T", "close"])
    df["T"] = pd.to_datetime(df["T"], utc=True)
    df = df.sort_values(["shift", "sym", "T"]).reset_index(drop=True)
    print(f"[audit_cboost] bars rows={len(df)} syms={sorted(df.sym.unique())}", flush=True)

    per_shift_tc: dict[int, list] = {}
    trig_detail = []  # (sym, shift, T, tc)
    nan_sig = 0
    nonfinite = 0
    total_bars = 0
    for (sym, shift), g in df.groupby(["sym", "shift"], sort=True):
        g = g.sort_values("T").reset_index(drop=True)
        T = g["T"].to_numpy()
        C = g["close"].to_numpy(dtype=float)
        total_bars += len(g)
        nonfinite += int((~np.isfinite(C)).sum())
        fires = br.triggers_of(T, C)
        tcs = br.trigger_close_times(T, fires)
        per_shift_tc.setdefault(int(shift), []).extend(list(tcs))
        for t, f in zip(g["T"][fires], tcs):
            trig_detail.append((str(sym), int(shift), str(pd.Timestamp(t)), str(pd.Timestamp(f))))
        # count NaN-sigma bars (conservative never-fire): recompute sigma NaN count
        r = br.close_returns(C)
        sig = br.trailing_sigma(r)
        nan_sig += int((~np.isfinite(sig)).sum())
    print(f"[audit_cboost] total bars={total_bars} nonfinitecloses={nonfinite} nanSIGbars={nan_sig} "
          f"triggers={len(trig_detail)} elapsed={(time.time()-t0)/60:.1f}min", flush=True)

    # union grid per shift + boosted mask
    rows = []
    counts = {}
    for s in range(4):
        g = df[df["shift"] == s].sort_values("T")
        grid = pd.DatetimeIndex(sorted(g["T"].unique()))
        tcs = pd.DatetimeIndex(sorted(set(per_shift_tc.get(s, []))))
        b = br.boosted_mask(grid.values, tcs.values, n_days=br.B7_DAYS)
        for t, bb in zip(grid, b):
            rows.append((int(s), pd.Timestamp(t), bool(bb), br.BOOST if bb else 1.0))
        # counts per anchor year on this shift's grid
        sh = pd.Timedelta(hours=s)
        for y, a in enumerate(ANCH):
            a0 = a + sh
            a1 = a0 + pd.Timedelta(days=365)
            n_trig = int(sum(1 for (_, ss, _, tc) in trig_detail
                             if ss == s and a0 <= pd.Timestamp(tc) < a1))
            seg = (grid >= a0) & (grid < a1)
            n_bar = int(seg.sum())
            n_boost = int(b[seg].sum()) if n_bar else 0
            counts[f"{a.date()}_s{s}"] = dict(n_triggers=n_trig, n_bars=n_bar,
                                              n_boosted=int(n_boost),
                                              share=round(n_boost / n_bar, 6) if n_bar else None)
        n_all_trig = len(set(tcs))
        print(f"[audit_cboost] shift {s}: grid={len(grid)} triggers_distinct_tc={n_all_trig} "
              f"boosted={int(b.sum())} share={float(b.mean()):.4f}", flush=True)

    out = pd.DataFrame(rows, columns=["shift", "T", "boosted_B7", "mult_B7"])
    out = out.sort_values(["shift", "T"]).reset_index(drop=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    COUNTS.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    COUNTS.write_text(json.dumps({
        "meta": {"source": str(BARS), "thresh": br.THRESH, "window": br.SIG_WINDOW,
                 "min_periods": br.SIG_MIN, "N_days": br.B7_DAYS, "boost": br.BOOST,
                 "total_bars": total_bars, "nonfinite_closes": nonfinite,
                 "nan_sig_bars": nan_sig, "n_trigger_rows": len(trig_detail)},
        "per_year_shift": counts,
    }, indent=1))
    print(f"[audit_cboost] wrote {OUT} rows={len(out)} + {COUNTS} "
          f"elapsed={(time.time()-t0)/60:.1f}min", flush=True)


if __name__ == "__main__":
    main()
