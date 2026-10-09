"""oc_b7taper PRIMARY: tapered boost on the pre-sample ledger.

Method inherited verbatim from oc_cboostpre/compute_boost_presample.py and
oc_b7first/compute_boost_presample_first.py, with V1/V2 taper mults from
boost_mult_presample_taper.parquet (frozen step/exp decay in the 7d window
after ANY union trigger; market-wide per shift) and the B7 reference mults
read-only from oc_cboostpre/boost_mult_presample.parquet (same join).
Ledger REUSED read-only from oc_presampletilt/tmp (ledger_presample.npz +
bt_presample.npy; reproduction gate: n == 9731, per-leg 909/2986/3115/2721,
base 4-phase-mean sums == (2.313362, 2.678870, 0.577643, 0.297538) +- 1e-6).

Per year y: base(y), boosted_V(y), realised_mean_V(y), norm_V(y),
gain_vs_base(y) = norm_V - base, gain_vs_B7(y) = norm_V - norm_B7.
Timing/block placebo (1000 perms, seeds 20261007+y / 20261008+y with y = 0..3,
percentile = 100*(1+#{perm<=actual})/1001, signif iff >= 95) with the
time-bar-within-(year,shift) null. Stop split from read-only
oc_cboostpre/tmp/stop_kinds.npz (no 1m work). CPU-only (numpy).
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
CBP = ROOT / "research/tournament/oc_cboostpre"

sys.path.insert(0, str(HERE))
from taper_rule import BOOST_DAYS  # noqa: E402 (assert the frozen window)

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
KIND_STOP = (0, 2)  # backstop, stop codes in stop_kinds.npz
KIND_UNKNOWN = -1
BOOST_EPS = 1e-12
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


def load_mult(path, cols):
    d = pd.read_parquet(path)
    d["T"] = pd.to_datetime(d["T"], utc=True)
    exact = {}
    per_shift = {}
    for s in SHIFTS:
        sub = d[d["shift"] == s].sort_values("T")
        t_ns = sub["T"].values.astype("datetime64[ns]").astype(np.int64)
        per_shift[s] = {c: sub[c].to_numpy(dtype=float) for c in cols}
        per_shift[s]["t_ns"] = t_ns
        per_shift[s]["T"] = pd.to_datetime(sub["T"], utc=True).tolist()
        for row in zip(per_shift[s]["T"], *[per_shift[s][c] for c in cols]):
            exact[(int(s), pd.Timestamp(row[0]))] = tuple(float(v) for v in row[1:])
    return exact, per_shift


def mult_at(shift, t, icol, exact, per_shift, cols):
    key = (int(shift), pd.Timestamp(t))
    hit = exact.get(key)
    if hit is not None:
        return hit[icol]
    t_ns = per_shift[int(shift)]["t_ns"]
    q = pd.Timestamp(t)
    if q.tzinfo is None:
        q = q.tz_localize("UTC")
    pos = int(np.searchsorted(t_ns, np.int64(q.value), side="right")) - 1
    if pos < 0:
        return 1.0
    return float(per_shift[int(shift)][cols[icol]][pos])


def main() -> None:
    t0 = time.time()
    last_hb = t0
    assert BOOST_DAYS == 7
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

    exact_f, per_shift_f = load_mult(HERE / "boost_mult_presample_taper.parquet",
                                     ("mult_V1", "mult_V2"))
    exact_b, per_shift_b = load_mult(CBP / "boost_mult_presample.parquet",
                                     ("mult_B7", "mult_B3"))
    kinds = np.load(CBP / "tmp/stop_kinds.npz")["kind"].astype(np.int64)
    assert len(kinds) == n, (len(kinds), n)
    n_unknown = int((kinds == KIND_UNKNOWN).sum())
    print(f"reused stop kinds: unknown={n_unknown}", flush=True)

    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)

    base_y = phase_mean_sums(ph, yr, w, yv)
    print(f"base 4-phase-mean sums={[round(v, 6) for v in base_y]}", flush=True)
    for y in range(4):
        assert abs(base_y[y] - BASE_GATE[y]) <= 1e-6, \
            f"base {LEG_ORDER[y]} {base_y[y]} != {BASE_GATE[y]}"

    mult_b7 = np.array([mult_at(int(ph[i]), bt_all[i], 0, exact_b, per_shift_b,
                                ("mult_B7", "mult_B3")) for i in range(n)], dtype=float)
    assert set(np.round(mult_b7, 6)) <= {1.0, 1.5}
    boost_b7_y = phase_mean_sums(ph, yr, w * mult_b7, yv)
    rm_b7 = np.array([float(mult_b7[yr == y].mean()) for y in range(4)])
    norm_b7 = np.array([boost_b7_y[y] / rm_b7[y] for y in range(4)])
    print(f"B7 reference norms={[round(v, 6) for v in norm_b7]}", flush=True)

    res = {
        "config": {
            "ledger": "oc_presampletilt/tmp/ledger_presample.npz + bt_presample.npy read-only (D0+B1, no budget/cap; SPOT fills/exits)",
            "boost": "boost_mult_presample_taper.parquet (tapered: V1 step 1.6/1.3/1.0 by floor-day bin, V2 1+0.5*2^(-d/3), 7d after ANY union >4sg trigger; market-wide per shift)",
            "b7ref": "oc_cboostpre/boost_mult_presample.parquet mult_B7 read-only (same join)",
            "stops": "oc_cboostpre/tmp/stop_kinds.npz read-only (no new 1m work); boosted = mult > 1+1e-12",
            "seed_timing": SEED_TIMING,
            "seed_block": SEED_BLOCK,
            "n_perm": N_PERM,
            "block": BLOCK,
            "rule": "V1 step / V2 exp taper, else 1.0; B7 reference plain 1.5/7d",
            "normalisation": "norm(y)=boosted(y)/realised_mean(y); gain_vs_base=norm-base; gain_vs_B7=norm-norm_B7; perm norms use the ACTUAL denominator",
            "percentile": "100*(1+#{perm<=actual})/1001; significant iff >=95",
            "placebo_null": "time-bar permutation WITHIN (year, shift) (1000 uniform; block-42 chronological within (year, shift))",
            "beater": "sum4 norm_V > sum4 norm_B7 (strict) is the only gate to the engine",
            "contamination": "PRIMARY clean test: pre-sample years unseen when the cascade idea was formed; 2021-2026 is contaminated (secondary only)",
        },
        "reproduction": {"per_leg_gate": list(PER_LEG_GATE),
                         "base_sums": [round(v, 6) for v in base_y],
                         "n_fills": int(n),
                         "b7_norms": [round(v, 6) for v in norm_b7],
                         "b7_sum4_norm": round(float(norm_b7.sum()), 6),
                         "stop_unknown": int(n_unknown)},
    }

    for vi, variant in enumerate(VARIANTS):
        cols = ("mult_V1", "mult_V2")
        mult = np.array([mult_at(int(ph[i]), bt_all[i], vi, exact_f, per_shift_f, cols)
                         for i in range(n)], dtype=float)
        assert np.isfinite(mult).all()
        assert (mult >= 1.0 - 1e-9).all(), float(mult.min())
        assert (mult <= 1.6 + 1e-9).all(), float(mult.max())
        print(f"{variant}: join n={n} boosted_share={float((mult > 1.0 + BOOST_EPS).mean()):.4f} "
              f"mean={float(mult.mean()):.4f} max={float(mult.max()):.4f}", flush=True)

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
                          "gain_vs_base": round(norm - float(base_y[y]), 6),
                          "gain_vs_B7": round(norm - float(norm_b7[y]), 6),
                          "boosted_share_fills": round(float((mult[m] > 1.0 + BOOST_EPS).mean()), 4)
                          if m.any() else None})
        for r in years:
            print(f"  {r['year']} n={r['n_fills']} base={r['base']} "
                  f"boosted={r['boosted']} rm={r['realised_mean']} "
                  f"norm={r['norm']} gBase={r['gain_vs_base']} gB7={r['gain_vs_B7']} "
                  f"boosted={r['boosted_share_fills']}", flush=True)

        # ---- time-bar universes per (year, shift) ----
        uni = {}
        for y in range(4):
            lo, hi = LEG_BOUNDS[LEG_ORDER[y]]
            for s in SHIFTS:
                t_ns = per_shift_f[s]["t_ns"]
                col = per_shift_f[s][MULT_COL[variant]]
                lo_ns, hi_ns = np.int64(lo.value), np.int64(hi.value)
                m = (t_ns >= lo_ns) & (t_ns < hi_ns)
                uni[(y, s)] = col[m].astype(float)

        pos_of = {}
        for (y, s), arr in uni.items():
            t_ns = per_shift_f[s]["t_ns"]
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
            print(f"timing {variant} y={y} actual={actual:.6f} pct={pct:.2f}", flush=True)

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
            print(f"block {variant} y={y} actual={actual:.6f} pct={pct:.2f}", flush=True)

        # ---- stop split (reused kinds; known kinds only) ----
        known = kinds != KIND_UNKNOWN
        stop = np.isin(kinds, np.array(KIND_STOP))
        stops = []
        for y in range(4):
            idx_y = np.where(yr == y)[0]
            my_known = known[idx_y]
            row = {"year": LEG_ORDER[y],
                   "base_stop_rate": round(float(stop[idx_y[my_known]].mean()), 4)
                   if my_known.any() else None}
            is_b = mult[idx_y] > 1.0 + BOOST_EPS
            kb = my_known & is_b
            row["boosted_share"] = round(float(is_b.mean()), 4)
            if kb.any():
                row["boosted_stop_rate"] = round(float(stop[idx_y[kb]].mean()), 4)
                row["stop_delta"] = round(float(stop[idx_y[kb]].mean())
                                          - float(stop[idx_y[my_known]].mean()), 4)
            else:
                row["boosted_stop_rate"] = None
                row["stop_delta"] = None
            stops.append(row)
            print(f"stop {variant} {row}", flush=True)
        is_b_all = (mult > 1.0 + BOOST_EPS) & known
        pooled = {"boosted_share": round(float((mult > 1.0 + BOOST_EPS).mean()), 4),
                  "base_stop_rate": round(float(stop[known].mean()), 4),
                  "boosted_stop_rate": round(float(stop[is_b_all].mean()), 4)
                  if is_b_all.any() else None,
                  "stop_delta": round(float(stop[is_b_all].mean())
                                      - float(stop[known].mean()), 4)
                  if is_b_all.any() else None}
        print(f"stop {variant} pooled {pooled}", flush=True)

        norms = np.array([r["norm"] for r in years])
        res[variant] = {"per_year": years, "timing_placebo": timing,
                        "block_placebo": block, "stops": stops,
                        "pooled_stop": pooled,
                        "sum4_norm": round(float(norms.sum()), 6),
                        "sum4_gain_vs_base": round(float((norms - np.array(base_y)).sum()), 6),
                        "sum4_gain_vs_B7": round(float((norms - norm_b7).sum()), 6),
                        "beats_B7": bool(float(norms.sum()) > float(norm_b7.sum()))}

    (HERE / "tmp").mkdir(exist_ok=True)
    (HERE / "tmp/taper_presample.json").write_text(json.dumps(res, indent=1))
    print("wrote tmp/taper_presample.json", flush=True)
    for variant in VARIANTS:
        r = res[variant]
        print(f"{variant}: sum4_norm={r['sum4_norm']} vs B7 {res['reproduction']['b7_sum4_norm']} "
              f"gain_vs_B7={r['sum4_gain_vs_B7']} beats_B7={r['beats_B7']}", flush=True)


if __name__ == "__main__":
    main()
