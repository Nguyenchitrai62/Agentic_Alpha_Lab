"""oc_b7thresh main replica surface: 12-cell boost grid on the reused 2021-2026 ledger.

Method verbatim from oc_cascadeboost/compute_replica_gate.py, parameterized over
k in {3.5,4.0,4.5} x W in {3,5,7,10} (mult 1.5 in window else 1.0, market-wide per shift).
Ledger REUSED read-only from oc_k2placebo/tmp (n == 22312, base sum5y == 7.718304 +- 0.002).
Per cell-year: base/boosted/realised_mean/norm/gain + 1000-perm timing/block placebo
(time-bar within-(year,shift), seeds 20261007+y / 20261008+y). CPU-only. CONTAMINATED LABEL:
idea formed after seeing the delay replica incl. post-release year; 2025 column is a labelled
diagnostic, never a selection input. REPORT ONLY, no gate, no selection.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
K2P = ROOT / "research/tournament/oc_k2placebo"

sys.path.insert(0, str(HERE))
from thresh_rule import BOOST, CELLS, cell_of  # noqa: E402

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
ANCH = [pd.Timestamp(a, tz="UTC") for a in ANCH5]
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
SEED_TIMING = 20261007
SEED_BLOCK = 20261008
N_PERM = 1000
BLOCK = 42
BASE_GATE = 7.718304
N_GATE = 22312
PHASES = (0, 1, 2, 3)
SHIFTS = (0, 1, 2, 3)
HB_S = 600


def phase_mean_sums(ph, yr, wv, yv):
    out = []
    for y in range(5):
        ss = []
        for p in PHASES:
            m = (ph == p) & (yr == y)
            ss.append(float((wv[m] * yv[m]).sum()) if m.any() else 0.0)
        out.append(float(np.mean(ss)))
    return out


def load_grid():
    d = pd.read_parquet(HERE / "boost_grid_main.parquet")
    d["T"] = pd.to_datetime(d["T"], utc=True)
    exact = {}
    per_shift = {}
    for s in SHIFTS:
        sub = d[d["shift"] == s].sort_values("T")
        t_ns = sub["T"].values.astype("datetime64[ns]").astype(np.int64)
        per_shift[s] = {f"mult_{c}": sub[f"mult_{c}"].to_numpy(dtype=float) for c in CELLS}
        per_shift[s]["t_ns"] = t_ns
        per_shift[s]["T"] = pd.to_datetime(sub["T"], utc=True).tolist()
        for t, row in zip(per_shift[s]["T"], sub[[f"mult_{c}" for c in CELLS]].itertuples(index=False)):
            exact[(int(s), pd.Timestamp(t))] = tuple(float(v) for v in row)
    return exact, per_shift


def mult_at(shift, t, ci, exact, per_shift):
    key = (int(shift), pd.Timestamp(t))
    hit = exact.get(key)
    if hit is not None:
        return hit[ci]
    col = f"mult_{CELLS[ci]}"
    t_ns = per_shift[int(shift)]["t_ns"]
    q = pd.Timestamp(t)
    if q.tzinfo is None:
        q = q.tz_localize("UTC")
    pos = int(np.searchsorted(t_ns, np.int64(q.value), side="right")) - 1
    if pos < 0:
        return 1.0
    return float(per_shift[int(shift)][col][pos])


def main() -> None:
    t0 = time.time()
    last_hb = t0
    assert BOOST == 1.5
    led = dict(np.load(K2P / "tmp/ledger.npz"))
    for k in ("phase", "coin", "year", "bar_time", "rung"):
        led[k] = led[k].astype(np.int64)
    for k in ("w", "y10"):
        led[k] = led[k].astype(np.float64)
    bt_all = np.load(K2P / "tmp/bt_all.npy", allow_pickle=True)
    n = len(led["w"])
    print(f"loaded ledger n={n}", flush=True)
    assert n == N_GATE, f"ledger size {n} != {N_GATE}"

    exact, per_shift = load_grid()
    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)
    base_y = phase_mean_sums(ph, yr, w, yv)
    got5 = float(sum(base_y))
    print(f"base sums={[round(v, 6) for v in base_y]} sum5y={got5:.6f}", flush=True)
    assert abs(got5 - BASE_GATE) <= 0.002, f"base {got5} != {BASE_GATE}"

    # time-bar universes are per (cell, y, s)
    res = {"config": {
        "ledger": "oc_k2placebo/tmp read-only (n=22312, base 7.718304)",
        "grid": "boost_grid_main.parquet (k x W, 1.5 in (tc,tc+Wd], market-wide per shift)",
        "seeds": [SEED_TIMING, SEED_BLOCK], "n_perm": N_PERM, "block": BLOCK,
        "contamination": "CONTAMINATED: idea formed after seeing delay replica incl. "
                         "post-release year; 2025 column is a LABELLED DIAGNOSTIC; no selection"},
        "reproduction": {"base_sums": [round(v, 6) for v in base_y], "n_fills": int(n)},
        "cells": {}}
    for ci, cell in enumerate(CELLS):
        print(f"[{ci + 1}/{len(CELLS)}] cell {cell} joining...", flush=True)
        mult = np.array([mult_at(int(ph[i]), bt_all[i], ci, exact, per_shift)
                         for i in range(n)], dtype=float)
        vals = sorted(set(np.round(mult, 6)))
        assert set(vals) <= {1.0, 1.5}, vals
        boost_y = phase_mean_sums(ph, yr, w * mult, yv)
        years = []
        for y in range(5):
            m = yr == y
            rm = float(mult[m].mean()) if m.any() else 1.0
            norm = float(boost_y[y]) / rm if rm else 0.0
            years.append({"year": y, "n_fills": int(m.sum()),
                          "base": round(float(base_y[y]), 6),
                          "boosted": round(float(boost_y[y]), 6),
                          "realised_mean": round(rm, 6), "norm": round(norm, 6),
                          "gain": round(norm - float(base_y[y]), 6),
                          "boosted_share_fills": round(float((mult[m] == 1.5).mean()), 4)})
        dsum = float(sum(boost_y) - sum(base_y))
        print(f"  {cell}: dSum5y={dsum:.6f} gains={[r['gain'] for r in years]}", flush=True)

        uni = {}
        for y in range(5):
            lo = ANCH[y]
            hi = ANCH[y + 1] if y < 4 else YEAR_END
            for s in SHIFTS:
                t_ns = per_shift[s]["t_ns"]
                col = per_shift[s][f"mult_{cell}"]
                m = (t_ns >= np.int64(lo.value)) & (t_ns < np.int64(hi.value))
                uni[(y, s)] = col[m].astype(float)
        pos_of = {}
        for (y, s) in uni:
            t_ns = per_shift[s]["t_ns"]
            lo = ANCH[y]
            hi = ANCH[y + 1] if y < 4 else YEAR_END
            m = (t_ns >= np.int64(lo.value)) & (t_ns < np.int64(hi.value))
            pos_of[(y, s)] = {int(tt): j for j, tt in enumerate(t_ns[m])}
        fill_pos = np.full(n, -1, dtype=np.int64)
        for i in range(n):
            q = pd.Timestamp(bt_all[i])
            if q.tzinfo is None:
                q = q.tz_localize("UTC")
            fill_pos[i] = pos_of[(int(yr[i]), int(ph[i]))].get(int(q.value), -1)
        assert (fill_pos >= 0).all()

        timing = []
        for y in range(5):
            rng = np.random.default_rng(SEED_TIMING + y)
            my = (yr == y)
            actual = float(boost_y[y]) / float(mult[my].mean())
            fill_w, fill_y, fill_ph, fill_p = w[my], yv[my], ph[my], fill_pos[my]
            slices = {s: (np.where(fill_ph == s)[0], uni[(y, s)]) for s in SHIFTS}
            denom = float(mult[my].mean())
            perms = np.empty(N_PERM)
            for kk in range(N_PERM):
                fm = np.empty(my.sum())
                for s in SHIFTS:
                    loc, arr = slices[s]
                    pm = rng.permutation(arr)
                    fm[loc] = pm[fill_p[loc]]
                s_sum = sum(float((fill_w[fill_ph == p] * fm[fill_ph == p] *
                                   fill_y[fill_ph == p]).sum()) for p in PHASES)
                perms[kk] = (s_sum / 4.0) / denom
                if time.time() - last_hb > HB_S:
                    last_hb = time.time()
                    print(f"[hb] main {cell} timing y={y} {kk}/{N_PERM} "
                          f"elapsed={time.time() - t0:.0f}s", flush=True)
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            timing.append({"year": y, "actual_norm": round(actual, 6),
                           "percentile": round(float(pct), 2)})
            print(f"  timing {cell} y={y} pct={pct:.2f}", flush=True)
        block = []
        for y in range(5):
            rng = np.random.default_rng(SEED_BLOCK + y)
            my = (yr == y)
            actual = float(boost_y[y]) / float(mult[my].mean())
            fill_w, fill_y, fill_ph, fill_p = w[my], yv[my], ph[my], fill_pos[my]
            denom = float(mult[my].mean())
            blk_of = {s: [uni[(y, s)][b:b + BLOCK] for b in range(0, len(uni[(y, s)]), BLOCK)]
                      for s in SHIFTS}
            perms = np.empty(N_PERM)
            for kk in range(N_PERM):
                fm = np.empty(my.sum())
                for s in SHIFTS:
                    loc = np.where(fill_ph == s)[0]
                    blks = blk_of[s]
                    seq = np.concatenate([blks[b] for b in rng.permutation(len(blks))])
                    fm[loc] = seq[fill_p[loc]]
                s_sum = sum(float((fill_w[fill_ph == p] * fm[fill_ph == p] *
                                   fill_y[fill_ph == p]).sum()) for p in PHASES)
                perms[kk] = (s_sum / 4.0) / denom
                if time.time() - last_hb > HB_S:
                    last_hb = time.time()
                    print(f"[hb] main {cell} block y={y} {kk}/{N_PERM} "
                          f"elapsed={time.time() - t0:.0f}s", flush=True)
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            block.append({"year": y, "actual_norm": round(actual, 6),
                          "percentile": round(float(pct), 2)})
            print(f"  block {cell} y={y} pct={pct:.2f}", flush=True)
        res["cells"][cell] = {"per_year": years, "timing": timing, "block": block,
                              "dSum5y": round(dsum, 6)}
    (HERE / "tmp").mkdir(exist_ok=True)
    (HERE / "tmp/replica_main.json").write_text(json.dumps(res, indent=1))
    print("wrote tmp/replica_main.json", flush=True)


if __name__ == "__main__":
    main()
