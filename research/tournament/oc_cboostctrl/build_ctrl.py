"""Build CTRL_R frozen inputs: trigger counts k_{y,s} + 20-seed random starts.

CPU-only, closes only. Trigger arithmetic verbatim oc_cascadeboost (4.0/540/120,
union over 5 majors per shift). Grid per shift read from the read-only B7 parquet
(same base as B7). Writes only this folder's tmp/:
  tmp/ctrl_counts.json  (k per (y,s), grid sizes, trigger totals, seeds, seeds scheme)
  tmp/ctrlR_starts.pkl  ({(y,s,j): sorted start-ns list} + metadata)
Deterministic from frozen seeds; no engine outcome is read.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BARS = ROOT / "research/tournament/oc_kronoshidden/bars_4h_4shift.parquet"
B7PQ = ROOT / "research/tournament/oc_cascadeboost/boost_mult_4shift.parquet"

import sys

sys.path.insert(0, str(HERE))
from ctrl_rule import N_SEEDS, SEED_BASE, seed_of, triggers_of  # noqa: E402

MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
SHIFTS = [0, 1, 2, 3]
ANCH = [pd.Timestamp(a, tz="UTC") for a in
        ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
LIVE1_FULL = {s: pd.Timestamp("2026-09-23", tz="UTC") + pd.Timedelta(hours=s)
              for s in SHIFTS}


def main() -> None:
    print("loading bars + B7 grid...", flush=True)
    b = pd.read_parquet(BARS)
    b["T"] = pd.to_datetime(b["T"], utc=True)
    g = pd.read_parquet(B7PQ, columns=["shift", "T"])
    g["T"] = pd.to_datetime(g["T"], utc=True)

    trig_per_shift: dict[int, list] = {s: [] for s in SHIFTS}
    for sym in MAJORS:
        for s in SHIFTS:
            sub = b[(b["sym"] == sym) & (b["shift"] == s)].sort_values("T")
            fire = triggers_of(sub["close"].to_numpy(dtype=float))
            tc = (pd.to_datetime(sub["T"], utc=True)[fire]
                  + pd.Timedelta(hours=4)).tolist()
            trig_per_shift[s].extend(tc)
            print(f"triggers {sym} shift{s}: {int(fire.sum())}/{len(sub)}",
                  flush=True)

    counts: dict[str, dict[str, int]] = {}
    grid_sizes: dict[str, dict[str, int]] = {}
    union_totals = {}
    for s in SHIFTS:
        tc = sorted(set(pd.to_datetime(trig_per_shift[s], utc=True)))
        union_totals[str(s)] = len(tc)
        grid_s = np.array(sorted(
            pd.to_datetime(g[g["shift"] == s]["T"], utc=True).values.astype(
                "datetime64[ns]").astype(np.int64)), dtype=np.int64)
        gt = pd.to_datetime(grid_s, utc=True)
        counts[str(s)] = {}
        grid_sizes[str(s)] = {}
        for y in range(5):
            lo = ANCH[y] + pd.Timedelta(hours=s)
            hi = min(ANCH[y] + pd.Timedelta(days=365),
                     LIVE1_FULL[s]) if y < 4 else LIVE1_FULL[s]
            # year-y interval for shift s: [A_y+s, ...); y=4 ends at live1
            hi = (min(ANCH[y] + pd.Timedelta(hours=s) + pd.Timedelta(days=365),
                      LIVE1_FULL[s]))
            n_tc = sum(1 for t in tc if lo <= t < hi)
            m = (grid_s >= lo.value) & (grid_s < hi.value)
            counts[str(s)][str(y)] = int(n_tc)
            grid_sizes[str(s)][str(y)] = int(m.sum())
            print(f"shift{s} year{y}: k={n_tc} gridN={int(m.sum())}",
                  flush=True)

    out_counts = {
        "trigger_rule": "closes-only |r|>4*SIG(540,min120), tc=T+4h, union over 5 majors per shift (verbatim oc_cascadeboost)",
        "year_interval": "[A_y+s, min(A_y+s+365d, 2026-09-23+s))",
        "union_triggers_per_shift": union_totals,
        "k_per_shift_year": counts,
        "gridN_per_shift_year": grid_sizes,
        "n_seeds": N_SEEDS,
        "seed_scheme": f"{SEED_BASE} + j*100 + y*10 + s (j=0..{N_SEEDS - 1})",
        "window": "7d strictly-after (0 < T-ts <= 7d), starts drawn w/o replacement from year grid",
    }
    (HERE / "tmp").mkdir(exist_ok=True)
    (HERE / "tmp/ctrl_counts.json").write_text(json.dumps(out_counts, indent=1))

    # ---- frozen random starts ----
    starts: dict[tuple, list] = {}
    for s in SHIFTS:
        grid_s = np.array(sorted(
            pd.to_datetime(g[g["shift"] == s]["T"], utc=True).values.astype(
                "datetime64[ns]").astype(np.int64)), dtype=np.int64)
        for y in range(5):
            lo = ANCH[y] + pd.Timedelta(hours=s)
            hi = min(ANCH[y] + pd.Timedelta(hours=s) + pd.Timedelta(days=365),
                     LIVE1_FULL[s])
            pos = np.where((grid_s >= lo.value) & (grid_s < hi.value))[0]
            seg = grid_s[pos]
            k = counts[str(s)][str(y)]
            for j in range(N_SEEDS):
                rng = np.random.default_rng(seed_of(y, s, j))
                if k <= 0:
                    sel = np.empty(0, dtype=np.int64)
                elif k >= len(seg):
                    sel = seg.copy()
                else:
                    sel = np.sort(rng.choice(seg, size=k, replace=False))
                starts[(y, s, j)] = [int(v) for v in sel]
    with open(HERE / "tmp/ctrlR_starts.pkl", "wb") as f:
        pickle.dump({"starts": starts, "seed_base": SEED_BASE,
                     "n_seeds": N_SEEDS}, f)
    ntot = sum(len(v) for v in starts.values())
    print(f"wrote tmp/ctrl_counts.json + tmp/ctrlR_starts.pkl "
          f"keys={len(starts)} total_starts={ntot}", flush=True)


if __name__ == "__main__":
    main()
