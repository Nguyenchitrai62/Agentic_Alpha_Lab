"""oc_cboostpre replica + placebo: post-cascade budget boost on the pre-sample ledger.

Method inherited verbatim from oc_cascadeboost/compute_replica_gate.py, applied to the
pre-sample grid/ledger (4 years Y2017..Y2020p instead of 5):
  boosted(T, shift) from boost_mult_presample.parquet (market-wide per shift:
  ANY available major's >4sg bar boosts ALL coins on that shift); mult = 1.5 if boosted
  else 1.0. B7 N = 7d; B3 N = 3d. No book leg in the presample replica (dip-only).
Ledger REUSED read-only from oc_presampletilt/tmp (ledger_presample.npz +
bt_presample.npy; reproduction gate: n == 9731, per-leg 909/2986/3115/2721, base
4-phase-mean sums == (2.313362, 2.678870, 0.577643, 0.297538) +- 1e-6).

Per year y: base(y), boosted(y), realised_mean(y), norm(y) = boosted(y)/realised_mean,
gain(y) = norm(y) - base(y). Timing/block placebo (1000 perms, seeds 20261007+y /
20261008+y with y = 0..3, percentile = 100*(1+#{perm<=actual})/1001, signif iff >= 95)
as supporting evidence. Placebo null (pre-registered): time-bar permutation
WITHIN (year, shift) — preserves per-shift boosted counts and the market-wide
cross-sym sharing; block-42 chronological within (year, shift). CPU-only (numpy).
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
from cboostpre_rule import BOOST  # noqa: E402 (assert the frozen boost)

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
VARIANTS = ("B7", "B3")
MULT_COL = {"B7": "mult_B7", "B3": "mult_B3"}
HB_S = 600


def phase_mean_sums(ph, yr, wv, yv, n_years=4):
    out = []
    for y in range(n_years):
        ss = []
        for p in PHASES:
            m = (ph == p) & (yr == y)
            ss.append(float((wv[m] * yv[m]).sum()) if m.any() else 0.0)
        out.append(float(np.mean(ss)))
    return out


def load_mult():
    d = pd.read_parquet(HERE / "boost_mult_presample.parquet")
    d["T"] = pd.to_datetime(d["T"], utc=True)
    exact = {}
    per_shift = {}
    for s in SHIFTS:
        sub = d[d["shift"] == s].sort_values("T")
        t_ns = sub["T"].values.astype("datetime64[ns]").astype(np.int64)
        per_shift[s] = {c: sub[c].to_numpy(dtype=float) for c in
                        ("mult_B7", "mult_B3")}
        per_shift[s]["t_ns"] = t_ns
        per_shift[s]["T"] = pd.to_datetime(sub["T"], utc=True).tolist()
        for t, a, e in zip(per_shift[s]["T"], per_shift[s]["mult_B7"],
                           per_shift[s]["mult_B3"]):
            exact[(int(s), pd.Timestamp(t))] = (float(a), float(e))
    return exact, per_shift


def mult_at(shift, t, variant, exact, per_shift):
    key = (int(shift), pd.Timestamp(t))
    hit = exact.get(key)
    if hit is not None:
        return hit[0] if variant == "B7" else hit[1]
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
    assert BOOST == 1.5
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

    exact, per_shift = load_mult()

    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)

    base_y = phase_mean_sums(ph, yr, w, yv)
    print(f"base 4-phase-mean sums={[round(v, 6) for v in base_y]}", flush=True)
    for y in range(4):
        assert abs(base_y[y] - BASE_GATE[y]) <= 1e-6, \
            f"base {LEG_ORDER[y]} {base_y[y]} != {BASE_GATE[y]}"

    res = {
        "config": {
            "ledger": "oc_presampletilt/tmp/ledger_presample.npz + bt_presample.npy read-only (D0+B1, no budget/cap; SPOT fills/exits)",
            "boost": "boost_mult_presample.parquet (closes-only >4sg triggers on pre-sample closes, union over available majors per shift; 1.5 in (tc, tc+Nd])",
            "seed_timing": SEED_TIMING,
            "seed_block": SEED_BLOCK,
            "n_perm": N_PERM,
            "block": BLOCK,
            "rule": "mult 1.5 if boosted else 1.0, market-wide per shift (B7 N=7d, B3 N=3d); no book leg",
            "normalisation": "norm(y)=boosted(y)/realised_mean(y); gain(y)=norm(y)-base(y); perm norms use the ACTUAL denominator",
            "percentile": "100*(1+#{perm<=actual})/1001; significant iff >=95",
            "placebo_null": "time-bar permutation WITHIN (year, shift) (1000 uniform; block-42 chronological within (year, shift))",
            "diagnostic": "no gate, no selection, no engine (unseen-years diagnostic only)",
        },
        "reproduction": {"per_leg_gate": list(PER_LEG_GATE),
                         "base_sums": [round(v, 6) for v in base_y],
                         "n_fills": int(n)},
    }

    for variant in VARIANTS:
        mult = np.array([mult_at(int(ph[i]), bt_all[i], variant, exact, per_shift)
                         for i in range(n)], dtype=float)
        vals = sorted(set(np.round(mult, 6)))
        assert set(vals) <= {1.0, 1.5}, vals
        nmiss = 0  # exact-match misses fall back to ffill; count non-exact joins
        print(f"{variant}: join n={n} boosted_share={float((mult == 1.5).mean()):.4f} "
              f"mult values={vals}", flush=True)

        boost_y = phase_mean_sums(ph, yr, w * mult, yv)
        years = []
        for y in range(4):
            m = yr == y
            rm = float(mult[m].mean()) if m.any() else 1.0
            norm = float(boost_y[y]) / rm if rm else 0.0
            years.append({"year": LEG_ORDER[y],
                          "n_fills": int(m.sum()),
                          "base": round(float(base_y[y]), 6),
                          "boosted": round(float(boost_y[y]), 6),
                          "realised_mean": round(rm, 6),
                          "norm": round(norm, 6),
                          "gain": round(norm - float(base_y[y]), 6),
                          "boosted_share_fills": round(float((mult[m] == 1.5).mean()), 4)
                          if m.any() else None})
        for r in years:
            print(f"  {r['year']} n={r['n_fills']} base={r['base']} "
                  f"boosted={r['boosted']} rm={r['realised_mean']} "
                  f"norm={r['norm']} gain={r['gain']} boosted={r['boosted_share_fills']}",
                  flush=True)

        # ---- time-bar universes per (year, shift) ----
        uni = {}   # (y, s) -> mult array (chronological)
        for y in range(4):
            lo, hi = LEG_BOUNDS[LEG_ORDER[y]]
            for s in SHIFTS:
                t_ns = per_shift[s]["t_ns"]
                col = per_shift[s][MULT_COL[variant]]
                lo_ns, hi_ns = np.int64(lo.value), np.int64(hi.value)
                m = (t_ns >= lo_ns) & (t_ns < hi_ns)
                uni[(y, s)] = col[m].astype(float)
        print(f"bar universes (y,s) sizes: {[len(uni[(y, s)]) for y in range(4) for s in SHIFTS][:8]}...",
              flush=True)

        # fill -> position in its (y, s) universe
        pos_of = {}
        for (y, s), arr in uni.items():
            t_ns = per_shift[s]["t_ns"]
            lo, hi = LEG_BOUNDS[LEG_ORDER[y]]
            m = (t_ns >= np.int64(lo.value)) & (t_ns < np.int64(hi.value))
            idx = {int(tt): j for j, tt in enumerate(t_ns[m])}
            pos_of[(y, s)] = idx
        fill_pos = np.full(n, -1, dtype=np.int64)
        for i in range(n):
            q = pd.Timestamp(bt_all[i])
            if q.tzinfo is None:
                q = q.tz_localize("UTC")
            fill_pos[i] = pos_of[(int(yr[i]), int(ph[i]))].get(int(q.value), -1)
        nmiss_fill = int((fill_pos < 0).sum())
        print(f"{variant}: fills w/o time-bar: {nmiss_fill}", flush=True)
        assert (fill_pos >= 0).all(), f"{nmiss_fill} fills w/o time-bar"

        timing = []
        for y in range(4):
            rng = np.random.default_rng(SEED_TIMING + y)
            my = (yr == y)
            fm_actual = mult[my]
            actual = float(boost_y[y]) / float(fm_actual.mean())
            fill_w = w[my]
            fill_y = yv[my]
            fill_ph = ph[my]
            fill_p = fill_pos[my]
            slices = {}
            for s in SHIFTS:
                sm = fill_ph == s
                slices[s] = (np.where(sm)[0], uni[(y, s)])
            denom_y = float(fm_actual.mean())
            perms = np.empty(N_PERM)
            for k in range(N_PERM):
                fm = np.empty(my.sum())
                for s in SHIFTS:
                    loc, arr = slices[s]
                    pm = rng.permutation(arr)
                    upos = fill_p[loc]
                    fm[loc] = pm[upos]
                s_sum = 0.0
                for p in PHASES:
                    mp = fill_ph == p
                    s_sum += float((fill_w[mp] * fm[mp] * fill_y[mp]).sum())
                perms[k] = (s_sum / 4.0) / denom_y
                if time.time() - last_hb > HB_S:
                    print(f"[hb] timing {variant} y={y} perm {k}/{N_PERM} "
                          f"elapsed={time.time() - t0:.0f}s", flush=True)
                    last_hb = time.time()
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            timing.append({"year": LEG_ORDER[y],
                           "actual_norm": round(actual, 6),
                           "p5": round(float(np.quantile(perms, 0.05)), 6),
                           "p50": round(float(np.quantile(perms, 0.50)), 6),
                           "p95": round(float(np.quantile(perms, 0.95)), 6),
                           "percentile": round(float(pct), 2)})
            print(f"timing {variant} y={y} actual={actual:.6f} "
                  f"p5={np.quantile(perms, 0.05):.6f} p50={np.quantile(perms, 0.50):.6f} "
                  f"p95={np.quantile(perms, 0.95):.6f} pct={pct:.2f}", flush=True)

        block = []
        for y in range(4):
            rng = np.random.default_rng(SEED_BLOCK + y)
            my = (yr == y)
            fm_actual = mult[my]
            actual = float(boost_y[y]) / float(fm_actual.mean())
            fill_w = w[my]
            fill_y = yv[my]
            fill_ph = ph[my]
            fill_p = fill_pos[my]
            denom_y = float(fm_actual.mean())
            blk_of = {}
            for s in SHIFTS:
                arr = uni[(y, s)]
                blks = [arr[b:b + BLOCK] for b in range(0, len(arr), BLOCK)]
                blk_of[s] = blks
            perms = np.empty(N_PERM)
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
                if time.time() - last_hb > HB_S:
                    print(f"[hb] block {variant} y={y} perm {k}/{N_PERM} "
                          f"elapsed={time.time() - t0:.0f}s", flush=True)
                    last_hb = time.time()
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            block.append({"year": LEG_ORDER[y],
                          "actual_norm": round(actual, 6),
                          "p5": round(float(np.quantile(perms, 0.05)), 6),
                          "p50": round(float(np.quantile(perms, 0.50)), 6),
                          "p95": round(float(np.quantile(perms, 0.95)), 6),
                          "percentile": round(float(pct), 2)})
            print(f"block {variant} y={y} actual={actual:.6f} "
                  f"p5={np.quantile(perms, 0.05):.6f} p50={np.quantile(perms, 0.50):.6f} "
                  f"p95={np.quantile(perms, 0.95):.6f} pct={pct:.2f}", flush=True)

        res[variant] = {"per_year": years, "timing_placebo": timing,
                        "block_placebo": block}

    (HERE / "tmp").mkdir(exist_ok=True)
    (HERE / "tmp/boost_presample.json").write_text(json.dumps(res, indent=1))
    print("wrote tmp/boost_presample.json", flush=True)


if __name__ == "__main__":
    main()
