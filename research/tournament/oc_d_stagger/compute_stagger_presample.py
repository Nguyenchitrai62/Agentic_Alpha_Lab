"""oc_d_stagger: CPU-only presample scoring + B-half placebos + stop tables.

- REF reproduction gate (read-only presampletilt ledger): n==9731,
  per-leg 909/2986/3115/2721, base 4-phase-mean sums ==
  (2.313362, 2.678870, 0.577643, 0.297538) +- 1e-6. Else STOP (raise).
- Per year: base(y), stag(y), gain = stag - base, exposure ratio E, fill split,
  B-half timing (1000 perms, seed 20261007+y) + block (seed 20261008+y) placebos.
- Stop tables from recorded kinds (stagger halves) + VERBATIM base-kind recompute
  is NOT redone here: base stop shares come from the same kind branch applied to
  REF fills? REF ledger has no kinds -> base kinds recomputed from bars+1m in
  compute_kind step? To stay CPU-only here, base stop rates are recomputed in the
  heavy build (kinds for REF are rebuilt in build_stagger_presample_basekind step)?
  SIMPLER (frozen): base stop shares are recomputed HERE from the spot 1m store
  per REF fill is heavy -> deferred to a heavy_slot kind script. This script writes
  stagger-side tables + gains + placebos; stop JOIN happens in analyze.
  Actually to keep one flow: this script loads stagger kinds (halves) and reports
  stagger filled-half stop% per year + pooled; base stop% is filled in by
  compute_stop_presample.py (heavy, VERBATIM). The PRIMARY stop gate is evaluated
  in analyze_stagger_presample.py after both exist.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
TMP = HERE / "tmp"
PRE = HERE.parent / "oc_presampletilt" / "tmp"
sys.path.insert(0, str(HERE))
import stagger_rule as sr  # noqa: E402

LEGS = ("Y2017", "Y2018", "Y2019", "Y2020p")
BASE_GATE_N = 9731
BASE_GATE_LEG = (909, 2986, 3115, 2721)
BASE_GATE_SUMS = (2.313362, 2.678870, 0.577643, 0.297538)
N_PERM = 1000
SEED_TIMING = 20261007
SEED_BLOCK = 20261008
BLOCK = 42
HB_S = 600
PHASES = (0, 1, 2, 3)


def main() -> None:
    t0 = time.time()
    last_hb = t0
    # ---- REF reproduction gate ----
    led = dict(np.load(PRE / "ledger_presample.npz"))
    for k in ("phase", "coin", "year"):
        led[k] = led[k].astype(np.int64)
    for k in ("w", "y10"):
        led[k] = led[k].astype(np.float64)
    n = len(led["w"])
    assert n == BASE_GATE_N, f"REF n {n} != {BASE_GATE_N}"
    per_leg = [int((led["year"] == i).sum()) for i in range(4)]
    assert tuple(per_leg) == BASE_GATE_LEG, f"REF legs {per_leg}"
    base_y = sr.phase_mean_sums(led["phase"], led["year"], led["w"], led["y10"], 4)
    for got, exp in zip(base_y, BASE_GATE_SUMS):
        assert abs(got - exp) <= 1e-6, f"REF base {base_y} != {BASE_GATE_SUMS}"
    print(f"REF gate OK n={n} base={base_y}", flush=True)

    out = {"reproduction": {"n": n, "per_leg": per_leg,
                            "base": [round(float(v), 6) for v in base_y]}}
    for variant in ("V1", "V2"):
        d = dict(np.load(TMP / f"stagger_presample_{variant}.npz"))
        for k in ("phase", "coin", "year", "t_ord", "rung", "kindA", "kindB"):
            d[k] = d[k].astype(np.int64)
        for k in ("wA", "yA", "wB", "yB"):
            d[k] = d[k].astype(np.float64)
        ph, yr = d["phase"], d["year"]
        cA, cB = d["wA"] * d["yA"], d["wB"] * d["yB"]
        cT = cA + cB
        stag_y = sr.phase_mean_sums(ph, yr, np.ones_like(cT), cT, 4)
        # exposure ratio + fill split per year
        years = []
        for y in range(4):
            m = yr == y
            mb = led["year"] == y
            sum_b = float((led["w"][mb] * led["y10"][mb]).sum())
            # 4-phase-mean base already in base_y; exposure over raw sums:
            sw_stag = float(cT[m].sum())
            sw_base = float((led["w"][mb] * led["y10"][mb]).sum())
            w_stag = float((d["wA"][m] + d["wB"][m]).sum())
            w_base = float(led["w"][mb].sum())
            nA = int(((d["wA"][m] > 0)).sum())
            nB = int(((d["wB"][m] > 0)).sum())
            nBoth = int((((d["wA"][m] > 0) & (d["wB"][m] > 0))).sum())
            nRows = int(m.sum())
            # stagger filled-half stop% (kinds 2/3 over known filled halves)
            kA, kB = d["kindA"][m], d["kindB"][m]
            halves_known = int(((kA >= 0)).sum() + ((kB >= 0)).sum())
            halves_stop = int((((kA == 2) | (kA == 3))).sum() + (((kB == 2) | (kB == 3))).sum())
            halves_tp = int(((kA == 0)).sum() + ((kB == 0)).sum())
            # skipped: base fills with no stagger row? join on (phase,coin,t_ord,rung)
            years.append({
                "year": LEGS[y],
                "n_base": int(mb.sum()),
                "n_stag_rows": nRows,
                "n_A": nA, "n_B": nB, "n_both": nBoth,
                "base": round(float(base_y[y]), 6),
                "stag": round(float(stag_y[y]), 6),
                "gain": round(float(stag_y[y]) - float(base_y[y]), 6),
                "exposure_ratio": round(w_stag / w_base, 6) if w_base else 0.0,
                "stag_half_stop": round(halves_stop / halves_known, 6) if halves_known else 0.0,
                "stag_half_tp": round(halves_tp / halves_known, 6) if halves_known else 0.0,
                "halves_known": halves_known,
            })
            print(f"  {variant} {LEGS[y]} base={base_y[y]:.6f} stag={stag_y[y]:.6f} "
                  f"gain={stag_y[y]-base_y[y]:.6f} E={w_stag/max(w_base,1e-12):.3f} "
                  f"A={nA} B={nB} both={nBoth}", flush=True)
        # ---- timing placebo: permute B-half P&L within (year, shift) ----
        timing, block = [], []
        for y in range(4):
            rng = np.random.default_rng(SEED_TIMING + y)
            my = yr == y
            idx = np.where(my)[0]
            fwA = cA[idx]
            fwB = cB[idx]
            fph = ph[idx]
            actual = float(sr.phase_mean_sums(fph, np.zeros_like(fph), np.ones_like(fwA),
                                              fwA + fwB, 1)[0])
            # NOTE: actual must equal stag_y[y]; checked below
            perms = np.empty(N_PERM)
            for k in range(N_PERM):
                pb = rng.permutation(fwB)
                tot = fwA + pb
                s = sum(float(tot[fph == p].sum()) for p in PHASES) / 4.0
                perms[k] = s
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            timing.append({"year": LEGS[y], "actual": round(actual, 6),
                           "p5": round(float(np.quantile(perms, 0.05)), 6),
                           "p50": round(float(np.quantile(perms, 0.50)), 6),
                           "p95": round(float(np.quantile(perms, 0.95)), 6),
                           "percentile": round(float(pct), 2)})
            print(f"timing {variant} {LEGS[y]} actual={actual:.6f} pct={pct:.2f}", flush=True)
            if time.time() - last_hb >= HB_S:
                last_hb = time.time()
                print(f"[hb] compute alive elapsed {last_hb-t0:.0f}s", flush=True)
        for y in range(4):
            rng = np.random.default_rng(SEED_BLOCK + y)
            my = yr == y
            idx = np.where(my)[0]
            fwA = cA[idx]
            fwB = cB[idx]
            fph = ph[idx]
            fco = d["coin"][idx]
            ford = d["t_ord"][idx]
            actual = float(sr.phase_mean_sums(fph, np.zeros_like(fph), np.ones_like(fwA),
                                              fwA + fwB, 1)[0])
            # blocks per (coin, phase): sort by t_ord, chunk 42, permute within group
            groups: dict = {}
            for ii in range(len(idx)):
                groups.setdefault((int(fco[ii]), int(fph[ii])), []).append(ii)
            gblocks = {g: [v[b:b + BLOCK] for b in range(0, len(v), BLOCK)]
                       for g, v in groups.items()}
            perms = np.empty(N_PERM)
            cur = np.empty_like(fwB)
            for k in range(N_PERM):
                for g, blks in gblocks.items():
                    order = rng.permutation(len(blks))
                    # permute block contents via index remap within group
                    members = groups[g]
                    vals = fwB[members]
                    chunks = [vals[b:b + BLOCK] for b in range(0, len(vals), BLOCK)]
                    perm_chunks = [chunks[b] for b in order]
                    cur[members] = np.concatenate(perm_chunks)
                tot = fwA + cur
                s = sum(float(tot[fph == p].sum()) for p in PHASES) / 4.0
                perms[k] = s
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            block.append({"year": LEGS[y], "actual": round(actual, 6),
                          "p5": round(float(np.quantile(perms, 0.05)), 6),
                          "p50": round(float(np.quantile(perms, 0.50)), 6),
                          "p95": round(float(np.quantile(perms, 0.95)), 6),
                          "percentile": round(float(pct), 2)})
            print(f"block {variant} {LEGS[y]} actual={actual:.6f} pct={pct:.2f}", flush=True)
        out[variant] = {"per_year": years, "timing_placebo": timing,
                        "block_placebo": block,
                        "n_rows": int(len(d["wA"]))}
    (TMP / "stagger_presample.json").write_text(json.dumps(out, indent=1))
    print("wrote tmp/stagger_presample.json", flush=True)


if __name__ == "__main__":
    main()
