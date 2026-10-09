"""Build B7 window flags from 2021-2026 4h closes (CPU-only).

SECONDARY, CONTAMINATED leg (info only): same verbatim B7 window as the
primary (7d at 1.5 from ANY >4sg trigger, market-wide per shift), applied to
oc_kronoshidden 4h closes (5 majors). Deep-rung gating happens at join time.
Output: boost_mult_4shift_deep.parquet (shift, T, boosted_B7, mult_B7).
Read-only input bars; writes only this folder.
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
from b7deep_rule import (  # noqa: E402
    BOOST,
    BOOST_DAYS,
    boosted_mask,
    triggers_of,
)

MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
SHIFTS = [0, 1, 2, 3]
ANCH = [pd.Timestamp(a, tz="UTC") for a in
        ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")


def main() -> None:
    assert BOOST == 1.5 and BOOST_DAYS == 7
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
        cb = boosted_mask(grid, np.sort(tc_ns), BOOST_DAYS)
        gt = pd.to_datetime(grid, utc=True)
        for T, a in zip(gt, cb):
            rows.append({"shift": s, "T": T, "boosted_B7": bool(a),
                         "mult_B7": BOOST if a else 1.0})
        for y in range(5):
            lo = ANCH[y]
            hi = ANCH[y + 1] if y < 4 else YEAR_END
            n_y = sum(1 for t in tc if lo <= t < hi)
            m = (gt >= lo) & (gt < hi)
            print(f"shift{s} year{y}: triggers={n_y} "
                  f"B7={float(cb[m].mean()):.4f}", flush=True)

    out = pd.DataFrame(rows).sort_values(["shift", "T"]).reset_index(drop=True)
    out.to_parquet(HERE / "boost_mult_4shift_deep.parquet", index=False)
    print(f"total triggers (5 sym x 4 shifts, union per shift later): {n_trig_total}",
          flush=True)
    print(f"wrote boost_mult_4shift_deep.parquet rows={len(out)} "
          f"boostedB7={int(out['boosted_B7'].sum())}", flush=True)


if __name__ == "__main__":
    main()
