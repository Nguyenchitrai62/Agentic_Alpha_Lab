"""Build B7 + breaker grids from PRE-SAMPLE 4h closes (CPU-only, closes only).

Trigger/B7 arithmetic VERBATIM oc_cboostpre build_boost_presample.py; breaker gate
(IDEAS7 #4, PLAN frozen reading) added on top:
  C(T,s) = #{union tc: tc <= T and T-tc <= M days}; breaker iff C >= K.
  mult_V = 1.0 if breaker else mult_B7. V1 K=2/M=14; V2 K=3/M=21.

Per (sym, shift): r[i] = ln(C[i]/C[i-1]); SIG[i] = std of r[i-540..i-1]
(min_periods 120); trigger iff |r[i]| > 4*SIG[i]; tc = T[i]+4h.
Per shift: union tc over available majors -> B7 window + breaker counts.
Output: breaker_mult_presample.parquet (shift, T, boosted_B7, mult_B7,
breaker_V1, breaker_V2, mult_V1, mult_V2). Read-only input bars; writes only this folder.
Asserts union counts match oc_cboostpre + B7 mults match (else STOP).
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
CBOOSTPRE = ROOT / "research/tournament/oc_cboostpre/boost_mult_presample.parquet"

sys.path.insert(0, str(HERE))
from breaker_rule import (  # noqa: E402
    B7_DAYS,
    BOOST,
    V1_K,
    V1_M,
    V2_K,
    V2_M,
    boosted_mask,
    breaker_active_mask,
    breaker_mult,
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
EXP_UNION = {  # oc_cboostpre REPORT union triggers per (year, shift)
    "Y2017": {0: 8, 1: 12, 2: 9, 3: 11},
    "Y2018": {0: 43, 1: 42, 2: 47, 3: 46},
    "Y2019": {0: 46, 1: 53, 2: 49, 3: 57},
    "Y2020p": {0: 31, 1: 39, 2: 31, 3: 29},
}
HB_S = 600


def main() -> None:
    t0 = time.time()
    last_hb = t0
    assert (V1_K, V1_M) == (2, 14) and (V2_K, V2_M) == (3, 21)
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
                print(f"[hb] build_breaker_presample alive elapsed {last_hb - t0:.0f}s",
                      flush=True)

    rows = []
    for s in SHIFTS:
        tc = sorted(set(pd.to_datetime(trig_per_shift[s], utc=True)))
        tc_ns = np.array([t.value for t in tc], dtype=np.int64)
        grid = np.array(sorted(set(
            b[b["shift"] == s]["T"].values.astype("datetime64[ns]").astype(np.int64))),
            dtype=np.int64)
        c7 = boosted_mask(grid, tc_ns, B7_DAYS)
        br1 = breaker_active_mask(grid, tc_ns, V1_K, V1_M)
        br2 = breaker_active_mask(grid, tc_ns, V2_K, V2_M)
        m_b7 = np.where(c7, BOOST, 1.0)
        m_v1 = breaker_mult(c7, br1)
        m_v2 = breaker_mult(c7, br2)
        gt = pd.to_datetime(grid, utc=True)
        for T, a, b1, b2, mb, mv1, mv2 in zip(gt, c7, br1, br2, m_b7, m_v1, m_v2):
            rows.append({"shift": s, "T": T, "boosted_B7": bool(a),
                         "mult_B7": float(mb),
                         "breaker_V1": bool(b1), "breaker_V2": bool(b2),
                         "mult_V1": float(mv1), "mult_V2": float(mv2)})
        for leg in LEG_ORDER:
            lo, hi = LEGS[leg]
            n_y = sum(1 for t in tc if lo <= t < hi)
            exp = EXP_UNION[leg][s]
            assert n_y == exp, f"union {leg} s{s}: {n_y} != expected {exp}"
            m = (gt >= lo) & (gt < hi)
            print(f"shift{s} {leg}: triggers={n_y} (exp {exp}) "
                  f"B7={float(c7[m].mean()):.4f} brV1={float(br1[m].mean()):.4f} "
                  f"brV2={float(br2[m].mean()):.4f} "
                  f"multV1mean={float(m_v1[m].mean()):.4f} multV2mean={float(m_v2[m].mean()):.4f}",
                  flush=True)

    out = pd.DataFrame(rows).sort_values(["shift", "T"]).reset_index(drop=True)
    # B7 identity check vs oc_cboostpre grid
    ref = pd.read_parquet(CBOOSTPRE)
    ref["T"] = pd.to_datetime(ref["T"], utc=True)
    merged = out.merge(ref[["shift", "T", "mult_B7"]].rename(columns={"mult_B7": "ref_B7"}),
                       on=["shift", "T"], how="inner")
    assert len(merged) == len(out) == len(ref), (len(merged), len(out), len(ref))
    assert (merged["mult_B7"].to_numpy() == merged["ref_B7"].to_numpy()).all(), \
        "B7 mult mismatch vs oc_cboostpre"
    # V-subset invariant: boosted V bars subset of B7 bars
    assert ((out["mult_V1"] == 1.5) <= (out["mult_B7"] == 1.5)).all()
    assert ((out["mult_V2"] == 1.5) <= (out["mult_B7"] == 1.5)).all()
    out.to_parquet(HERE / "breaker_mult_presample.parquet", index=False)
    print(f"total triggers (4 sym x 4 shifts): {n_trig_total} (exp 915)", flush=True)
    assert n_trig_total == 915, n_trig_total
    print(f"wrote breaker_mult_presample.parquet rows={len(out)} "
          f"B7={int(out['boosted_B7'].sum())} brV1={int(out['breaker_V1'].sum())} "
          f"brV2={int(out['breaker_V2'].sum())} V1boost={int((out['mult_V1'] == 1.5).sum())} "
          f"V2boost={int((out['mult_V2'] == 1.5).sum())}", flush=True)


if __name__ == "__main__":
    main()
