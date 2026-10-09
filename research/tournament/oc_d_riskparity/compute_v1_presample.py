"""V1 pre-sample replica + diagnostic placebos (CPU-only).

Reuses oc_presampletilt ledger read-only (reproduction gate n==9731,
per-leg 909/2986/3115/2721, base sums == 2.313362/2.678870/0.577643/0.297538).
Joins per-fill rung index 0..4 -> frozen V1 parity mults 4/(k+4) (sizing-only;
outcomes y10 unchanged). Per-year 4-phase-mean base/tilted/realised/norm/gain.
Placebos are DIAGNOSTIC (parity is not a timing rule): timing = uniform per-fill
mult permutation within year (seed 20261009+y); block = chronological 42-fill
blocks per (coin, phase) within year (seed 20261008+y). 1000 perms each.
Percentile = 100*(1+#{perm<=actual})/1001, signif iff >=95. Heartbeat 600 s.
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
from riskparity_rule import parity_mults_V1, phase_mean_sums  # noqa: E402

LEG_ORDER = ("Y2017", "Y2018", "Y2019", "Y2020p")
SEED_TIMING = 20261009
SEED_BLOCK = 20261008
N_PERM = 1000
BLOCK = 42
N_GATE = 9731
PER_LEG_GATE = (909, 2986, 3115, 2721)
BASE_GATE = (2.313362, 2.678870, 0.577643, 0.297538)
PHASES = (0, 1, 2, 3)
HB_S = 600


def main() -> None:
    t0 = time.time()
    last_hb = t0
    led = dict(np.load(PST / "tmp/ledger_presample.npz"))
    for k in ("phase", "coin", "year", "t_ord", "rung"):
        led[k] = led[k].astype(np.int64)
    for k in ("w", "y10"):
        led[k] = led[k].astype(np.float64)
    n = len(led["w"])
    print(f"loaded presample ledger n={n}", flush=True)
    assert n == N_GATE, f"ledger size {n} != {N_GATE}"
    for y, g in enumerate(PER_LEG_GATE):
        got = int((led["year"] == y).sum())
        assert got == g, f"leg {LEG_ORDER[y]} n {got} != {g}"

    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    co = led["coin"].astype(int)
    ru = led["rung"].astype(int)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)
    assert set(np.unique(ru)) <= {0, 1, 2, 3, 4}

    base_y = phase_mean_sums(ph, yr, w, yv, 4)
    print(f"base 4-phase-mean sums={[round(v, 6) for v in base_y]}", flush=True)
    for y in range(4):
        assert abs(base_y[y] - BASE_GATE[y]) <= 1e-6, f"base {LEG_ORDER[y]} fail"

    mult_map = parity_mults_V1()
    mult = np.array([mult_map[int(r)] for r in ru], dtype=float)
    print("V1 mults by rung: " + ", ".join(
        f"r{i}={mult_map[i]:.6f}" for i in range(5)), flush=True)
    tilt_y = phase_mean_sums(ph, yr, w * mult, yv, 4)

    res = {
        "config": {
            "ledger": "oc_presampletilt/tmp/ledger_presample.npz read-only (D0+B1, SPOT)",
            "mult": "frozen V1 4/(k+4) per rung {2.5,3,3.5,4,5} (sizing-only; outcomes unchanged)",
            "seed_timing": SEED_TIMING, "seed_block": SEED_BLOCK,
            "n_perm": N_PERM, "block": BLOCK,
            "rule": "norm(y)=tilted(y)/realised_mean(y); gain=norm-base; perm norms use ACTUAL denominator",
            "percentile": "100*(1+#{perm<=actual})/1001; signif iff >=95 (diagnostic: not a timing rule)",
        },
        "reproduction": {"per_leg_gate": list(PER_LEG_GATE),
                         "base_sums": [round(v, 6) for v in base_y],
                         "n_fills": int(n)},
    }
    years = []
    for y in range(4):
        m = yr == y
        rm = float(mult[m].mean())
        norm = float(tilt_y[y]) / rm
        rung_share = {f"rung{i}": round(float(((ru[m] == i)).mean()), 4)
                      for i in range(5)}
        years.append({"year": LEG_ORDER[y], "n_fills": int(m.sum()),
                      "base": round(float(base_y[y]), 6),
                      "tilted": round(float(tilt_y[y]), 6),
                      "realised_mean": round(rm, 6),
                      "norm": round(norm, 6),
                      "gain": round(norm - float(base_y[y]), 6),
                      "rung_share": rung_share})
        print(f"  {LEG_ORDER[y]} base={base_y[y]:.6f} tilt={tilt_y[y]:.6f} "
              f"rm={rm:.6f} norm={norm:.6f} gain={norm - base_y[y]:+.6f}",
              flush=True)

    # ---- timing diagnostic: uniform per-fill mult permutation within year ----
    timing = []
    for y in range(4):
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
        timing.append({"year": LEG_ORDER[y], "actual_norm": round(actual, 6),
                       "p5": round(float(np.quantile(perms, 0.05)), 6),
                       "p50": round(float(np.quantile(perms, 0.50)), 6),
                       "p95": round(float(np.quantile(perms, 0.95)), 6),
                       "percentile": round(float(pct), 2)})
        print(f"timing y={y} actual={actual:.6f} pct={pct:.2f}", flush=True)

    # ---- block diagnostic: chronological 42-fill blocks per (coin, phase) ----
    block = []
    for y in range(4):
        rng = np.random.default_rng(SEED_BLOCK + y)
        my = np.where(yr == y)[0]
        denom = float(mult[my].mean())
        actual = float(tilt_y[y]) / denom
        order = np.argsort(my, kind="stable")  # ledger order ~ chronological
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
        block.append({"year": LEG_ORDER[y], "actual_norm": round(actual, 6),
                      "p5": round(float(np.quantile(perms, 0.05)), 6),
                      "p50": round(float(np.quantile(perms, 0.50)), 6),
                      "p95": round(float(np.quantile(perms, 0.95)), 6),
                      "percentile": round(float(pct), 2)})
        print(f"block y={y} actual={actual:.6f} pct={pct:.2f}", flush=True)

    res["V1"] = {"per_year": years, "timing_placebo": timing,
                 "block_placebo": block}
    (HERE / "tmp").mkdir(exist_ok=True)
    (HERE / "tmp/v1_presample.json").write_text(json.dumps(res, indent=1))
    print("wrote tmp/v1_presample.json", flush=True)


if __name__ == "__main__":
    main()
