"""oc_cascadedelay replica + placebo gate: post-cascade budget halving on the reused ledger.

Method = oc_crashgate/compute_placebo.py shape with the frozen delay mults:
  cooled(T, shift) from delay_mult_4shift.parquet (market-wide per shift:
  ANY major's >4sg bar cools ALL coins on that shift); mult = 0.5 if cooled
  else 1.0. V1 N = 7d; V2 N = 3d. Book untouched (dip-only overlay).
Ledger REUSED read-only from oc_k2placebo/tmp (ledger.npz + bt_all.npy;
  reproduction gate: n == 22312 and base 4-phase-mean sum5y == 7.718304 +- 0.002).

Per year y: base(y), delay(y), realised_mean(y), norm(y) = delay(y)/realised_mean.
Gate (IDEAS5 header): sum-half (delay >= base in >= 4/5 years) PLUS
  dSum5y >= +0.273. Timing/block placebo (1000 perms, seeds 20261007+y /
  20261008+y, percentile = 100*(1+#{perm<=actual})/1001, signif iff >= 95)
  reported as supporting evidence. Placebo null (pre-registered adaptation):
  time-bar permutation WITHIN (year, shift) — preserves per-shift cooled counts
  and the market-wide cross-sym sharing. CPU-only (numpy).
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
from delay_rule import HALF  # noqa: E402 (assert the frozen half)

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
VARIANTS = ("V1", "V2")
MULT_COL = {"V1": "mult_V1", "V2": "mult_V2"}


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
    d = pd.read_parquet(HERE / "delay_mult_4shift.parquet")
    d["T"] = pd.to_datetime(d["T"], utc=True)
    exact = {}
    per_shift = {}
    for s in SHIFTS:
        sub = d[d["shift"] == s].sort_values("T")
        t_ns = sub["T"].values.astype("datetime64[ns]").astype(np.int64)
        per_shift[s] = {c: sub[c].to_numpy(dtype=float) for c in
                        ("mult_V1", "mult_V2")}
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
    assert HALF == 0.5
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
            "ledger": "oc_k2placebo/tmp/ledger.npz + bt_all.npy read-only (identical build_base)",
            "delay": "delay_mult_4shift.parquet (closes-only >4sg triggers, union over 5 majors per shift; 0.5 in (tc, tc+Nd])",
            "seed_timing": SEED_TIMING,
            "seed_block": SEED_BLOCK,
            "n_perm": N_PERM,
            "block": BLOCK,
            "rule": "mult 0.5 if cooled else 1.0, market-wide per shift (V1 N=7d, V2 N=3d); book untouched",
            "normalisation": "norm(y)=delay(y)/realised_mean(y); perm norms use the ACTUAL denominator",
            "percentile": "100*(1+#{perm<=actual})/1001; significant iff >=95",
            "placebo_null": "time-bar permutation WITHIN (year, shift) (1000 uniform; block-42 chronological within (year, shift))",
            "gate": "sum-half (delay>=base in >=4/5y) PLUS dSum5y>=+0.273; replica DD-half not scored from this ledger (no daily path) — binding DD check is the 4-phase engine",
        },
        "reproduction": {"base_sum5y_gate": BASE_GATE,
                         "base_sums": [round(v, 6) for v in base_y],
                         "base_sum5y": round(got5, 6), "n_fills": int(n)},
    }

    for variant in VARIANTS:
        mult = np.array([mult_at(int(ph[i]), bt_all[i], variant, exact, per_shift)
                         for i in range(n)], dtype=float)
        vals = sorted(set(np.round(mult, 6)))
        assert set(vals) <= {0.5, 1.0}, vals
        print(f"{variant}: join n={n} cooled_share={float((mult == 0.5).mean()):.4f} "
              f"mult values={vals}", flush=True)

        delay_y = phase_mean_sums(ph, yr, w * mult, yv)
        dsum = float(sum(delay_y) - sum(base_y))
        sum_ge = sum(1 for y in range(5) if delay_y[y] >= base_y[y] - 1e-12)
        years = []
        for y in range(5):
            m = yr == y
            rm = float(mult[m].mean()) if m.any() else 1.0
            years.append({"year": ANCH[y].date().isoformat(),
                          "n_fills": int(m.sum()),
                          "base": round(float(base_y[y]), 6),
                          "delayed": round(float(delay_y[y]), 6),
                          "realised_mean": round(rm, 6),
                          "norm": round(float(delay_y[y]) / rm, 6) if rm else 0.0,
                          "cooled_share_fills": round(float((mult[m] == 0.5).mean()), 4)
                          if m.any() else None})
        for r in years:
            print(f"  {r['year']} n={r['n_fills']} base={r['base']} "
                  f"delayed={r['delayed']} rm={r['realised_mean']} "
                  f"norm={r['norm']} cooled={r['cooled_share_fills']}", flush=True)
        print(f"{variant}: dSum5y={dsum:.6f} (gate >= {DSUM_GATE}); "
              f"sum-half years>=base: {sum_ge}/5", flush=True)

        # ---- time-bar universes per (year, shift) ----
        uni = {}   # (y, s) -> mult array (chronological)
        for y in range(5):
            lo = ANCH[y]
            hi = ANCH[y + 1] if y < 4 else YEAR_END
            for s in SHIFTS:
                t_ns = per_shift[s]["t_ns"]
                col = per_shift[s][MULT_COL[variant]]
                lo_ns, hi_ns = np.int64(lo.value), np.int64(hi.value)
                m = (t_ns >= lo_ns) & (t_ns < hi_ns)
                uni[(y, s)] = col[m].astype(float)
        print(f"bar universes (y,s) sizes: {[len(uni[(y, s)]) for y in range(5) for s in SHIFTS][:8]}...",
              flush=True)

        # fill -> position in its (y, s) universe
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
        assert (fill_pos >= 0).all(), f"{(fill_pos < 0).sum()} fills w/o time-bar"

        timing = []
        for y in range(5):
            rng = np.random.default_rng(SEED_TIMING + y)
            my = (yr == y)
            fm_actual = mult[my]
            actual = float(delay_y[y]) / float(fm_actual.mean())
            fill_w = w[my]
            fill_y = yv[my]
            fill_ph = ph[my]
            fill_p = fill_pos[my]
            # per-(y,s) slices for structured permutation
            slices = {}
            for s in SHIFTS:
                sm = fill_ph == s
                slices[s] = (np.where(sm)[0], uni[(y, s)])
            denom_y = float(fm_actual.mean())
            perms = np.empty(N_PERM)
            last_hb = time.time()
            for k in range(N_PERM):
                fm = np.empty(my.sum())
                for s in SHIFTS:
                    loc, arr = slices[s]
                    pm = rng.permutation(arr)
                    # map: position of each fill in universe -> permuted mult
                    upos = fill_p[loc]
                    fm[loc] = pm[upos]
                s_sum = 0.0
                for p in PHASES:
                    mp = fill_ph == p
                    s_sum += float((fill_w[mp] * fm[mp] * fill_y[mp]).sum())
                perms[k] = (s_sum / 4.0) / denom_y
                if time.time() - last_hb > 600:
                    print(f"timing {variant} y={y} perm {k}/{N_PERM} "
                          f"elapsed={time.time() - t0:.0f}s", flush=True)
                    last_hb = time.time()
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            timing.append({"year": ANCH[y].date().isoformat(),
                           "actual_norm": round(actual, 6),
                           "p5": round(float(np.quantile(perms, 0.05)), 6),
                           "p50": round(float(np.quantile(perms, 0.50)), 6),
                           "p95": round(float(np.quantile(perms, 0.95)), 6),
                           "percentile": round(float(pct), 2)})
            print(f"timing {variant} y={y} actual={actual:.6f} "
                  f"p5={np.quantile(perms, 0.05):.6f} p50={np.quantile(perms, 0.50):.6f} "
                  f"p95={np.quantile(perms, 0.95):.6f} pct={pct:.2f}", flush=True)

        block = []
        for y in range(5):
            rng = np.random.default_rng(SEED_BLOCK + y)
            my = (yr == y)
            fm_actual = mult[my]
            actual = float(delay_y[y]) / float(fm_actual.mean())
            fill_w = w[my]
            fill_y = yv[my]
            fill_ph = ph[my]
            fill_p = fill_pos[my]
            denom_y = float(fm_actual.mean())
            # precompute block structure per (y, s)
            blk_of = {}
            for s in SHIFTS:
                arr = uni[(y, s)]
                blks = [arr[b:b + BLOCK] for b in range(0, len(arr), BLOCK)]
                blk_of[s] = blks
            perms = np.empty(N_PERM)
            last_hb = time.time()
            for k in range(N_PERM):
                fm = np.empty(my.sum())
                for s in SHIFTS:
                    loc = np.where(fill_ph == s)[0]
                    blks = blk_of[s]
                    order = rng.permutation(len(blks))
                    seq = np.concatenate([blks[b] for b in order]) if blks else np.array([])
                    upos = fill_p[loc]
                    fm[loc] = seq[upos]
                s_sum = 0.0
                for p in PHASES:
                    mp = fill_ph == p
                    s_sum += float((fill_w[mp] * fm[mp] * fill_y[mp]).sum())
                perms[k] = (s_sum / 4.0) / denom_y
                if time.time() - last_hb > 600:
                    print(f"block {variant} y={y} perm {k}/{N_PERM} "
                          f"elapsed={time.time() - t0:.0f}s", flush=True)
                    last_hb = time.time()
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            block.append({"year": ANCH[y].date().isoformat(),
                          "actual_norm": round(actual, 6),
                          "p5": round(float(np.quantile(perms, 0.05)), 6),
                          "p50": round(float(np.quantile(perms, 0.50)), 6),
                          "p95": round(float(np.quantile(perms, 0.95)), 6),
                          "percentile": round(float(pct), 2)})
            print(f"block {variant} y={y} actual={actual:.6f} "
                  f"p5={np.quantile(perms, 0.05):.6f} p50={np.quantile(perms, 0.50):.6f} "
                  f"p95={np.quantile(perms, 0.95):.6f} pct={pct:.2f}", flush=True)

        res[variant] = {"per_year": years, "timing_placebo": timing,
                        "block_placebo": block,
                        "dSum5y": round(dsum, 6),
                        "sum_half_years_ge": int(sum_ge),
                        "gate_sum_half": bool(sum_ge >= 4),
                        "gate_dsum": bool(dsum >= DSUM_GATE),
                        "gate_pass": bool(sum_ge >= 4 and dsum >= DSUM_GATE)}

    (HERE / "tmp").mkdir(exist_ok=True)
    (HERE / "tmp/replica_cascadedelay.json").write_text(json.dumps(res, indent=1))
    print("wrote tmp/replica_cascadedelay.json", flush=True)
    for variant in VARIANTS:
        r = res[variant]
        print(f"{variant}: dSum5y={r['dSum5y']} sum_half={r['sum_half_years_ge']}/5 "
              f"gate_pass={r['gate_pass']}", flush=True)


if __name__ == "__main__":
    main()
