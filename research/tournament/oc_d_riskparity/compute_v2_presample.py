"""V2-vs-base pre-sample scoring (CPU-only; needs tmp/ledger_v2_presample.npz).

REF base from oc_presampletilt ledger (gate re-checked). V2 tilted(y) = 4-phase means
of w2*y10_2 (parity mults built into w2); realised_mean_V2(y) = mean MULTS_V2 over V2
fills in y; norm = tilted/realised_mean; gain = norm - base(y). Timing/block
diagnostics (1000 perms, seeds 20261009+y / 20261008+y) on V2 per-fill mults —
diagnostic only (not a timing rule). V2 stop-group table from kinds recorded in the
rebuild (groups shallow {0}, mid {1}, deep {2,3}; pooled parity-weighted vs REF base
merged in the final analyze step from stop_v1_presample.json). Heartbeat 600 s.
Output: tmp/v2_presample.json.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PST = ROOT / "research/tournament/oc_presampletilt"

sys.path.insert(0, str(HERE))
from riskparity_rule import parity_mults_V2, phase_mean_sums  # noqa: E402

LEG_ORDER = ("Y2017", "Y2018", "Y2019", "Y2020p")
SEED_TIMING = 20261009
SEED_BLOCK = 20261008
N_PERM = 1000
BLOCK = 42
BASE_GATE = (2.313362, 2.678870, 0.577643, 0.297538)
PHASES = (0, 1, 2, 3)
HB_S = 600
KIND_NAMES = {0: "backstop", 1: "tp", 2: "stop", 3: "time"}
GROUPS_V2 = {"shallow": (0,), "mid": (1,), "deep": (2, 3)}


def main() -> None:
    t0 = time.time()
    last_hb = t0
    ref = dict(np.load(PST / "tmp/ledger_presample.npz"))
    for k in ("phase", "year"):
        ref[k] = ref[k].astype(np.int64)
    for k in ("w", "y10"):
        ref[k] = ref[k].astype(np.float64)
    base_y = phase_mean_sums(ref["phase"], ref["year"], ref["w"], ref["y10"], 4)
    for y in range(4):
        assert abs(base_y[y] - BASE_GATE[y]) <= 1e-6, "REF base gate fail"
    print(f"REF base ok {[round(v, 6) for v in base_y]}", flush=True)

    led = dict(np.load(HERE / "tmp/ledger_v2_presample.npz"))
    for k in ("phase", "coin", "year", "t_ord", "rung", "kind"):
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
    print(f"loaded V2 ledger n={n}", flush=True)

    mmap = parity_mults_V2()
    mult = np.array([mmap[int(r)] for r in ru], dtype=float)
    tilt_y = phase_mean_sums(ph, yr, w2, yv, 4)

    res = {
        "config": {
            "ledger_v2": "tmp/ledger_v2_presample.npz (V2 grid/stops/sizes rebuild)",
            "mult": "frozen V2 4/(k'+s') (built into w2; realised mean = rung-composition mean)",
            "seed_timing": SEED_TIMING, "seed_block": SEED_BLOCK,
            "n_perm": N_PERM, "block": BLOCK,
        },
        "n_fills_v2": int(n),
        "per_leg_v2": [int((yr == y).sum()) for y in range(4)],
    }
    years = []
    for y in range(4):
        m = yr == y
        rm = float(mult[m].mean()) if m.any() else 1.0
        norm = float(tilt_y[y]) / rm if rm else 0.0
        years.append({"year": LEG_ORDER[y], "n_fills_v2": int(m.sum()),
                      "base": round(float(base_y[y]), 6),
                      "tilted_v2": round(float(tilt_y[y]), 6),
                      "realised_mean_v2": round(rm, 6),
                      "norm_v2": round(norm, 6),
                      "gain": round(norm - float(base_y[y]), 6)})
        print(f"  {LEG_ORDER[y]} n2={m.sum()} base={base_y[y]:.6f} "
              f"tilt2={tilt_y[y]:.6f} rm2={rm:.6f} norm2={norm:.6f} "
              f"gain={norm - base_y[y]:+.6f}", flush=True)

    timing = []
    for y in range(4):
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
        timing.append({"year": LEG_ORDER[y], "actual_norm": round(actual, 6),
                       "p5": round(float(np.quantile(perms, 0.05)), 6),
                       "p50": round(float(np.quantile(perms, 0.50)), 6),
                       "p95": round(float(np.quantile(perms, 0.95)), 6),
                       "percentile": round(float(pct), 2)})
        print(f"timing y={y} actual={actual:.6f} pct={pct:.2f}", flush=True)

    block = []
    for y in range(4):
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
        block.append({"year": LEG_ORDER[y], "actual_norm": round(actual, 6),
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
    for y in range(4):
        my = yr == y
        wsum = float(mult[my].sum())
        pstop = float((mult[my] * stop[my]).sum() / wsum) if wsum else float("nan")
        stops["per_year"].append({"year": LEG_ORDER[y],
                                  "v2_stop_rate": round(float(stop[my].mean()), 4),
                                  "v2_tp_rate": round(float(tp[my].mean()), 4),
                                  "v2_parity_stop_rate": round(pstop, 4)})
    wsum_all = float(mult.sum())
    stops["pooled_parity_stop_rate"] = round(float((mult * stop).sum() / wsum_all), 4)
    stops["pooled_stop_rate"] = round(float(stop.mean()), 4)
    print(stops, flush=True)

    res["V2"] = {"per_year": years, "timing_placebo": timing,
                 "block_placebo": block, "stops_v2": stops}
    (HERE / "tmp/v2_presample.json").write_text(json.dumps(res, indent=1))
    print("wrote tmp/v2_presample.json", flush=True)


if __name__ == "__main__":
    main()
