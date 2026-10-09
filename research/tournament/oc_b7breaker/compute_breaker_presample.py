"""oc_b7breaker PRIMARY: pre-sample replica + placebo for B7/V1/V2 (clean test).

Method inherited verbatim from oc_cboostpre/compute_boost_presample.py, applied to the
breaker grids (breaker_mult_presample.parquet):
  mult_B7 = 1.5 iff in B7 window else 1.0; mult_V = 1.0 if breaker active else mult_B7.
  V1 K=2/M=14; V2 K=3/M=21 (frozen). No book leg (dip-only).
Ledger REUSED read-only from oc_presampletilt/tmp (ledger_presample.npz +
bt_presample.npy; reproduction gate: n == 9731, per-leg 909/2986/3115/2721, base
4-phase-mean sums == (2.313362, 2.678870, 0.577643, 0.297538) +- 1e-6; B7 rows
reproduced vs oc_cboostpre/results.json gains).

Per year y: base(y), variant(y), realised_mean(y), norm(y) = variant(y)/realised_mean,
gain_vs_base(y) = norm(y)-base(y), delta_vs_B7(y) = norm(y)-norm_B7(y).
Beats-B7 rule (PLAN, binding): sum_4y delta_vs_B7 > 0 AND Y2020p delta_vs_B7 > 0.
Timing/block placebo (1000 perms, seeds 20261007+y / 20261008+y with y = 0..3,
percentile = 100*(1+#{perm<=actual})/1001, signif iff >= 95) as supporting evidence.
Placebo null: time-bar permutation WITHIN (year, shift); block-42 chronological within
(year, shift). CPU-only (numpy). Heartbeat every 600 s.
Output: tmp/breaker_presample.json.
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
from breaker_rule import BOOST, V1_K, V1_M, V2_K, V2_M  # noqa: E402

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
EXP_B7_GAIN = (0.045913, 0.078085, 0.111004, -0.069459)
PHASES = (0, 1, 2, 3)
SHIFTS = (0, 1, 2, 3)
VARIANTS = ("B7", "V1", "V2")
MULT_COL = {"B7": "mult_B7", "V1": "mult_V1", "V2": "mult_V2"}
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
    d = pd.read_parquet(HERE / "breaker_mult_presample.parquet")
    d["T"] = pd.to_datetime(d["T"], utc=True)
    exact = {}
    per_shift = {}
    for s in SHIFTS:
        sub = d[d["shift"] == s].sort_values("T")
        t_ns = sub["T"].values.astype("datetime64[ns]").astype(np.int64)
        per_shift[s] = {c: sub[c].to_numpy(dtype=float) for c in
                        ("mult_B7", "mult_V1", "mult_V2")}
        per_shift[s]["t_ns"] = t_ns
        per_shift[s]["T"] = pd.to_datetime(sub["T"], utc=True).tolist()
        for t, a, v1, v2 in zip(per_shift[s]["T"], per_shift[s]["mult_B7"],
                               per_shift[s]["mult_V1"], per_shift[s]["mult_V2"]):
            exact[(int(s), pd.Timestamp(t))] = (float(a), float(v1), float(v2))
    return exact, per_shift


def mult_at(shift, t, variant, exact, per_shift):
    key = (int(shift), pd.Timestamp(t))
    hit = exact.get(key)
    if hit is not None:
        return {"B7": hit[0], "V1": hit[1], "V2": hit[2]}[variant]
    col = MULT_COL[variant]
    t_ns = per_shift[int(shift)]["t_ns"]
    q = pd.Timestamp(t)
    if q.tzinfo is None:
        q = q.tz_localize("UTC")
    pos = int(np.searchsorted(t_ns, np.int64(q.value), side="right")) - 1
    if pos < 0:
        return 1.0
    return float(per_shift[int(shift)][col][pos])


def run_placebo(yr, ph, w, yv, fill_pos, mult, boost_y, uni, seed, block, t0, tag, variant):
    out = []
    global_last_hb = [t0]
    for y in range(4):
        rng = np.random.default_rng(seed + y)
        my = (yr == y)
        fm_actual = mult[my]
        actual = float(boost_y[y]) / float(fm_actual.mean())
        fill_w = w[my]
        fill_y = yv[my]
        fill_ph = ph[my]
        fill_p = fill_pos[my]
        denom_y = float(fm_actual.mean())
        if not block:
            slices = {}
            for s in SHIFTS:
                sm = fill_ph == s
                slices[s] = (np.where(sm)[0], uni[(y, s)])
        else:
            blk_of = {}
            for s in SHIFTS:
                arr = uni[(y, s)]
                blk_of[s] = [arr[bb:bb + BLOCK] for bb in range(0, len(arr), BLOCK)]
        perms = np.empty(N_PERM)
        for k in range(N_PERM):
            fm = np.empty(my.sum())
            for s in SHIFTS:
                loc = np.where(fill_ph == s)[0]
                if not block:
                    _loc, arr = slices[s]
                    pm = rng.permutation(arr)
                    fm[loc] = pm[fill_p[loc]]
                else:
                    blks = blk_of[s]
                    order = rng.permutation(len(blks))
                    seq = np.concatenate([blks[bb] for bb in order]) if blks else np.array([])
                    fm[loc] = seq[fill_p[loc]]
            s_sum = 0.0
            for p in PHASES:
                mp = fill_ph == p
                s_sum += float((fill_w[mp] * fm[mp] * fill_y[mp]).sum())
            perms[k] = (s_sum / 4.0) / denom_y
            if time.time() - global_last_hb[0] > HB_S:
                global_last_hb[0] = time.time()
                print(f"[hb] {tag} {variant} y={y} perm {k}/{N_PERM} "
                      f"elapsed={time.time() - t0:.0f}s", flush=True)
        pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
        out.append({"year": LEG_ORDER[y],
                    "actual_norm": round(actual, 6),
                    "p5": round(float(np.quantile(perms, 0.05)), 6),
                    "p50": round(float(np.quantile(perms, 0.50)), 6),
                    "p95": round(float(np.quantile(perms, 0.95)), 6),
                    "percentile": round(float(pct), 2)})
        print(f"{tag} {variant} y={y} actual={actual:.6f} "
              f"p5={np.quantile(perms, 0.05):.6f} p50={np.quantile(perms, 0.50):.6f} "
              f"p95={np.quantile(perms, 0.95):.6f} pct={pct:.2f}", flush=True)
    return out


def main() -> None:
    t0 = time.time()
    assert BOOST == 1.5 and (V1_K, V1_M) == (2, 14) and (V2_K, V2_M) == (3, 21)
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
            "grids": "breaker_mult_presample.parquet (closes-only >4sg triggers, union per shift; B7 1.5 in (tc,tc+7d]; V1/V2 1.0 if >=K in trailing M days else B7)",
            "variants": "B7 (reference, reproduced), V1 K=2/M=14, V2 K=3/M=21; no book leg",
            "seed_timing": SEED_TIMING, "seed_block": SEED_BLOCK,
            "n_perm": N_PERM, "block": BLOCK,
            "normalisation": "norm(y)=variant(y)/realised_mean(y); gain_vs_base(y)=norm(y)-base(y); delta_vs_B7(y)=norm(y)-norm_B7(y); perm norms use ACTUAL denominator",
            "percentile": "100*(1+#{perm<=actual})/1001; significant iff >=95",
            "placebo_null": "time-bar permutation WITHIN (year, shift) (1000 uniform; block-42 chronological within (year, shift))",
            "beats_B7": "sum_4y delta_vs_B7 > 0 AND Y2020p delta_vs_B7 > 0 (pre-registered, binding for engine gating)",
            "contamination": "pre-sample years unseen when the idea was formed: PRIMARY clean test; no selection on 2021-2026 here",
        },
        "reproduction": {"per_leg_gate": list(PER_LEG_GATE),
                         "base_sums": [round(v, 6) for v in base_y],
                         "n_fills": int(n)},
    }

    mults = {}
    boost_ys = {}
    for variant in VARIANTS:
        mult = np.array([mult_at(int(ph[i]), bt_all[i], variant, exact, per_shift)
                         for i in range(n)], dtype=float)
        vals = sorted(set(np.round(mult, 6)))
        assert set(vals) <= {1.0, 1.5}, vals
        mults[variant] = mult
        boost_y = phase_mean_sums(ph, yr, w * mult, yv)
        boost_ys[variant] = boost_y
        print(f"{variant}: boosted_share={float((mult == 1.5).mean()):.4f} mult values={vals}",
              flush=True)
    # B7 reproduction vs oc_cboostpre gains
    for y in range(4):
        m = yr == y
        rm = float(mults["B7"][m].mean())
        gain = float(boost_ys["B7"][y]) / rm - float(base_y[y])
        assert abs(gain - EXP_B7_GAIN[y]) <= 2e-6, f"B7 Y{LEG_ORDER[y]} gain {gain} != {EXP_B7_GAIN[y]}"
    print("B7 reproduction vs oc_cboostpre gains OK", flush=True)

    for variant in VARIANTS:
        mult = mults[variant]
        boost_y = boost_ys[variant]
        years = []
        for y in range(4):
            m = yr == y
            rm = float(mult[m].mean()) if m.any() else 1.0
            norm = float(boost_y[y]) / rm if rm else 0.0
            mB = yr == y
            rmB = float(mults["B7"][mB].mean())
            normB = float(boost_ys["B7"][y]) / rmB
            years.append({"year": LEG_ORDER[y],
                          "n_fills": int(m.sum()),
                          "base": round(float(base_y[y]), 6),
                          "variant": round(float(boost_y[y]), 6),
                          "realised_mean": round(rm, 6),
                          "norm": round(norm, 6),
                          "gain_vs_base": round(norm - float(base_y[y]), 6),
                          "delta_vs_B7": round(norm - normB, 6),
                          "boosted_share_fills": round(float((mult[m] == 1.5).mean()), 4)
                          if m.any() else None})
        for r in years:
            print(f"  {variant} {r['year']} n={r['n_fills']} base={r['base']} "
                  f"var={r['variant']} rm={r['realised_mean']} norm={r['norm']} "
                  f"gain={r['gain_vs_base']} dB7={r['delta_vs_B7']} "
                  f"boosted={r['boosted_share_fills']}", flush=True)

        uni = {}
        for y in range(4):
            lo, hi = LEG_BOUNDS[LEG_ORDER[y]]
            for s in SHIFTS:
                t_ns = per_shift[s]["t_ns"]
                col = per_shift[s][MULT_COL[variant]]
                lo_ns, hi_ns = np.int64(lo.value), np.int64(hi.value)
                m = (t_ns >= lo_ns) & (t_ns < hi_ns)
                uni[(y, s)] = col[m].astype(float)
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
        assert (fill_pos >= 0).all(), f"{int((fill_pos < 0).sum())} fills w/o time-bar"

        timing = run_placebo(yr, ph, w, yv, fill_pos, mult, boost_y, uni,
                             SEED_TIMING, False, t0, "timing", variant)
        block = run_placebo(yr, ph, w, yv, fill_pos, mult, boost_y, uni,
                            SEED_BLOCK, True, t0, "block", variant)
        res[variant] = {"per_year": years, "timing_placebo": timing,
                        "block_placebo": block}

    # beats-B7 summary (mechanical)
    beats = {}
    for variant in ("V1", "V2"):
        d = [r["delta_vs_B7"] for r in res[variant]["per_year"]]
        beats[variant] = {"sum_delta_vs_B7": round(float(sum(d)), 6),
                          "y2020p_delta_vs_B7": round(float(d[3]), 6),
                          "beats_B7": bool(sum(d) > 0 and d[3] > 0)}
        print(f"{variant} beats-B7: sum_delta={beats[variant]['sum_delta_vs_B7']} "
              f"y2020p={beats[variant]['y2020p_delta_vs_B7']} "
              f"beats={beats[variant]['beats_B7']}", flush=True)
    res["beats_B7"] = beats

    (HERE / "tmp").mkdir(exist_ok=True)
    (HERE / "tmp/breaker_presample.json").write_text(json.dumps(res, indent=1))
    print("wrote tmp/breaker_presample.json", flush=True)


if __name__ == "__main__":
    main()
