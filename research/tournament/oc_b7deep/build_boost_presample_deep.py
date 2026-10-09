"""Build B7 window flags from PRE-SAMPLE 4h closes (CPU-only).

Trigger arithmetic VERBATIM oc_cascadedelay/oc_cascadeboost/oc_cboostpre;
deep-rung gating happens at join time (window flag x ledger rung), so this
script stores only the market-wide B7 window per (shift, T).

Per (sym, shift): r[i] = ln(C[i]/C[i-1]); SIG[i] = std of r[i-540..i-1]
(min_periods 120); trigger iff |r[i]| > 4*SIG[i]; tc = T[i]+4h.
Per shift: union tc over available majors -> boosted_B7 on the shift grid
(0 < T-tc <= 7d).
Output: boost_mult_presample_deep.parquet (shift, T, boosted_B7, mult_B7).
Read-only input bars; writes only this folder. Equality vs the frozen
oc_cboostpre parquet is asserted in compute (same grid expected).
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
from b7deep_rule import (  # noqa: E402
    BOOST,
    BOOST_DAYS,
    boosted_mask,
    triggers_of,
)

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
    assert BOOST == 1.5 and BOOST_DAYS == 7
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
                print(f"[hb] build presample-deep alive elapsed {last_hb - t0:.0f}s",
                      flush=True)

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
        for leg in LEG_ORDER:
            lo, hi = LEGS[leg]
            n_y = sum(1 for t in tc if lo <= t < hi)
            m = (gt >= lo) & (gt < hi)
            print(f"shift{s} {leg}: triggers={n_y} "
                  f"boostedB7={float(cb[m].mean()):.4f}", flush=True)

    out = pd.DataFrame(rows).sort_values(["shift", "T"]).reset_index(drop=True)
    out.to_parquet(HERE / "boost_mult_presample_deep.parquet", index=False)
    print(f"total triggers (4 sym x 4 shifts, union per shift later): {n_trig_total}",
          flush=True)
    print(f"wrote boost_mult_presample_deep.parquet rows={len(out)} "
          f"boostedB7={int(out['boosted_B7'].sum())}", flush=True)


if __name__ == "__main__":
    main()
