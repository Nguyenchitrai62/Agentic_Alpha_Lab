"""V2-vs-base 2021-2026 scoring (CPU-only; needs tmp/ledger_v2_2021.npz).

REF base from oc_k2placebo ledger (gate re-checked). V2 tilted(y) = 4-phase means of
w2*y10_2; realised_mean_V2(y) = mean MULTS_V2 over V2 fills in y; norm/V2 gain as usual.
dSum5y + sum-half vs SECONDARY gate (+0.273 and 4/5). Timing/block diagnostics
(1000 perms, seeds 20261009+y / 20261008+y) — diagnostic only. V2 stop-group table
from recorded kinds (groups shallow {0}, mid {1}, deep {2,3}). Heartbeat 600 s.
Output: tmp/v2_2021.json.
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
from riskparity_rule import parity_mults_V2, phase_mean_sums  # noqa: E402

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
SEED_TIMING = 20261009
SEED_BLOCK = 20261008
N_PERM = 1000
BLOCK = 42
BASE_GATE = (0.911273, 0.832599, 2.099814, 3.197390, 0.677229)
SUM5Y_GATE = 7.718304
PHASES = (0, 1, 2, 3)
HB_S = 600
GROUPS_V2 = {"shallow": (0,), "mid": (1,), "deep": (2, 3)}


def main() -> None:
    t0 = time.time()
    last_hb = t0
    ref = dict(np.load(K2 / "tmp/ledger.npz"))
    for k in ("phase", "year"):
        ref[k] = ref[k].astype(np.int64)
    for k in ("w", "y10"):
        ref[k] = ref[k].astype(np.float64)
    base_y = phase_mean_sums(ref["phase"], ref["year"], ref["w"], ref["y10"], 5)
    for y in range(5):
        assert abs(base_y[y] - BASE_GATE[y]) <= 0.002, "REF base gate fail"
    assert abs(sum(base_y) - SUM5Y_GATE) <= 0.002, "REF sum5y gate fail"
    print(f"REF base ok sum5y={sum(base_y):.6f}", flush=True)

    led = dict(np.load(HERE / "tmp/ledger_v2_2021.npz"))
    for k in ("phase", "coin", "year", "bar_time", "rung", "kind"):
        led[k] = led[k].astype(np.int64)
    for k in ("w", "y10"):
        led[k] = led[k].astype(np.float64)
    n = len(led["w"])
    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    co = led["coin"].astype(int)
    ru = led["rung"].astype(int)
    w2 = led["w"].astype(float)
    yv = led["y10"].astype(float)
    kd = led["kind"].astype(int)
    assert set(np.unique(ru)) <= {0, 1, 2, 3}
    print(f"loaded V2 2021 ledger n={n}", flush=True)

    mmap = parity_mults_V2()
    mult = np.array([mmap[int(r)] for r in ru], dtype=float)
    tilt_y = phase_mean_sums(ph, yr, w2, yv, 5)

    res = {
        "config": {
            "ledger_v2": "tmp/ledger_v2_2021.npz (V2 grid/stops/sizes rebuild)",
            "gate": "dSum5y >= +0.273 AND sum-half >= 4/5",
            "seed_timing": SEED_TIMING, "seed_block": SEED_BLOCK,
            "n_perm": N_PERM, "block": BLOCK,
        },
        "n_fills_v2": int(n),
        "per_leg_v2": [int((yr == y).sum()) for y in range(5)],
    }
    years = []
    for y in range(5):
        m = yr == y
        rm = float(mult[m].mean()) if m.any() else 1.0
        norm = float(tilt_y[y]) / rm if rm else 0.0
        years.append({"year": ANCH5[y], "n_fills_v2": int(m.sum()),
                      "base": round(float(base_y[y]), 6),
                      "tilted_v2": round(float(tilt_y[y]), 6),
                      "realised_mean_v2": round(rm, 6),
                      "norm_v2": round(norm, 6),
                      "gain": round(norm - float(base_y[y]), 6)})
        print(f"  {ANCH5[y]} n2={m.sum()} base={base_y[y]:.6f} "
              f"tilt2={tilt_y[y]:.6f} rm2={rm:.6f} norm2={norm:.6f} "
              f"gain={norm - base_y[y]:+.6f}", flush=True)
    dsum = sum(r["gain"] for r in years)
    half = sum(1 for r in years if r["gain"] > 0)
    print(f"dSum5y={dsum:+.6f} sum-half={half}/5", flush=True)

    timing = []
    for y in range(5):
        rng = np.random.default_rng(SEED_TIMING + y)
        my = yr == y
        denom = float(mult[my].mean())
        actual = float(tilt_y[y]) / denom
        fw, fy, fp, m0 = w2[my], yv[my], ph[my], mult[my]
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
        fw = w2[my][order]
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

    stop = (kd == 2) | (kd == 0)
    tp = kd == 1
    stops = {"groups": {}, "per_year": []}
    for g, members in GROUPS_V2.items():
        gm = np.isin(ru, members)
        stops["groups"][g] = {
            "n": int(gm.sum()),
            "stop_rate": round(float(stop[gm].mean()), 4) if gm.any() else None,
            "tp_rate": round(float(tp[gm].mean()), 4) if gm.any() else None}
    for y in range(5):
        my = yr == y
        wsum = float(mult[my].sum())
        pstop = float((mult[my] * stop[my]).sum() / wsum) if wsum else float("nan")
        stops["per_year"].append({"year": ANCH5[y],
                                  "v2_stop_rate": round(float(stop[my].mean()), 4),
                                  "v2_tp_rate": round(float(tp[my].mean()), 4),
                                  "v2_parity_stop_rate": round(pstop, 4)})
    wsum_all = float(mult.sum())
    stops["pooled_parity_stop_rate"] = round(float((mult * stop).sum() / wsum_all), 4)
    stops["pooled_stop_rate"] = round(float(stop.mean()), 4)
    print(stops, flush=True)

    res["V2"] = {"per_year": years, "dSum5y": round(dsum, 6),
                 "sum_half": int(half),
                 "secondary_pass": bool(dsum >= 0.273 and half >= 4),
                 "timing_placebo": timing, "block_placebo": block,
                 "stops_v2": stops}
    (HERE / "tmp/v2_2021.json").write_text(json.dumps(res, indent=1))
    print("wrote tmp/v2_2021.json", flush=True)


if __name__ == "__main__":
    main()
