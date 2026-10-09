"""Build B7 + breaker grids from 2021-2026 4h closes (CPU-only, closes only). SECONDARY.

Same breaker arithmetic as build_breaker_presample.py applied to bars_4h_4shift
(5 majors x shifts 0..3). Output: breaker_mult_4shift.parquet
(shift, T, boosted_B7, mult_B7, breaker_V1, breaker_V2, mult_V1, mult_V2).
Asserts union triggers per shift == oc_cascadeboost (264/266/263/255) and B7 mults
match oc_cascadeboost boost_mult_4shift.parquet exactly, else STOP.
CONTAMINATED: runs after the primary outcome is logged; no outcome feeds any choice.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BARS = ROOT / "research/tournament/oc_kronoshidden/bars_4h_4shift.parquet"
REFB = ROOT / "research/tournament/oc_cascadeboost/boost_mult_4shift.parquet"

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

MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
SHIFTS = [0, 1, 2, 3]
EXP_UNION_SHIFT = {0: 264, 1: 266, 2: 263, 3: 255}
ANCH = [pd.Timestamp(a, tz="UTC") for a in
        ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")


def main() -> None:
    assert (V1_K, V1_M) == (2, 14) and (V2_K, V2_M) == (3, 21)
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
    A0 = pd.Timestamp("2021-09-24", tz="UTC")
    for s in SHIFTS:
        tc = sorted(set(pd.to_datetime(trig_per_shift[s], utc=True)))
        # REPORT convention (oc_cascadedelay/oc_cascadeboost): union counts OVER THE
        # 5 ANCHOR YEARS (tc >= 2021-09-24); the grid starts 2020-08-01 for the
        # 540-return warmup, so full-grid union is larger (s0 338). Assert anchor-only.
        n_anchor = sum(1 for t in tc if t >= A0)
        assert n_anchor == EXP_UNION_SHIFT[s], \
            f"union shift{s} in-anchor: {n_anchor} != expected {EXP_UNION_SHIFT[s]}"
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
        for y in range(5):
            lo = ANCH[y]
            hi = ANCH[y + 1] if y < 4 else YEAR_END
            n_y = sum(1 for t in tc if lo <= t < hi)
            m = (gt >= lo) & (gt < hi)
            print(f"shift{s} year{y}: triggers={n_y} B7={float(c7[m].mean()):.4f} "
                  f"brV1={float(br1[m].mean()):.4f} brV2={float(br2[m].mean()):.4f}",
                  flush=True)

    out = pd.DataFrame(rows).sort_values(["shift", "T"]).reset_index(drop=True)
    ref = pd.read_parquet(REFB)
    ref["T"] = pd.to_datetime(ref["T"], utc=True)
    merged = out.merge(ref[["shift", "T", "mult_B7"]].rename(columns={"mult_B7": "ref_B7"}),
                       on=["shift", "T"], how="inner")
    assert len(merged) == len(out) == len(ref), (len(merged), len(out), len(ref))
    assert (merged["mult_B7"].to_numpy() == merged["ref_B7"].to_numpy()).all(), \
        "B7 mult mismatch vs oc_cascadeboost"
    assert ((out["mult_V1"] == 1.5) <= (out["mult_B7"] == 1.5)).all()
    assert ((out["mult_V2"] == 1.5) <= (out["mult_B7"] == 1.5)).all()
    out.to_parquet(HERE / "breaker_mult_4shift.parquet", index=False)
    print(f"wrote breaker_mult_4shift.parquet rows={len(out)}", flush=True)


if __name__ == "__main__":
    main()
