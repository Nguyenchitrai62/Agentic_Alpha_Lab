"""Build post-cascade cooldown grids from 4h closes (CPU-only, closes only).

Per (sym, shift): r[i] = ln(C[i]/C[i-1]); SIG[i] = std of r[i-540..i-1]
(min_periods 120); trigger iff |r[i]| > 4*SIG[i]; tc = T[i]+4h.
Per shift: union tc over the 5 majors -> cooled_V1/V2 on the shift grid.
Output: delay_mult_4shift.parquet (shift, T, cooled_V1, cooled_V2, mult_V1,
mult_V2). Read-only input bars; writes only this folder.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BARS = ROOT / "research/tournament/oc_kronoshidden/bars_4h_4shift.parquet"

sys.path.insert(0, str(HERE))
from delay_rule import HALF, V1_DAYS, V2_DAYS, cooled_mask, triggers_of

MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
SHIFTS = [0, 1, 2, 3]
ANCH = [pd.Timestamp(a, tz="UTC") for a in
        ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")


def main() -> None:
    print("loading bars...", flush=True)
    b = pd.read_parquet(BARS)
    b["T"] = pd.to_datetime(b["T"], utc=True)
    print(f"bars rows={len(b)} Trange={b['T'].min()}..{b['T'].max()}", flush=True)

    trig_per_shift: dict[int, list] = {s: [] for s in SHIFTS}
    n_trig_total = 0
    for sym in MAJORS:
        for s in SHIFTS:
            sub = b[(b["sym"] == sym) & (b["shift"] == s)].sort_values("T")
            t = pd.to_datetime(sub["T"], utc=True)
            c = sub["close"].to_numpy(dtype=float)
            fire = triggers_of(c)
            n = int(fire.sum())
            n_trig_total += n
            tc = (t[fire] + pd.Timedelta(hours=4)).tolist()
            trig_per_shift[s].extend(tc)
            print(f"triggers {sym} shift{s}: {n}/{len(sub)}", flush=True)

    rows = []
    for s in SHIFTS:
        tc = sorted(set(pd.to_datetime(trig_per_shift[s], utc=True)))
        tc_ns = np.array([t.value for t in tc], dtype=np.int64)
        grid = np.array(sorted(set(
            b[b["shift"] == s]["T"].values.astype("datetime64[ns]").astype(np.int64))),
            dtype=np.int64)
        c1 = cooled_mask(grid, tc_ns, V1_DAYS)
        c2 = cooled_mask(grid, tc_ns, V2_DAYS)
        gt = pd.to_datetime(grid, utc=True)
        for T, a, cc in zip(gt, c1, c2):
            rows.append({"shift": s, "T": T, "cooled_V1": bool(a),
                         "cooled_V2": bool(cc),
                         "mult_V1": HALF if a else 1.0,
                         "mult_V2": HALF if cc else 1.0})
        # trigger counts per calendar anchor year (disclosed convention)
        for y in range(5):
            lo = ANCH[y]
            hi = ANCH[y + 1] if y < 4 else YEAR_END
            n_y = sum(1 for t in tc if lo <= t < hi)
            share1 = float(c1[(gt >= lo) & (gt < hi)].mean()) if (gt >= lo).any() else 0.0
            print(f"shift{s} year{y}: triggers={n_y} cooled_share_V1={share1:.4f} "
                  f"V2={float(c2[(gt >= lo) & (gt < hi)].mean()):.4f}", flush=True)

    out = pd.DataFrame(rows).sort_values(["shift", "T"]).reset_index(drop=True)
    out.to_parquet(HERE / "delay_mult_4shift.parquet", index=False)
    print(f"total triggers (5 sym x 4 shifts, union per shift later): {n_trig_total}",
          flush=True)
    print(f"wrote delay_mult_4shift.parquet rows={len(out)} "
          f"cooledV1={int(out['cooled_V1'].sum())} cooledV2={int(out['cooled_V2'].sum())}",
          flush=True)


if __name__ == "__main__":
    main()
