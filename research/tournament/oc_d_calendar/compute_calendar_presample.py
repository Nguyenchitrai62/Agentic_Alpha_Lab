"""Calendar pre-sample replica + placebos (CPU-only).

Reuses oc_presampletilt ledger read-only (reproduction gate n==9731,
per-leg 909/2986/3115/2721, base sums == 2.313362/2.678870/0.577643/0.297538).
Joins per-fill (shift=phase, T) calendar mults (V1 weekend 1.25, V2 session 1.2;
market-wide per time-bar) with causal ffill fallback; missing -> 1.0.
Per-year 4-phase-mean base/tilted/realised/norm/gain.
Placebos (1000 perms, PRIMARY null = time-bar permutation within (year, shift),
seed 20261007+y; block-42 per (year, shift), seed 20261008+y).
Percentile = 100*(1+#{perm<=actual})/1001, signif iff >=95. Heartbeat every 600 s.
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

sys.path.insert(0, str(HERE))
from calendar_rule import phase_mean_sums  # noqa: E402

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
VARIANTS = ("V1", "V2")
MULT_COL = {"V1": "mult_V1", "V2": "mult_V2"}
HI = {"V1": 1.25, "V2": 1.2}
HB_S = 600


def load_mult():
    d = pd.read_parquet(HERE / "calendar_mult_presample.parquet")
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
    led = dict(np.load(PST / "tmp/ledger_presample.npz"))
    for k in ("phase", "coin", "year", "t_ord", "rung"):
        led[k] = led[k].astype(np.int64)
    for k in ("w", "y10"):
        led[k] = led[k].astype(np.float64)
    bt_all = np.load(PST / "tmp/bt_presample.npy", allow_pickle=True)
    n = len(led["w"])
    print(f"loaded presample ledger n={n}", flush=True)
    assert n == N_GATE, f"ledger size {n} != {N_GATE}"
    for y, g in enumerate(PER_LEG_GATE):
        got = int((led["year"] == y).sum())
        assert got == g, f"leg {LEG_ORDER[y]} n {got} != {g}"

    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)
    base_y = phase_mean_sums(ph, yr, w, yv, n_years=4)
    print(f"base 4-phase-mean sums={[round(v, 6) for v in base_y]}", flush=True)
    for y in range(4):
        assert abs(base_y[y] - BASE_GATE[y]) <= 1e-6, f"base {LEG_ORDER[y]} fail"

    exact, per_shift = load_mult()
    nmiss_total = 0
    res = {
        "config": {
            "ledger": "oc_presampletilt/tmp/ledger_presample.npz read-only (D0+B1, SPOT)",
            "mult": "calendar_mult_presample.parquet (frozen UTC windows; V1 Sat/Sun 1.25, V2 00-08 1.2; market-wide per time-bar)",
            "seed_timing": SEED_TIMING, "seed_block": SEED_BLOCK,
            "n_perm": N_PERM, "block": BLOCK,
            "rule": "norm(y)=tilted(y)/realised_mean(y); gain=norm-base; perm norms use ACTUAL denominator",
            "percentile": "100*(1+#{perm<=actual})/1001; signif iff >=95",
            "nulls": "timing: time-bar permutation within (year,shift) (PRIMARY); block-42 per (year,shift) (diagnostic)",
        },
        "reproduction": {"per_leg_gate": list(PER_LEG_GATE),
                         "base_sums": [round(v, 6) for v in base_y],
                         "n_fills": int(n)},
    }

    for variant in VARIANTS:
        mult = np.array([mult_at(int(ph[i]), bt_all[i], variant, exact, per_shift)
                         for i in range(n)], dtype=float)
        hi = HI[variant]
        print(f"{variant}: boosted={(mult == hi).mean():.4f} "
              f"rest={(mult == 1.0).mean():.4f}", flush=True)
        tilt_y = phase_mean_sums(ph, yr, w * mult, yv, n_years=4)
        years = []
        for y in range(4):
            m = yr == y
            rm = float(mult[m].mean()) if m.any() else 1.0
            norm = float(tilt_y[y]) / rm if rm else 0.0
            years.append({"year": LEG_ORDER[y], "n_fills": int(m.sum()),
                          "base": round(float(base_y[y]), 6),
                          "tilted": round(float(tilt_y[y]), 6),
                          "realised_mean": round(rm, 6),
                          "norm": round(norm, 6),
                          "gain": round(norm - float(base_y[y]), 6),
                          "boosted_share": round(float((mult[m] == hi).mean()), 4)})
            print(f"  {LEG_ORDER[y]} base={base_y[y]:.6f} tilt={tilt_y[y]:.6f} "
                  f"rm={rm:.6f} norm={norm:.6f} gain={norm - base_y[y]:+.6f}", flush=True)

        # ---- timing null (PRIMARY): permute time-bar mults within (y, s) ----
        timing = []
        for y in range(4):
            rng = np.random.default_rng(SEED_TIMING + y)
            lo, hi_b = LEG_BOUNDS[LEG_ORDER[y]]
            lo_ns, hi_ns = np.int64(lo.value), np.int64(hi_b.value)
            denom = float(mult[yr == y].mean())
            actual = float(tilt_y[y]) / denom
            # per-shift year sequences + per-fill positions
            seq_of = {}
            for s in SHIFTS:
                t_ns = per_shift[s]["t_ns"]
                arr = per_shift[s][MULT_COL[variant]].astype(float)
                m = (t_ns >= lo_ns) & (t_ns < hi_ns)
                seq_of[s] = arr[m]
                assert len(seq_of[s]) > 0, f"empty grid y={y} s={s}"
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
            timing.append({"year": LEG_ORDER[y], "actual_norm": round(actual, 6),
                           "p5": round(float(np.quantile(perms, 0.05)), 6),
                           "p50": round(float(np.quantile(perms, 0.50)), 6),
                           "p95": round(float(np.quantile(perms, 0.95)), 6),
                           "percentile": round(float(pct), 2)})
            print(f"timing {variant} y={y} actual={actual:.6f} pct={pct:.2f}", flush=True)

        # ---- block null: 42-bar blocks per (y, s) ----
        block = []
        for y in range(4):
            rng = np.random.default_rng(SEED_BLOCK + y)
            lo, hi_b = LEG_BOUNDS[LEG_ORDER[y]]
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
            block.append({"year": LEG_ORDER[y], "actual_norm": round(actual, 6),
                          "p5": round(float(np.quantile(perms, 0.05)), 6),
                          "p50": round(float(np.quantile(perms, 0.50)), 6),
                          "p95": round(float(np.quantile(perms, 0.95)), 6),
                          "percentile": round(float(pct), 2)})
            print(f"block {variant} y={y} actual={actual:.6f} pct={pct:.2f}", flush=True)

        res[variant] = {"per_year": years, "timing_placebo": timing,
                        "block_placebo": block}

    (HERE / "tmp").mkdir(exist_ok=True)
    (HERE / "tmp/calendar_presample.json").write_text(json.dumps(res, indent=1))
    print("wrote tmp/calendar_presample.json", flush=True)


if __name__ == "__main__":
    main()
