"""oc_b7deep PRIMARY: deep-rung-only boost on the pre-sample ledger.

Method inherited verbatim from oc_cboostpre/compute_boost_presample.py, with
the deep gate: per fill, mult_V = 1.5 iff (B7 window active at (shift,T) AND
rung ri >= cutoff) else 1.0 (V1 ri>=2 i.e. 3.5sg; V2 ri>=3 i.e. 4.0sg).
B7 window flags rebuilt here (boost_mult_presample_deep.parquet) and checked
equal to the frozen oc_cboostpre B7 flags; the B7 reference norms use the
FROZEN cboostpre mults (same join).
Ledger REUSED read-only from oc_presampletilt/tmp (ledger_presample.npz +
bt_presample.npy; reproduction gate: n == 9731, per-leg 909/2986/3115/2721,
base 4-phase-mean sums == (2.313362, 2.678870, 0.577643, 0.297538) +- 1e-6).

Per year y: base(y), boosted_V(y), realised_mean_V(y), norm_V(y),
gain_vs_base(y) = norm_V - base, gain_vs_B7(y) = norm_V - norm_B7.
Timing/block placebo (1000 perms, seeds 20261007+y / 20261008+y with y = 0..3,
percentile = 100*(1+#{perm<=actual})/1001, signif iff >= 95) with the
window-flag-within-(year,shift) null + frozen rung gate re-applied.
Stop split from read-only oc_cboostpre/tmp/stop_kinds.npz (no 1m work).
CPU-only (numpy).
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
from b7deep_rule import BOOST, V1_RI_MIN, V2_RI_MIN  # noqa: E402

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
RI_MIN = {"V1": V1_RI_MIN, "V2": V2_RI_MIN}
X_SG = {"V1": 3.5, "V2": 4.0}
KIND_STOP = (0, 2)  # backstop, stop codes in stop_kinds.npz
KIND_UNKNOWN = -1
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


def load_flags(path):
    """Load B7 window flags per shift: exact dict + per-shift arrays."""
    d = pd.read_parquet(path)
    d["T"] = pd.to_datetime(d["T"], utc=True)
    exact = {}
    per_shift = {}
    for s in SHIFTS:
        sub = d[d["shift"] == s].sort_values("T")
        t_ns = sub["T"].values.astype("datetime64[ns]").astype(np.int64)
        flag = (sub["mult_B7"].to_numpy(dtype=float) == 1.5)
        if "boosted_B7" in sub.columns:
            flag2 = sub["boosted_B7"].to_numpy(dtype=bool)
            assert (flag == flag2).all(), f"shift {s} boosted_B7 != mult_B7==1.5"
        per_shift[s] = {"t_ns": t_ns,
                        "flag": flag.astype(bool),
                        "T": pd.to_datetime(sub["T"], utc=True).tolist()}
        for T, f in zip(per_shift[s]["T"], flag):
            exact[(int(s), pd.Timestamp(T))] = bool(f)
    return exact, per_shift


def flag_at(shift, t, exact, per_shift):
    key = (int(shift), pd.Timestamp(t))
    hit = exact.get(key)
    if hit is not None:
        return hit
    t_ns = per_shift[int(shift)]["t_ns"]
    q = pd.Timestamp(t)
    if q.tzinfo is None:
        q = q.tz_localize("UTC")
    pos = int(np.searchsorted(t_ns, np.int64(q.value), side="right")) - 1
    if pos < 0:
        return False
    return bool(per_shift[int(shift)]["flag"][pos])


def main() -> None:
    t0 = time.time()
    last_hb = t0
    assert BOOST == 1.5 and V1_RI_MIN == 2 and V2_RI_MIN == 3
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
    assert set(np.unique(led["rung"])) <= {0, 1, 2, 3, 4}

    exact_d, per_shift_d = load_flags(HERE / "boost_mult_presample_deep.parquet")
    exact_b, per_shift_b = load_flags(CBP / "boost_mult_presample.parquet")
    # Rebuild equality check: our B7 flags must match frozen cboostpre B7 flags.
    nd = pd.read_parquet(HERE / "boost_mult_presample_deep.parquet")
    nb = pd.read_parquet(CBP / "boost_mult_presample.parquet")
    m = nd.merge(nb, on=["shift", "T"], suffixes=("", "_frozen"))
    assert len(m) == len(nd) == len(nb), (len(m), len(nd), len(nb))
    assert (m["mult_B7"] == m["mult_B7_frozen"]).all(), "rebuilt B7 != frozen B7"
    print(f"B7 rebuild equality OK rows={len(m)}", flush=True)
    kinds = np.load(CBP / "tmp/stop_kinds.npz")["kind"].astype(np.int64)
    assert len(kinds) == n, (len(kinds), n)
    n_unknown = int((kinds == KIND_UNKNOWN).sum())
    print(f"reused stop kinds: unknown={n_unknown}", flush=True)

    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    ri = led["rung"].astype(int)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)

    base_y = phase_mean_sums(ph, yr, w, yv)
    print(f"base 4-phase-mean sums={[round(v, 6) for v in base_y]}", flush=True)
    for y in range(4):
        assert abs(base_y[y] - BASE_GATE[y]) <= 1e-6, \
            f"base {LEG_ORDER[y]} {base_y[y]} != {BASE_GATE[y]}"

    b7flag = np.array([flag_at(int(ph[i]), bt_all[i], exact_b, per_shift_b)
                       for i in range(n)], dtype=bool)
    mult_b7 = np.where(b7flag, 1.5, 1.0)
    boost_b7_y = phase_mean_sums(ph, yr, w * mult_b7, yv)
    rm_b7 = np.array([float(mult_b7[yr == y].mean()) for y in range(4)])
    norm_b7 = np.array([boost_b7_y[y] / rm_b7[y] for y in range(4)])
    print(f"B7 reference norms={[round(v, 6) for v in norm_b7]}", flush=True)
    # Cross-check vs frozen oc_cboostpre B7 norms.
    ref = json.loads((CBP / "results.json").read_text())
    if "B7" in ref and "per_year" in ref["B7"]:
        for y in range(4):
            assert abs(norm_b7[y] - ref["B7"]["per_year"][y]["norm"]) < 5e-6, y
        print("B7 norms match frozen oc_cboostpre results.json", flush=True)

    deep_flag = {v: (ri >= RI_MIN[v]) for v in VARIANTS}

    res = {
        "config": {
            "ledger": "oc_presampletilt/tmp/ledger_presample.npz + bt_presample.npy read-only (D0+B1, no budget/cap; SPOT fills/exits)",
            "boost": "boost_mult_presample_deep.parquet B7 window (verbatim >4sg 7d, market-wide per shift) x frozen rung gate (V1 ri>=2 i.e. 3.5sg, V2 ri>=3 i.e. 4.0sg); shallow rungs stay 1.0, no veto",
            "b7ref": "oc_cboostpre/boost_mult_presample.parquet mult_B7 read-only (same join; rebuild equality asserted)",
            "stops": "oc_cboostpre/tmp/stop_kinds.npz read-only (no new 1m work)",
            "seed_timing": SEED_TIMING,
            "seed_block": SEED_BLOCK,
            "n_perm": N_PERM,
            "block": BLOCK,
            "rule": "mult_V = 1.5 iff (B7 window AND ri>=cutoff) else 1.0",
            "normalisation": "norm(y)=boosted(y)/realised_mean(y); gain_vs_base=norm-base; gain_vs_B7=norm-norm_B7; perm norms use the ACTUAL denominator",
            "percentile": "100*(1+#{perm<=actual})/1001; significant iff >=95",
            "placebo_null": "B7 window-flag permutation WITHIN (year, shift) (1000 uniform; block-42 chronological within (year, shift)), frozen rung gate re-applied after permutation",
            "beater": "sum4 norm_V > sum4 norm_B7 (strict) is the only gate to the engine",
            "contamination": "PRIMARY clean test: pre-sample years unseen when the cascade idea was formed; 2021-2026 is contaminated (secondary only)",
        },
        "reproduction": {"per_leg_gate": list(PER_LEG_GATE),
                         "base_sums": [round(v, 6) for v in base_y],
                         "n_fills": int(n),
                         "b7_norms": [round(v, 6) for v in norm_b7],
                         "b7_sum4_norm": round(float(norm_b7.sum()), 6),
                         "stop_unknown": int(n_unknown),
                         "deep_rung_mix": {v: round(float(deep_flag[v].mean()), 4)
                                           for v in VARIANTS}},
    }

    for variant in VARIANTS:
        is_deep = deep_flag[variant]
        mult = np.where(b7flag & is_deep, 1.5, 1.0)
        vals = sorted(set(np.round(mult, 6)))
        assert set(vals) <= {1.0, 1.5}, vals
        print(f"{variant} (X={X_SG[variant]}sg, ri>={RI_MIN[variant]}): join n={n} "
              f"deep_share={float(is_deep.mean()):.4f} "
              f"deepboost_share={float((mult == 1.5).mean()):.4f} mult values={vals}",
              flush=True)

        boost_y = phase_mean_sums(ph, yr, w * mult, yv)
        years = []
        for y in range(4):
            msk = yr == y
            rm = float(mult[msk].mean()) if msk.any() else 1.0
            norm = float(boost_y[y]) / rm if rm else 0.0
            years.append({"year": LEG_ORDER[y],
                          "n_fills": int(msk.sum()),
                          "base": round(float(base_y[y]), 6),
                          "boosted": round(float(boost_y[y]), 6),
                          "realised_mean": round(rm, 6),
                          "norm": round(norm, 6),
                          "gain_vs_base": round(norm - float(base_y[y]), 6),
                          "gain_vs_B7": round(norm - float(norm_b7[y]), 6),
                          "boosted_share_fills": round(float((mult[msk] == 1.5).mean()), 4)
                          if msk.any() else None})
        for r in years:
            print(f"  {r['year']} n={r['n_fills']} base={r['base']} "
                  f"boosted={r['boosted']} rm={r['realised_mean']} "
                  f"norm={r['norm']} gBase={r['gain_vs_base']} gB7={r['gain_vs_B7']} "
                  f"boosted={r['boosted_share_fills']}", flush=True)

        # ---- B7-flag time-bar universes per (year, shift) ----
        uni = {}
        for y in range(4):
            lo, hi = LEG_BOUNDS[LEG_ORDER[y]]
            for s in SHIFTS:
                t_ns = per_shift_d[s]["t_ns"]
                col = per_shift_d[s]["flag"].astype(float)
                lo_ns, hi_ns = np.int64(lo.value), np.int64(hi.value)
                msk = (t_ns >= lo_ns) & (t_ns < hi_ns)
                uni[(y, s)] = col[msk].astype(float)

        pos_of = {}
        for (y, s), arr in uni.items():
            t_ns = per_shift_d[s]["t_ns"]
            lo, hi = LEG_BOUNDS[LEG_ORDER[y]]
            msk = (t_ns >= np.int64(lo.value)) & (t_ns < np.int64(hi.value))
            idx = {int(tt): j for j, tt in enumerate(t_ns[msk])}
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
            fill_deep = is_deep[my]
            slices = {}
            for s in SHIFTS:
                sm = fill_ph == s
                slices[s] = (np.where(sm)[0], uni[(y, s)])
            denom_y = float(fm_actual.mean())
            perms = np.empty(N_PERM)
            for k in range(N_PERM):
                pflag = np.empty(my.sum(), dtype=bool)
                for s in SHIFTS:
                    loc, arr = slices[s]
                    pm = rng.permutation(arr).astype(bool)
                    upos = fill_p[loc]
                    pflag[loc] = pm[upos]
                fm = np.where(pflag & fill_deep, 1.5, 1.0)
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
            fill_deep = is_deep[my]
            denom_y = float(fm_actual.mean())
            blk_of = {}
            for s in SHIFTS:
                arr = uni[(y, s)]
                blks = [arr[b:b + BLOCK] for b in range(0, len(arr), BLOCK)]
                blk_of[s] = blks
            perms = np.empty(N_PERM)
            for k in range(N_PERM):
                pflag = np.empty(my.sum(), dtype=bool)
                for s in SHIFTS:
                    loc = np.where(fill_ph == s)[0]
                    blks = blk_of[s]
                    order = rng.permutation(len(blks))
                    seq = np.concatenate([blks[bb] for bb in order]).astype(bool) \
                        if blks else np.array([], dtype=bool)
                    upos = fill_p[loc]
                    pflag[loc] = seq[upos]
                fm = np.where(pflag & fill_deep, 1.5, 1.0)
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
            is_b = mult[idx_y] == 1.5
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
        is_b_all = (mult == 1.5) & known
        pooled = {"boosted_share": round(float((mult == 1.5).mean()), 4),
                  "base_stop_rate": round(float(stop[known].mean()), 4),
                  "boosted_stop_rate": round(float(stop[is_b_all].mean()), 4)
                  if is_b_all.any() else None,
                  "stop_delta": round(float(stop[is_b_all].mean())
                                      - float(stop[known].mean()), 4)
                  if is_b_all.any() else None}
        print(f"stop {variant} pooled {pooled}", flush=True)

        norms = np.array([r["norm"] for r in years])
        res[variant] = {"X_sg": X_SG[variant], "ri_min": RI_MIN[variant],
                        "per_year": years, "timing_placebo": timing,
                        "block_placebo": block, "stops": stops,
                        "pooled_stop": pooled,
                        "sum4_norm": round(float(norms.sum()), 6),
                        "sum4_gain_vs_base": round(float((norms - np.array(base_y)).sum()), 6),
                        "sum4_gain_vs_B7": round(float((norms - norm_b7).sum()), 6),
                        "beats_B7": bool(float(norms.sum()) > float(norm_b7.sum()))}

    # B7 reference stop row (plain window fills) for the REPORT side-by-side.
    known = kinds != KIND_UNKNOWN
    stop = np.isin(kinds, np.array(KIND_STOP))
    b7stops = []
    for y in range(4):
        idx_y = np.where(yr == y)[0]
        my_known = known[idx_y]
        is_b = mult_b7[idx_y] == 1.5
        kb = my_known & is_b
        b7stops.append({"year": LEG_ORDER[y],
                        "boosted_share": round(float(is_b.mean()), 4),
                        "boosted_stop_rate": round(float(stop[idx_y[kb]].mean()), 4)
                        if kb.any() else None,
                        "stop_delta": round(float(stop[idx_y[kb]].mean())
                                            - float(stop[idx_y[my_known]].mean()), 4)
                        if kb.any() else None})
    res["B7_stops"] = b7stops

    (HERE / "tmp").mkdir(exist_ok=True)
    (HERE / "tmp/boost_presample_deep.json").write_text(json.dumps(res, indent=1))
    print("wrote tmp/boost_presample_deep.json", flush=True)
    for variant in VARIANTS:
        r = res[variant]
        print(f"{variant}: sum4_norm={r['sum4_norm']} vs B7 {res['reproduction']['b7_sum4_norm']} "
              f"gain_vs_B7={r['sum4_gain_vs_B7']} beats_B7={r['beats_B7']}", flush=True)


if __name__ == "__main__":
    main()
