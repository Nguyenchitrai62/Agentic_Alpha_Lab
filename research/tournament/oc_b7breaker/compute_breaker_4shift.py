"""oc_b7breaker SECONDARY (contaminated): 2021-2026 replica + placebo for B7/V1/V2.

Method verbatim from oc_cascadeboost/compute_replica_gate.py, applied to the breaker
grids (breaker_mult_4shift.parquet): mult_B7 = 1.5 iff in B7 window else 1.0;
mult_V = 1.0 if breaker active else mult_B7. V1 K=2/M=14; V2 K=3/M=21.
Ledger REUSED read-only from oc_k2placebo/tmp (ledger.npz + bt_all.npy;
reproduction gate: n == 22312 and base 4-phase-mean sum5y == 7.718304 +- 0.002;
B7 dSum5y reproduced == +2.946xxx).
Gate (same as cascadeboost, CONTAMINATED — reported only): sum-half (>=4/5y) PLUS
dSum5y >= +0.273. Also report delta vs B7 per dev year + dSum2021-2024 vs B7
("without losing the 2021-2024 gains"). CPU-only. Runs AFTER the primary outcome
is logged; no outcome feeds any choice.
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
from breaker_rule import BOOST, V1_K, V1_M, V2_K, V2_M  # noqa: E402

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
ANCH = [pd.Timestamp(a, tz="UTC") for a in ANCH5]
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
SEED_TIMING = 20261007
SEED_BLOCK = 20261008
N_PERM = 1000
BLOCK = 42
BASE_GATE = 7.718304
N_GATE = 22312
DSUM_GATE = 0.273
PHASES = (0, 1, 2, 3)
SHIFTS = (0, 1, 2, 3)
VARIANTS = ("B7", "V1", "V2")
MULT_COL = {"B7": "mult_B7", "V1": "mult_V1", "V2": "mult_V2"}


def phase_mean_sums(ph, yr, wv, yv):
    out = []
    for y in range(5):
        ss = []
        for p in PHASES:
            m = (ph == p) & (yr == y)
            ss.append(float((wv[m] * yv[m]).sum()) if m.any() else 0.0)
        out.append(float(np.mean(ss)))
    return out


def load_mult():
    d = pd.read_parquet(HERE / "breaker_mult_4shift.parquet")
    d["T"] = pd.to_datetime(d["T"], utc=True)
    exact = {}
    per_shift = {}
    for s in SHIFTS:
        sub = d[d["shift"] == s].sort_values("T")
        t_ns = sub["T"].values.astype("datetime64[ns]").astype(np.int64)
        per_shift[s] = {c: sub[c].to_numpy(dtype=float) for c in
                        ("mult_B7", "mult_V1", "mult_V2")}
        per_shift[s]["t_ns"] = t_ns
        per_shift[s]["T"] = pd.to_datetime(sub["T"], utc=True).tolist()
        for t, a, v1, v2 in zip(per_shift[s]["T"], per_shift[s]["mult_B7"],
                               per_shift[s]["mult_V1"], per_shift[s]["mult_V2"]):
            exact[(int(s), pd.Timestamp(t))] = (float(a), float(v1), float(v2))
    return exact, per_shift


def mult_at(shift, t, variant, exact, per_shift):
    key = (int(shift), pd.Timestamp(t))
    hit = exact.get(key)
    if hit is not None:
        return {"B7": hit[0], "V1": hit[1], "V2": hit[2]}[variant]
    col = MULT_COL[variant]
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
    assert BOOST == 1.5 and (V1_K, V1_M) == (2, 14) and (V2_K, V2_M) == (3, 21)
    led = dict(np.load(K2P / "tmp/ledger.npz"))
    for k in ("phase", "coin", "year", "bar_time", "rung"):
        led[k] = led[k].astype(np.int64)
    for k in ("w", "y10"):
        led[k] = led[k].astype(np.float64)
    bt_all = np.load(K2P / "tmp/bt_all.npy", allow_pickle=True)
    n = len(led["w"])
    print(f"loaded ledger n={n}", flush=True)
    assert n == N_GATE, f"ledger size {n} != {N_GATE}"

    exact, per_shift = load_mult()

    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)

    base_y = phase_mean_sums(ph, yr, w, yv)
    got5 = float(sum(base_y))
    print(f"base 4-phase-mean sums={[round(v, 6) for v in base_y]} sum5y={got5:.6f}",
          flush=True)
    assert abs(got5 - BASE_GATE) <= 0.002, f"base {got5} != {BASE_GATE}"

    res = {
        "config": {
            "ledger": "oc_k2placebo/tmp/ledger.npz + bt_all.npy read-only",
            "grids": "breaker_mult_4shift.parquet (B7 1.5 in (tc,tc+7d]; V1/V2 1.0 if breaker else B7)",
            "gate": "sum-half (>=4/5y) PLUS dSum5y>=+0.273 (CONTAMINATED — reported only, not clean evidence)",
            "contamination": "idea formed after seeing cascade years incl. post-release year; this replica is a labelled diagnostic",
        },
        "reproduction": {"base_sums": [round(v, 6) for v in base_y],
                         "base_sum5y": round(got5, 6), "n_fills": int(n)},
    }
    boost_ys = {}
    for variant in VARIANTS:
        mult = np.array([mult_at(int(ph[i]), bt_all[i], variant, exact, per_shift)
                         for i in range(n)], dtype=float)
        vals = sorted(set(np.round(mult, 6)))
        assert set(vals) <= {1.0, 1.5}, vals
        print(f"{variant}: boosted_share={float((mult == 1.5).mean()):.4f} values={vals}",
              flush=True)
        boost_y = phase_mean_sums(ph, yr, w * mult, yv)
        boost_ys[variant] = (mult, boost_y)
        dsum = float(sum(boost_y) - sum(base_y))
        sum_ge = sum(1 for y in range(5) if boost_y[y] >= base_y[y] - 1e-12)
        years = []
        for y in range(5):
            m = yr == y
            rm = float(mult[m].mean()) if m.any() else 1.0
            years.append({"year": ANCH[y].date().isoformat(),
                          "n_fills": int(m.sum()),
                          "base": round(float(base_y[y]), 6),
                          "variant": round(float(boost_y[y]), 6),
                          "realised_mean": round(rm, 6),
                          "norm": round(float(boost_y[y]) / rm, 6) if rm else 0.0,
                          "boosted_share_fills": round(float((mult[m] == 1.5).mean()), 4)
                          if m.any() else None})
            print(f"  {years[-1]['year']} base={years[-1]['base']} var={years[-1]['variant']} "
                  f"rm={years[-1]['realised_mean']} norm={years[-1]['norm']}", flush=True)
        print(f"{variant}: dSum5y={dsum:.6f} sum_half={sum_ge}/5", flush=True)

        uni = {}
        for y in range(5):
            lo = ANCH[y]
            hi = ANCH[y + 1] if y < 4 else YEAR_END
            for s in SHIFTS:
                t_ns = per_shift[s]["t_ns"]
                col = per_shift[s][MULT_COL[variant]]
                lo_ns, hi_ns = np.int64(lo.value), np.int64(hi.value)
                m = (t_ns >= lo_ns) & (t_ns < hi_ns)
                uni[(y, s)] = col[m].astype(float)
        pos_of = {}
        for (y, s), arr in uni.items():
            t_ns = per_shift[s]["t_ns"]
            lo = ANCH[y]
            hi = ANCH[y + 1] if y < 4 else YEAR_END
            m = (t_ns >= np.int64(lo.value)) & (t_ns < np.int64(hi.value))
            idx = {int(tt): j for j, tt in enumerate(t_ns[m])}
            pos_of[(y, s)] = idx
        fill_pos = np.full(n, -1, dtype=np.int64)
        for i in range(n):
            q = pd.Timestamp(bt_all[i])
            if q.tzinfo is None:
                q = q.tz_localize("UTC")
            fill_pos[i] = pos_of[(int(yr[i]), int(ph[i]))].get(int(q.value), -1)
        assert (fill_pos >= 0).all()

        for tag, seed, blk in (("timing", SEED_TIMING, False), ("block", SEED_BLOCK, True)):
            store = []
            for y in range(5):
                rng = np.random.default_rng(seed + y)
                my = (yr == y)
                fm_actual = mult[my]
                actual = float(boost_y[y]) / float(fm_actual.mean())
                fill_w = w[my]
                fill_y = yv[my]
                fill_ph = ph[my]
                fill_p = fill_pos[my]
                denom_y = float(fm_actual.mean())
                if not blk:
                    slices = {}
                    for s in SHIFTS:
                        sm = fill_ph == s
                        slices[s] = (np.where(sm)[0], uni[(y, s)])
                else:
                    blk_of = {}
                    for s in SHIFTS:
                        arr = uni[(y, s)]
                        blk_of[s] = [arr[bb:bb + BLOCK] for bb in range(0, len(arr), BLOCK)]
                perms = np.empty(N_PERM)
                last_hb = time.time()
                for k in range(N_PERM):
                    fm = np.empty(my.sum())
                    for s in SHIFTS:
                        loc = np.where(fill_ph == s)[0]
                        if not blk:
                            _loc, arr = slices[s]
                            pm = rng.permutation(arr)
                            fm[loc] = pm[fill_p[loc]]
                        else:
                            blks = blk_of[s]
                            order = rng.permutation(len(blks))
                            seq = np.concatenate([blks[bb] for bb in order]) if blks else np.array([])
                            fm[loc] = seq[fill_p[loc]]
                    s_sum = 0.0
                    for p in PHASES:
                        mp = fill_ph == p
                        s_sum += float((fill_w[mp] * fm[mp] * fill_y[mp]).sum())
                    perms[k] = (s_sum / 4.0) / denom_y
                    if time.time() - last_hb > 600:
                        print(f"[{tag} hb] {variant} y={y} perm {k}/{N_PERM}", flush=True)
                        last_hb = time.time()
                pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
                store.append({"year": ANCH[y].date().isoformat(),
                              "actual_norm": round(actual, 6),
                              "percentile": round(float(pct), 2)})
                print(f"{tag} {variant} y={y} pct={pct:.2f}", flush=True)
            res.setdefault(variant, {})[tag + "_placebo"] = store
        res[variant] = {**res.get(variant, {}), "per_year": years,
                        "dSum5y": round(float(sum(boost_y) - sum(base_y)), 6),
                        "sum_half_years_ge": int(sum(1 for y in range(5)
                                                     if boost_y[y] >= base_y[y] - 1e-12)),
                        "gate_pass": bool(sum(1 for y in range(5)
                                              if boost_y[y] >= base_y[y] - 1e-12) >= 4
                                          and float(sum(boost_y) - sum(base_y)) >= DSUM_GATE)}

    # delta vs B7 (dev4 + full)
    for variant in ("V1", "V2"):
        d_all = [res[variant]["per_year"][y]["norm"] - res["B7"]["per_year"][y]["norm"]
                 for y in range(5)]
        res[variant]["delta_vs_B7_per_year"] = [round(float(v), 6) for v in d_all]
        res[variant]["dSum_dev4_vs_B7"] = round(
            float(sum(res[variant]["per_year"][y]["variant"] for y in range(4))
                  - sum(res["B7"]["per_year"][y]["variant"] for y in range(4))), 6)
    (HERE / "tmp").mkdir(exist_ok=True)
    (HERE / "tmp/breaker_4shift.json").write_text(json.dumps(res, indent=1))
    print("wrote tmp/breaker_4shift.json", flush=True)


if __name__ == "__main__":
    main()
