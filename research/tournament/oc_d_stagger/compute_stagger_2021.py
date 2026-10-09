"""oc_d_stagger: CPU-only 2021-2026 scoring + secondary gate.

- REF reproduction gate (read-only k2placebo ledger): n==22312, base 4-phase-mean
  sums == (0.911273, 0.832599, 2.099814, 3.197390, 0.677229), sum5y 7.718304 +-0.002.
- Per year: base(y), stag(y), gain, exposure ratio, fill split; dSum5y + sum-half.
  SECONDARY pass: dSum5y >= +0.273 AND sum-half >= 4/5.
- B-half timing/block placebos per year (seeds 20261007+y / 20261008+y), reported.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
TMP = HERE / "tmp"
K2 = HERE.parent / "oc_k2placebo" / "tmp"
sys.path.insert(0, str(HERE))
import stagger_rule as sr  # noqa: E402

BASE_GATE_N = 22312
BASE_GATE_SUMS = (0.911273, 0.832599, 2.099814, 3.197390, 0.677229)
BASE_GATE_SUM5Y = 7.718304
N_PERM = 1000
SEED_TIMING = 20261007
SEED_BLOCK = 20261008
BLOCK = 42
HB_S = 600
PHASES = (0, 1, 2, 3)
ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")


def main() -> None:
    t0 = time.time()
    last_hb = t0
    led = dict(np.load(K2 / "ledger.npz"))
    for k in ("phase", "coin", "year"):
        led[k] = led[k].astype(np.int64)
    for k in ("w", "y10"):
        led[k] = led[k].astype(np.float64)
    n = len(led["w"])
    assert n == BASE_GATE_N, f"REF n {n} != {BASE_GATE_N}"
    base_y = sr.phase_mean_sums(led["phase"], led["year"], led["w"], led["y10"], 5)
    for got, exp in zip(base_y, BASE_GATE_SUMS):
        assert abs(got - exp) <= 0.002, f"REF base {base_y} != {BASE_GATE_SUMS}"
    assert abs(sum(base_y) - BASE_GATE_SUM5Y) <= 0.002, f"sum5y {sum(base_y)}"
    print(f"REF gate OK n={n} base={base_y}", flush=True)

    out = {"reproduction": {"n": n, "base": [round(float(v), 6) for v in base_y],
                            "sum5y": round(float(sum(base_y)), 6)}}
    for variant in ("V1", "V2"):
        d = dict(np.load(TMP / f"stagger_2021_{variant}.npz"))
        for k in ("phase", "coin", "year", "bar_time", "rung", "kindA", "kindB"):
            d[k] = d[k].astype(np.int64)
        for k in ("wA", "yA", "wB", "yB"):
            d[k] = d[k].astype(np.float64)
        ph, yr = d["phase"], d["year"]
        cA, cB = d["wA"] * d["yA"], d["wB"] * d["yB"]
        cT = cA + cB
        stag_y = sr.phase_mean_sums(ph, yr, np.ones_like(cT), cT, 5)
        years = []
        for y in range(5):
            m = yr == y
            mb = led["year"] == y
            w_stag = float((d["wA"][m] + d["wB"][m]).sum())
            w_base = float(led["w"][mb].sum())
            years.append({
                "year": ANCH5[y],
                "n_base": int(mb.sum()),
                "n_stag_rows": int(m.sum()),
                "n_A": int((d["wA"][m] > 0).sum()),
                "n_B": int((d["wB"][m] > 0).sum()),
                "n_both": int((((d["wA"][m] > 0) & (d["wB"][m] > 0))).sum()),
                "base": round(float(base_y[y]), 6),
                "stag": round(float(stag_y[y]), 6),
                "gain": round(float(stag_y[y]) - float(base_y[y]), 6),
                "exposure_ratio": round(w_stag / w_base, 6) if w_base else 0.0,
            })
            print(f"  {variant} {ANCH5[y]} base={base_y[y]:.6f} stag={stag_y[y]:.6f} "
                  f"gain={stag_y[y]-base_y[y]:.6f}", flush=True)
        gains = [stag_y[y] - base_y[y] for y in range(5)]
        dsum = float(sum(gains))
        shalf = int(sum(1 for g in gains if g > 0))
        timing, block = [], []
        for y in range(5):
            rng = np.random.default_rng(SEED_TIMING + y)
            my = yr == y
            idx = np.where(my)[0]
            fwA, fwB, fph = cA[idx], cB[idx], ph[idx]
            actual = float(sr.phase_mean_sums(fph, np.zeros_like(fph),
                                              np.ones_like(fwA), fwA + fwB, 1)[0])
            perms = np.empty(N_PERM)
            for k in range(N_PERM):
                pb = rng.permutation(fwB)
                tot = fwA + pb
                perms[k] = sum(float(tot[fph == p].sum()) for p in PHASES) / 4.0
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            timing.append({"year": ANCH5[y], "actual": round(actual, 6),
                           "percentile": round(float(pct), 2)})
            print(f"timing {variant} {ANCH5[y]} pct={pct:.2f}", flush=True)
            if time.time() - last_hb >= HB_S:
                last_hb = time.time()
                print(f"[hb] compute_2021 alive elapsed {last_hb-t0:.0f}s", flush=True)
        for y in range(5):
            rng = np.random.default_rng(SEED_BLOCK + y)
            my = yr == y
            idx = np.where(my)[0]
            fwA, fwB = cA[idx], cB[idx]
            fph, fco = ph[idx], d["coin"][idx]
            actual = float(sr.phase_mean_sums(fph, np.zeros_like(fph),
                                              np.ones_like(fwA), fwA + fwB, 1)[0])
            groups: dict = {}
            for ii in range(len(idx)):
                groups.setdefault((int(fco[ii]), int(fph[ii])), []).append(ii)
            perms = np.empty(N_PERM)
            cur = np.empty_like(fwB)
            for k in range(N_PERM):
                for g, members in groups.items():
                    vals = fwB[members]
                    chunks = [vals[b:b + BLOCK] for b in range(0, len(vals), BLOCK)]
                    order = rng.permutation(len(chunks))
                    cur[members] = np.concatenate([chunks[b] for b in order])
                tot = fwA + cur
                perms[k] = sum(float(tot[fph == p].sum()) for p in PHASES) / 4.0
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            block.append({"year": ANCH5[y], "actual": round(actual, 6),
                          "percentile": round(float(pct), 2)})
            print(f"block {variant} {ANCH5[y]} pct={pct:.2f}", flush=True)
        out[variant] = {"per_year": years, "dSum5y": round(dsum, 6),
                        "sum_half": f"{shalf}/5",
                        "secondary_pass": bool(dsum >= 0.273 and shalf >= 4),
                        "timing_placebo": timing, "block_placebo": block,
                        "n_rows": int(len(d["wA"]))}
        print(f"{variant}: dSum5y={dsum:.6f} sum-half={shalf}/5 "
              f"pass={dsum >= 0.273 and shalf >= 4}", flush=True)
    (TMP / "stagger_2021.json").write_text(json.dumps(out, indent=1))
    print("wrote tmp/stagger_2021.json", flush=True)


if __name__ == "__main__":
    main()
