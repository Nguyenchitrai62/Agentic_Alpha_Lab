"""oc_b7thresh pre-sample replica surface: 12-cell boost grid on the clean 2017-2020 ledger.

Method inherited verbatim from oc_cboostpre/compute_boost_presample.py, parameterized over
k in {3.5,4.0,4.5} x W in {3,5,7,10} (mult 1.5 in window else 1.0, market-wide per shift).
Ledger REUSED read-only from oc_presampletilt/tmp (n == 9731, per-leg 909/2986/3115/2721).
Boosted stop rates via reused read-only oc_cboostpre/tmp/stop_kinds.npz (boost-independent
kinds; rates over known kinds only). CPU-only. Clean unseen-years leg. REPORT ONLY.
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
PST = ROOT / "research/tournament/oc_presampletilt"
CBP = ROOT / "research/tournament/oc_cboostpre"

sys.path.insert(0, str(HERE))
from thresh_rule import BOOST, CELLS  # noqa: E402

LEG_ORDER = ("Y2017", "Y2018", "Y2019", "Y2020p")
LEG_BOUNDS = {
    "Y2017": (pd.Timestamp("2017-10-16", tz="UTC"), pd.Timestamp("2018-01-01", tz="UTC")),
    "Y2018": (pd.Timestamp("2018-01-01", tz="UTC"), pd.Timestamp("2019-01-01", tz="UTC")),
    "Y2019": (pd.Timestamp("2019-01-01", tz="UTC"), pd.Timestamp("2020-01-01", tz="UTC")),
    "Y2020p": (pd.Timestamp("2020-01-01", tz="UTC"), pd.Timestamp("2020-09-01", tz="UTC")),
}
SEED_TIMING = 20261007
SEED_BLOCK = 20261008
N_PERM = 1000
BLOCK = 42
N_GATE = 9731
PER_LEG_GATE = (909, 2986, 3115, 2721)
BASE_GATE = (2.313362, 2.678870, 0.577643, 0.297538)
PHASES = (0, 1, 2, 3)
SHIFTS = (0, 1, 2, 3)
HB_S = 600
KIND_STOP = (0, 2)  # backstop=0, stop=2 in stop_kinds.npz


def phase_mean_sums(ph, yr, wv, yv, n_years=4):
    out = []
    for y in range(n_years):
        ss = []
        for p in PHASES:
            m = (ph == p) & (yr == y)
            ss.append(float((wv[m] * yv[m]).sum()) if m.any() else 0.0)
        out.append(float(np.mean(ss)))
    return out


def load_grid():
    d = pd.read_parquet(HERE / "boost_grid_pre.parquet")
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
    led = dict(np.load(PST / "tmp/ledger_presample.npz"))
    for k in ("phase", "coin", "year", "t_ord", "rung"):
        led[k] = led[k].astype(np.int64)
    for k in ("w", "y10"):
        led[k] = led[k].astype(np.float64)
    bt_all = np.load(PST / "tmp/bt_presample.npy", allow_pickle=True)
    n = len(led["w"])
    print(f"loaded presample ledger n={n}", flush=True)
    assert n == N_GATE, f"ledger size {n} != {N_GATE}"
    kinds = np.load(CBP / "tmp/stop_kinds.npz")["kind"].astype(int)
    assert len(kinds) == n, (len(kinds), n)
    known = kinds != -1
    is_stop = np.isin(kinds, list(KIND_STOP))

    exact, per_shift = load_grid()
    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)
    base_y = phase_mean_sums(ph, yr, w, yv)
    print(f"base sums={[round(v, 6) for v in base_y]}", flush=True)
    for y in range(4):
        assert abs(base_y[y] - BASE_GATE[y]) <= 1e-6

    res = {"config": {
        "ledger": "oc_presampletilt/tmp read-only (n=9731, clean unseen years)",
        "grid": "boost_grid_pre.parquet (k x W, 1.5 in (tc,tc+Wd], market-wide per shift)",
        "stop": "reused oc_cboostpre/tmp/stop_kinds.npz (verbatim mu=1.0 kinds; stop={stop,backstop}; rates over known only)",
        "seeds": [SEED_TIMING, SEED_BLOCK], "n_perm": N_PERM, "block": BLOCK},
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
        for y in range(4):
            m = yr == y
            rm = float(mult[m].mean()) if m.any() else 1.0
            norm = float(boost_y[y]) / rm if rm else 0.0
            my_known = m & known
            base_stop = float(is_stop[my_known].mean()) if my_known.any() else None
            mb = m & (mult == 1.5) & known
            b_stop = float(is_stop[mb].mean()) if mb.any() else None
            years.append({"year": LEG_ORDER[y], "n_fills": int(m.sum()),
                          "base": round(float(base_y[y]), 6),
                          "boosted": round(float(boost_y[y]), 6),
                          "realised_mean": round(rm, 6), "norm": round(norm, 6),
                          "gain": round(norm - float(base_y[y]), 6),
                          "boosted_share_fills": round(float((mult[m] == 1.5).mean()), 4),
                          "base_stop_rate": round(base_stop, 4) if base_stop is not None else None,
                          "boosted_stop_rate": round(b_stop, 4) if b_stop is not None else None,
                          "stop_delta": round(b_stop - base_stop, 4)
                          if (b_stop is not None and base_stop is not None) else None})
        print(f"  {cell}: gains={[r['gain'] for r in years]} "
              f"stop_d={[r['stop_delta'] for r in years]}", flush=True)

        uni = {}
        for y in range(4):
            lo, hi = LEG_BOUNDS[LEG_ORDER[y]]
            for s in SHIFTS:
                t_ns = per_shift[s]["t_ns"]
                col = per_shift[s][f"mult_{cell}"]
                m = (t_ns >= np.int64(lo.value)) & (t_ns < np.int64(hi.value))
                uni[(y, s)] = col[m].astype(float)
        pos_of = {}
        for (y, s) in uni:
            t_ns = per_shift[s]["t_ns"]
            lo, hi = LEG_BOUNDS[LEG_ORDER[y]]
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
        for y in range(4):
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
                    print(f"[hb] pre {cell} timing y={y} {kk}/{N_PERM} "
                          f"elapsed={time.time() - t0:.0f}s", flush=True)
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            timing.append({"year": LEG_ORDER[y], "actual_norm": round(actual, 6),
                           "percentile": round(float(pct), 2)})
            print(f"  timing {cell} y={y} pct={pct:.2f}", flush=True)
        block = []
        for y in range(4):
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
                    print(f"[hb] pre {cell} block y={y} {kk}/{N_PERM} "
                          f"elapsed={time.time() - t0:.0f}s", flush=True)
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            block.append({"year": LEG_ORDER[y], "actual_norm": round(actual, 6),
                          "percentile": round(float(pct), 2)})
            print(f"  block {cell} y={y} pct={pct:.2f}", flush=True)
        res["cells"][cell] = {"per_year": years, "timing": timing, "block": block}
    (HERE / "tmp").mkdir(exist_ok=True)
    (HERE / "tmp/replica_pre.json").write_text(json.dumps(res, indent=1))
    print("wrote tmp/replica_pre.json", flush=True)


if __name__ == "__main__":
    main()
