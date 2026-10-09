"""Calendar 2021-2026 replica gate (CPU-only).

Reuses oc_k2placebo ledger read-only (reproduction gate n==22312, base sums ==
0.911273/0.832599/2.099814/3.197390/0.677229, sum5y == 7.718304 +- 0.002).
Joins per-fill (shift=phase, T) calendar mults with causal ffill fallback;
missing -> 1.0. Per-year base/tilted/realised/norm/gain; dSum5y + sum-half.
Timing/block placebos per year (same within-(y,s) nulls, y = 0..4).
SECONDARY pass: dSum5y >= +0.273 AND sum-half >= 4/5.
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
from calendar_rule import phase_mean_sums  # noqa: E402

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
ANCH = [pd.Timestamp(a, tz="UTC") for a in ANCH5]
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
SEED_TIMING = 20261007
SEED_BLOCK = 20261008
N_PERM = 1000
BLOCK = 42
N_GATE = 22312
BASE_GATE = (0.911273, 0.832599, 2.099814, 3.197390, 0.677229)
SUM5Y_GATE = 7.718304
PHASES = (0, 1, 2, 3)
SHIFTS = (0, 1, 2, 3)
VARIANTS = ("V1", "V2")
MULT_COL = {"V1": "mult_V1", "V2": "mult_V2"}
HI = {"V1": 1.25, "V2": 1.2}
HB_S = 600


def load_mult():
    d = pd.read_parquet(HERE / "calendar_mult_2021.parquet")
    d["T"] = pd.to_datetime(d["T"], utc=True)
    exact = {}
    per_shift = {}
    for s in SHIFTS:
        sub = d[d["shift"] == s].sort_values("T")
        t_ns = sub["T"].values.astype("datetime64[ns]").astype(np.int64)
        per_shift[s] = {c: sub[c].to_numpy(dtype=float) for c in ("mult_V1", "mult_V2")}
        per_shift[s]["t_ns"] = t_ns
        per_shift[s]["T"] = pd.to_datetime(sub["T"], utc=True).tolist()
        for t, a, e in zip(per_shift[s]["T"], per_shift[s]["mult_V1"],
                           per_shift[s]["mult_V2"]):
            exact[(int(s), pd.Timestamp(t))] = (float(a), float(e))
    return exact, per_shift


def mult_at(shift, t, variant, exact, per_shift):
    key = (int(shift), pd.Timestamp(t))
    hit = exact.get(key)
    if hit is not None:
        return hit[0] if variant == "V1" else hit[1]
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
    last_hb = t0
    led = dict(np.load(K2P / "tmp/ledger.npz"))
    for k in ("phase", "coin", "year", "bar_time", "rung"):
        led[k] = led[k].astype(np.int64)
    for k in ("w", "y10"):
        led[k] = led[k].astype(np.float64)
    bt_all = np.load(K2P / "tmp/bt_all.npy", allow_pickle=True)
    n = len(led["w"])
    print(f"loaded k2placebo ledger n={n}", flush=True)
    assert n == N_GATE, f"ledger size {n} != {N_GATE}"

    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)
    base_y = phase_mean_sums(ph, yr, w, yv, n_years=5)
    print(f"base 4-phase-mean sums={[round(v, 6) for v in base_y]}", flush=True)
    for y in range(5):
        assert abs(base_y[y] - BASE_GATE[y]) <= 0.002, f"base y{y} fail"
    assert abs(sum(base_y) - SUM5Y_GATE) <= 0.002, "sum5y fail"

    exact, per_shift = load_mult()
    res = {
        "config": {
            "ledger": "oc_k2placebo/tmp/ledger.npz read-only (D0+B1, perp 1m)",
            "mult": "calendar_mult_2021.parquet (frozen UTC windows; market-wide per time-bar)",
            "seed_timing": SEED_TIMING, "seed_block": SEED_BLOCK,
            "n_perm": N_PERM, "block": BLOCK,
            "rule": "norm(y)=tilted(y)/realised_mean(y); gain=norm-base; perm norms use ACTUAL denominator",
            "percentile": "100*(1+#{perm<=actual})/1001; signif iff >=95",
            "gate": "SECONDARY pass iff dSum5y >= +0.273 AND sum-half >= 4/5",
        },
        "reproduction": {"base_sums": [round(v, 6) for v in base_y],
                         "base_sum5y": round(float(sum(base_y)), 6),
                         "n_fills": int(n)},
    }

    for variant in VARIANTS:
        mult = np.array([mult_at(int(ph[i]), bt_all[i], variant, exact, per_shift)
                         for i in range(n)], dtype=float)
        hi = HI[variant]
        print(f"{variant}: boosted={(mult == hi).mean():.4f}", flush=True)
        tilt_y = phase_mean_sums(ph, yr, w * mult, yv, n_years=5)
        years = []
        for y in range(5):
            m = yr == y
            rm = float(mult[m].mean()) if m.any() else 1.0
            norm = float(tilt_y[y]) / rm if rm else 0.0
            years.append({"year": ANCH5[y], "n_fills": int(m.sum()),
                          "base": round(float(base_y[y]), 6),
                          "tilted": round(float(tilt_y[y]), 6),
                          "realised_mean": round(rm, 6),
                          "norm": round(norm, 6),
                          "gain": round(norm - float(base_y[y]), 6),
                          "boosted_share": round(float((mult[m] == hi).mean()), 4)})
            print(f"  {ANCH5[y]} base={base_y[y]:.6f} tilt={tilt_y[y]:.6f} "
                  f"rm={rm:.6f} norm={norm:.6f} gain={norm - base_y[y]:+.6f}", flush=True)

        timing = []
        for y in range(5):
            rng = np.random.default_rng(SEED_TIMING + y)
            lo, hi_b = (ANCH[y], ANCH[y + 1] if y < 4 else YEAR_END)
            lo_ns, hi_ns = np.int64(lo.value), np.int64(hi_b.value)
            denom = float(mult[yr == y].mean())
            actual = float(tilt_y[y]) / denom
            seq_of = {}
            for s in SHIFTS:
                t_ns = per_shift[s]["t_ns"]
                arr = per_shift[s][MULT_COL[variant]].astype(float)
                m = (t_ns >= lo_ns) & (t_ns < hi_ns)
                seq_of[s] = arr[m]
            my = np.where(yr == y)[0]
            pos = np.empty(len(my), dtype=np.int64)
            for k, j in enumerate(my):
                t_ns = per_shift[int(ph[j])]["t_ns"]
                m = (t_ns >= lo_ns) & (t_ns < hi_ns)
                grid = t_ns[m]
                q = pd.Timestamp(bt_all[j])
                if q.tzinfo is None:
                    q = q.tz_localize("UTC")
                pos[k] = int(np.searchsorted(grid, np.int64(q.value), side="right")) - 1
            assert (pos >= 0).all(), f"timing map miss y={y}"
            fill_w = w[my]
            fill_y = yv[my]
            fill_ph = ph[my]
            fill_s = ph[my]
            perms = np.empty(N_PERM)
            for k in range(N_PERM):
                perm_seq = {s: rng.permutation(seq_of[s]) for s in SHIFTS}
                fm = np.array([perm_seq[int(fill_s[t])][pos[t]] for t in range(len(my))])
                s_sum = 0.0
                for p in PHASES:
                    mp = fill_ph == p
                    s_sum += float((fill_w[mp] * fm[mp] * fill_y[mp]).sum())
                perms[k] = (s_sum / 4.0) / denom
                if time.time() - last_hb > HB_S:
                    print(f"[hb] timing {variant} y={y} perm {k}/{N_PERM}", flush=True)
                    last_hb = time.time()
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            timing.append({"year": ANCH5[y], "actual_norm": round(actual, 6),
                           "p5": round(float(np.quantile(perms, 0.05)), 6),
                           "p50": round(float(np.quantile(perms, 0.50)), 6),
                           "p95": round(float(np.quantile(perms, 0.95)), 6),
                           "percentile": round(float(pct), 2)})
            print(f"timing {variant} y={y} actual={actual:.6f} pct={pct:.2f}", flush=True)

        block = []
        for y in range(5):
            rng = np.random.default_rng(SEED_BLOCK + y)
            lo, hi_b = (ANCH[y], ANCH[y + 1] if y < 4 else YEAR_END)
            lo_ns, hi_ns = np.int64(lo.value), np.int64(hi_b.value)
            blk_of = {}
            for s in SHIFTS:
                t_ns = per_shift[s]["t_ns"]
                arr = per_shift[s][MULT_COL[variant]].astype(float)
                m = (t_ns >= lo_ns) & (t_ns < hi_ns)
                seq = arr[m].astype(float)
                blk_of[s] = [seq[b:b + BLOCK] for b in range(0, len(seq), BLOCK)]
            my = np.where(yr == y)[0]
            denom = float(mult[my].mean())
            actual = float(tilt_y[y]) / denom
            pos = np.empty(len(my), dtype=np.int64)
            for k, j in enumerate(my):
                t_ns = per_shift[int(ph[j])]["t_ns"]
                m = (t_ns >= lo_ns) & (t_ns < hi_ns)
                grid = t_ns[m]
                q = pd.Timestamp(bt_all[j])
                if q.tzinfo is None:
                    q = q.tz_localize("UTC")
                pos[k] = int(np.searchsorted(grid, np.int64(q.value), side="right")) - 1
            assert (pos >= 0).all(), f"block map miss y={y}"
            fill_w = w[my]
            fill_y = yv[my]
            fill_ph = ph[my]
            perms = np.empty(N_PERM)
            for k in range(N_PERM):
                perm_seq = {}
                for s in SHIFTS:
                    blks = blk_of[s]
                    order = rng.permutation(len(blks)) if blks else np.array([], dtype=int)
                    perm_seq[s] = np.concatenate([blks[b] for b in order]) if blks else np.array([])
                fm = np.array([perm_seq[int(ph[my[t]])][pos[t]] for t in range(len(my))])
                s_sum = 0.0
                for p in PHASES:
                    mp = fill_ph == p
                    s_sum += float((fill_w[mp] * fm[mp] * fill_y[mp]).sum())
                perms[k] = (s_sum / 4.0) / denom
                if time.time() - last_hb > HB_S:
                    print(f"[hb] block {variant} y={y} perm {k}/{N_PERM}", flush=True)
                    last_hb = time.time()
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            block.append({"year": ANCH5[y], "actual_norm": round(actual, 6),
                          "p5": round(float(np.quantile(perms, 0.05)), 6),
                          "p50": round(float(np.quantile(perms, 0.50)), 6),
                          "p95": round(float(np.quantile(perms, 0.95)), 6),
                          "percentile": round(float(pct), 2)})
            print(f"block {variant} y={y} actual={actual:.6f} pct={pct:.2f}", flush=True)

        gains = [r["gain"] for r in years]
        res[variant] = {"per_year": years, "timing_placebo": timing,
                        "block_placebo": block,
                        "dSum5y": round(float(sum(gains)), 6),
                        "sum_half": int(sum(1 for g in gains if g > 0))}

    (HERE / "tmp").mkdir(exist_ok=True)
    (HERE / "tmp/calendar_2021.json").write_text(json.dumps(res, indent=1))
    print("wrote tmp/calendar_2021.json", flush=True)


if __name__ == "__main__":
    main()
