"""V1 2021-2026 replica gate (CPU-only).

Reuses oc_k2placebo ledger read-only (reproduction gate n==22312, base sums ==
0.911273/0.832599/2.099814/3.197390/0.677229, sum5y == 7.718304 +- 0.002).
Joins per-fill rung 0..4 -> frozen V1 parity mults 4/(k+4) (sizing-only).
Per-year base/tilted/realised/norm/gain, dSum5y, sum-half. SECONDARY pass:
dSum5y >= +0.273 AND sum-half >= 4/5. Timing/block diagnostics (1000 perms,
seeds 20261009+y / 20261008+y) reported, never gating. Heartbeat 600 s.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
K2 = ROOT / "research/tournament/oc_k2placebo"

sys.path.insert(0, str(HERE))
from riskparity_rule import parity_mults_V1, phase_mean_sums  # noqa: E402

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
SEED_TIMING = 20261009
SEED_BLOCK = 20261008
N_PERM = 1000
BLOCK = 42
N_GATE = 22312
BASE_GATE = (0.911273, 0.832599, 2.099814, 3.197390, 0.677229)
SUM5Y_GATE = 7.718304
PHASES = (0, 1, 2, 3)
HB_S = 600


def main() -> None:
    t0 = time.time()
    last_hb = t0
    led = dict(np.load(K2 / "tmp/ledger.npz"))
    for k in ("phase", "coin", "year", "bar_time", "rung"):
        led[k] = led[k].astype(np.int64)
    for k in ("w", "y10"):
        led[k] = led[k].astype(np.float64)
    n = len(led["w"])
    print(f"loaded k2placebo ledger n={n}", flush=True)
    assert n == N_GATE, f"ledger size {n} != {N_GATE}"

    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    co = led["coin"].astype(int)
    ru = led["rung"].astype(int)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)
    assert set(np.unique(ru)) <= {0, 1, 2, 3, 4}

    base_y = phase_mean_sums(ph, yr, w, yv, 5)
    print(f"base sums={[round(v, 6) for v in base_y]} "
          f"sum5y={sum(base_y):.6f}", flush=True)
    for y in range(5):
        assert abs(base_y[y] - BASE_GATE[y]) <= 0.002, f"base y{y} fail"
    assert abs(sum(base_y) - SUM5Y_GATE) <= 0.002, "sum5y gate fail"

    mult_map = parity_mults_V1()
    mult = np.array([mult_map[int(r)] for r in ru], dtype=float)
    tilt_y = phase_mean_sums(ph, yr, w * mult, yv, 5)

    res = {
        "config": {
            "ledger": "oc_k2placebo/tmp/ledger.npz read-only (D0+B1 2021-2026)",
            "mult": "frozen V1 4/(k+4) per rung (sizing-only)",
            "seed_timing": SEED_TIMING, "seed_block": SEED_BLOCK,
            "n_perm": N_PERM, "block": BLOCK,
            "gate": "dSum5y >= +0.273 AND sum-half >= 4/5",
        },
        "reproduction": {"base_sums": [round(v, 6) for v in base_y],
                         "sum5y": round(float(sum(base_y)), 6),
                         "n_fills": int(n)},
    }
    years = []
    for y in range(5):
        m = yr == y
        rm = float(mult[m].mean())
        norm = float(tilt_y[y]) / rm
        years.append({"year": ANCH5[y], "n_fills": int(m.sum()),
                      "base": round(float(base_y[y]), 6),
                      "tilted": round(float(tilt_y[y]), 6),
                      "realised_mean": round(rm, 6),
                      "norm": round(norm, 6),
                      "gain": round(norm - float(base_y[y]), 6)})
        print(f"  {ANCH5[y]} base={base_y[y]:.6f} tilt={tilt_y[y]:.6f} "
              f"rm={rm:.6f} norm={norm:.6f} gain={norm - base_y[y]:+.6f}",
              flush=True)
    dsum = sum(r["gain"] for r in years)
    half = sum(1 for r in years if r["gain"] > 0)
    print(f"dSum5y={dsum:+.6f} sum-half={half}/5", flush=True)

    timing = []
    for y in range(5):
        rng = np.random.default_rng(SEED_TIMING + y)
        my = yr == y
        denom = float(mult[my].mean())
        actual = float(tilt_y[y]) / denom
        fw, fy, fp, m0 = w[my], yv[my], ph[my], mult[my]
        perms = np.empty(N_PERM)
        for k in range(N_PERM):
            fm = rng.permutation(m0)
            s_sum = sum(float((fw[fp == p] * fm[fp == p] * fy[fp == p]).sum())
                        for p in PHASES)
            perms[k] = (s_sum / 4.0) / denom
            if time.time() - last_hb > HB_S:
                print(f"[hb] timing y={y} perm {k}/{N_PERM}", flush=True)
                last_hb = time.time()
        pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
        timing.append({"year": ANCH5[y], "actual_norm": round(actual, 6),
                       "p5": round(float(np.quantile(perms, 0.05)), 6),
                       "p50": round(float(np.quantile(perms, 0.50)), 6),
                       "p95": round(float(np.quantile(perms, 0.95)), 6),
                       "percentile": round(float(pct), 2)})
        print(f"timing y={y} actual={actual:.6f} pct={pct:.2f}", flush=True)

    block = []
    for y in range(5):
        rng = np.random.default_rng(SEED_BLOCK + y)
        my = np.where(yr == y)[0]
        denom = float(mult[my].mean())
        actual = float(tilt_y[y]) / denom
        order = np.argsort(my, kind="stable")
        groups: dict = {}
        for t, j in enumerate(my[order]):
            groups.setdefault((int(co[j]), int(ph[j])), []).append(t)
        blks = []
        for members in groups.values():
            seq = [mult[my[order[t]]] for t in members]
            blks.append([seq[b:b + BLOCK] for b in range(0, len(seq), BLOCK)])
        fw = w[my][order]
        fy = yv[my][order]
        fp = ph[my][order]
        perms = np.empty(N_PERM)
        for k in range(N_PERM):
            fm = np.empty(len(my))
            for members, bl in zip(groups.values(), blks):
                order_b = rng.permutation(len(bl))
                seq = np.concatenate([bl[b] for b in order_b]) if bl else np.array([])
                for t, v in zip(members, seq):
                    fm[t] = v
            s_sum = sum(float((fw[fp == p] * fm[fp == p] * fy[fp == p]).sum())
                        for p in PHASES)
            perms[k] = (s_sum / 4.0) / denom
            if time.time() - last_hb > HB_S:
                print(f"[hb] block y={y} perm {k}/{N_PERM}", flush=True)
                last_hb = time.time()
        pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
        block.append({"year": ANCH5[y], "actual_norm": round(actual, 6),
                      "p5": round(float(np.quantile(perms, 0.05)), 6),
                      "p50": round(float(np.quantile(perms, 0.50)), 6),
                      "p95": round(float(np.quantile(perms, 0.95)), 6),
                      "percentile": round(float(pct), 2)})
        print(f"block y={y} actual={actual:.6f} pct={pct:.2f}", flush=True)

    res["V1"] = {"per_year": years, "dSum5y": round(dsum, 6),
                 "sum_half": int(half),
                 "secondary_pass": bool(dsum >= 0.273 and half >= 4),
                 "timing_placebo": timing, "block_placebo": block}
    (HERE / "tmp").mkdir(exist_ok=True)
    (HERE / "tmp/v1_2021.json").write_text(json.dumps(res, indent=1))
    print("wrote tmp/v1_2021.json", flush=True)


if __name__ == "__main__":
    main()
