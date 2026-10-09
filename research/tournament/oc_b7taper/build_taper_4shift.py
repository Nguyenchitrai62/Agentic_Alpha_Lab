"""Build tapered-boost grids from 2021-2026 4h closes (CPU-only, SECONDARY).

Same frozen taper as build_taper_presample.py, applied to the 5-major
2021-2026 grid (oc_kronoshidden/bars_4h_4shift.parquet). CONTAMINATED leg
(info only): idea derived from cascade results covering these years.
Output: boost_mult_4shift_taper.parquet (shift, T, mult_V1, mult_V2,
boosted_V1, boosted_V2). Read-only input bars; writes only this folder.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BARS = ROOT / "research/tournament/oc_kronoshidden/bars_4h_4shift.parquet"

sys.path.insert(0, str(HERE))
from taper_rule import BOOST_DAYS, mults_on_grid, triggers_of  # noqa: E402

MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
SHIFTS = [0, 1, 2, 3]
ANCH = [pd.Timestamp(a, tz="UTC") for a in
        ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
HB_S = 600


def main() -> None:
    t0 = time.time()
    last_hb = t0
    assert BOOST_DAYS == 7
    print("loading 4h bars...", flush=True)
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
            if time.time() - last_hb >= HB_S:
                last_hb = time.time()
                print(f"[hb] build 4shift-taper alive elapsed {last_hb - t0:.0f}s",
                      flush=True)

    rows = []
    for s in SHIFTS:
        tc = sorted(set(pd.to_datetime(trig_per_shift[s], utc=True)))
        tc_ns = np.array([t.value for t in tc], dtype=np.int64)
        grid = np.array(sorted(set(
            b[b["shift"] == s]["T"].values.astype("datetime64[ns]").astype(np.int64))),
            dtype=np.int64)
        m1, m2, _dd = mults_on_grid(grid, tc_ns)
        b1 = m1 > 1.0 + 1e-12
        b2 = m2 > 1.0 + 1e-12
        gt = pd.to_datetime(grid, utc=True)
        for T, a, cc, f1, f2 in zip(gt, m1, m2, b1, b2):
            rows.append({"shift": s, "T": T, "mult_V1": float(a),
                         "mult_V2": float(cc), "boosted_V1": bool(f1),
                         "boosted_V2": bool(f2)})
        for y in range(5):
            lo = ANCH[y]
            hi = ANCH[y + 1] if y < 4 else YEAR_END
            n_y = sum(1 for t in tc if lo <= t < hi)
            m = (gt >= lo) & (gt < hi)
            print(f"shift{s} year{y}: triggers={n_y} "
                  f"boostedV1={float(b1[m].mean()):.4f} "
                  f"boostedV2={float(b2[m].mean()):.4f}", flush=True)

    out = pd.DataFrame(rows).sort_values(["shift", "T"]).reset_index(drop=True)
    out.to_parquet(HERE / "boost_mult_4shift_taper.parquet", index=False)
    print(f"total triggers (5 sym x 4 shifts, union per shift later): {n_trig_total}",
          flush=True)
    print(f"wrote boost_mult_4shift_taper.parquet rows={len(out)} "
          f"boostedV1={int(out['boosted_V1'].sum())} "
          f"boostedV2={int(out['boosted_V2'].sum())}", flush=True)


if __name__ == "__main__":
    main()
