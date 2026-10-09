"""Build tapered-boost grids from PRE-SAMPLE 4h closes (CPU-only).

Trigger arithmetic VERBATIM oc_cascadedelay/oc_cascadeboost/oc_cboostpre;
only new logic: per-shift taper mults (taper_rule.mults_on_grid)
with V1 step (1.6/1.3/1.0) / V2 exp (1+0.5*2^(-d/3)); window 7d.

Per (sym, shift): r[i] = ln(C[i]/C[i-1]); SIG[i] = std of r[i-540..i-1]
(min_periods 120); trigger iff |r[i]| > 4*SIG[i]; tc = T[i]+4h.
Per shift: union tc over available majors -> (mult_V1, mult_V2) on the grid.
Output: boost_mult_presample_taper.parquet (shift, T, mult_V1, mult_V2,
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
BARS = ROOT / "research/tournament/oc_presampletilt/bars_4h_presample.parquet"

sys.path.insert(0, str(HERE))
from taper_rule import BOOST_DAYS, mults_on_grid, triggers_of  # noqa: E402

MAJORS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT"]  # SOL absent pre-sample
SHIFTS = [0, 1, 2, 3]
LEGS = {
    "Y2017": (pd.Timestamp("2017-10-16", tz="UTC"), pd.Timestamp("2018-01-01", tz="UTC")),
    "Y2018": (pd.Timestamp("2018-01-01", tz="UTC"), pd.Timestamp("2019-01-01", tz="UTC")),
    "Y2019": (pd.Timestamp("2019-01-01", tz="UTC"), pd.Timestamp("2020-01-01", tz="UTC")),
    "Y2020p": (pd.Timestamp("2020-01-01", tz="UTC"), pd.Timestamp("2020-09-01", tz="UTC")),
}
LEG_ORDER = ("Y2017", "Y2018", "Y2019", "Y2020p")
HB_S = 600


def main() -> None:
    t0 = time.time()
    last_hb = t0
    assert BOOST_DAYS == 7
    print("loading pre-sample bars...", flush=True)
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
                print(f"[hb] build presample-taper alive elapsed {last_hb - t0:.0f}s",
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
        for leg in LEG_ORDER:
            lo, hi = LEGS[leg]
            n_y = sum(1 for t in tc if lo <= t < hi)
            m = (gt >= lo) & (gt < hi)
            print(f"shift{s} {leg}: triggers={n_y} "
                  f"boostedV1={float(b1[m].mean()):.4f} "
                  f"boostedV2={float(b2[m].mean()):.4f} "
                  f"meanV1={float(m1[m].mean()):.4f} meanV2={float(m2[m].mean()):.4f}",
                  flush=True)

    out = pd.DataFrame(rows).sort_values(["shift", "T"]).reset_index(drop=True)
    out.to_parquet(HERE / "boost_mult_presample_taper.parquet", index=False)
    print(f"total triggers (4 sym x 4 shifts, union per shift later): {n_trig_total}",
          flush=True)
    print(f"wrote boost_mult_presample_taper.parquet rows={len(out)} "
          f"boostedV1={int(out['boosted_V1'].sum())} "
          f"boostedV2={int(out['boosted_V2'].sum())}", flush=True)


if __name__ == "__main__":
    main()
