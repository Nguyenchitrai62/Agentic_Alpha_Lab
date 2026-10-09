"""oc_b7deep SECONDARY: deep-rung-only boost on the 2021-2026 ledger.

CONTAMINATED leg (info only, never a selection basis): same window-rebuild +
rung-gate method as the primary, with V1 (ri>=2, 3.5sg) / V2 (ri>=3, 4.0sg)
deep mults and the B7 reference read-only from
oc_cascadeboost/boost_mult_4shift.parquet.
Ledger REUSED read-only from oc_k2placebo/tmp (ledger.npz + bt_all.npy;
reproduction gate: n == 22312 and base 4-phase-mean sum5y == 7.718304 +- 0.002).

Per year y: base(y), boosted_V(y), realised_mean_V(y), norm_V(y),
gain_vs_base, gain_vs_B7. Timing/block placebo (1000 perms, seeds
20261007+y / 20261008+y, y = 0..4). Placebo null: B7 window-flag permutation
WITHIN (year, shift), frozen rung gate re-applied. CPU-only (numpy).
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
CB = ROOT / "research/tournament/oc_cascadeboost"

sys.path.insert(0, str(HERE))
from b7deep_rule import BOOST, V1_RI_MIN, V2_RI_MIN  # noqa: E402

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
ANCH = [pd.Timestamp(a, tz="UTC") for a in ANCH5]
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
SEED_TIMING = 20261007
SEED_BLOCK = 20261008
N_PERM = 1000
BLOCK = 42
BASE_GATE = 7.718304
N_GATE = 22312
PHASES = (0, 1, 2, 3)
SHIFTS = (0, 1, 2, 3)
VARIANTS = ("V1", "V2")
RI_MIN = {"V1": V1_RI_MIN, "V2": V2_RI_MIN}
HB_S = 600


def phase_mean_sums(ph, yr, wv, yv):
    out = []
    for y in range(5):
        ss = []
        for p in PHASES:
            m = (ph == p) & (yr == y)
            ss.append(float((wv[m] * yv[m]).sum()) if m.any() else 0.0)
        out.append(float(np.mean(ss)))
    return out


def load_flags(path):
    d = pd.read_parquet(path)
    d["T"] = pd.to_datetime(d["T"], utc=True)
    exact = {}
    per_shift = {}
    for s in SHIFTS:
        sub = d[d["shift"] == s].sort_values("T")
        t_ns = sub["T"].values.astype("datetime64[ns]").astype(np.int64)
        flag = (sub["mult_B7"].to_numpy(dtype=float) == 1.5)
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
    led = dict(np.load(K2P / "tmp/ledger.npz"))
    for k in ("phase", "coin", "year", "bar_time", "rung"):
        led[k] = led[k].astype(np.int64)
    for k in ("w", "y10"):
        led[k] = led[k].astype(np.float64)
    bt_all = np.load(K2P / "tmp/bt_all.npy", allow_pickle=True)
    n = len(led["w"])
    print(f"loaded ledger n={n}", flush=True)
    assert n == N_GATE, f"ledger size {n} != {N_GATE}"
    assert set(np.unique(led["rung"])) <= {0, 1, 2, 3, 4}

    exact_d, per_shift_d = load_flags(HERE / "boost_mult_4shift_deep.parquet")
    exact_b, per_shift_b = load_flags(CB / "boost_mult_4shift.parquet")
    nd = pd.read_parquet(HERE / "boost_mult_4shift_deep.parquet")
    nb = pd.read_parquet(CB / "boost_mult_4shift.parquet")
    m = nd.merge(nb, on=["shift", "T"], suffixes=("", "_frozen"))
    assert len(m) == len(nd) == len(nb), (len(m), len(nd), len(nb))
    assert (m["mult_B7"] == m["mult_B7_frozen"]).all(), "rebuilt B7 != frozen B7"
    print(f"B7 rebuild equality OK rows={len(m)}", flush=True)

    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    ri = led["rung"].astype(int)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)

    base_y = phase_mean_sums(ph, yr, w, yv)
    got5 = float(sum(base_y))
    print(f"base 4-phase-mean sums={[round(v, 6) for v in base_y]} sum5y={got5:.6f}",
          flush=True)
    assert abs(got5 - BASE_GATE) <= 0.002, f"base {got5} != {BASE_GATE}"

    b7flag = np.array([flag_at(int(ph[i]), bt_all[i], exact_b, per_shift_b)
                       for i in range(n)], dtype=bool)
    mult_b7 = np.where(b7flag, 1.5, 1.0)
    boost_b7_y = phase_mean_sums(ph, yr, w * mult_b7, yv)
    rm_b7 = np.array([float(mult_b7[yr == y].mean()) for y in range(5)])
    norm_b7 = np.array([boost_b7_y[y] / rm_b7[y] for y in range(5)])

    res = {
        "config": {
            "ledger": "oc_k2placebo/tmp/ledger.npz + bt_all.npy read-only",
            "boost": "boost_mult_4shift_deep.parquet B7 window (verbatim) x frozen rung gate (V1 ri>=2, V2 ri>=3)",
            "b7ref": "oc_cascadeboost/boost_mult_4shift.parquet mult_B7 read-only (rebuild equality asserted)",
            "seed_timing": SEED_TIMING,
            "seed_block": SEED_BLOCK,
            "n_perm": N_PERM,
            "block": BLOCK,
            "contamination": "SECONDARY contaminated leg: idea derived from cascade results covering these years; info only, never a selection basis",
        },
        "reproduction": {"base_sum5y_gate": BASE_GATE,
                         "base_sums": [round(v, 6) for v in base_y],
                         "base_sum5y": round(got5, 6), "n_fills": int(n),
                         "b7_norms": [round(v, 6) for v in norm_b7]},
    }

    for variant in VARIANTS:
        is_deep = ri >= RI_MIN[variant]
        mult = np.where(b7flag & is_deep, 1.5, 1.0)
        vals = sorted(set(np.round(mult, 6)))
        assert set(vals) <= {1.0, 1.5}, vals
        print(f"{variant}: join n={n} deep_share={float(is_deep.mean()):.4f} "
              f"deepboost_share={float((mult == 1.5).mean()):.4f} mult values={vals}",
              flush=True)

        boost_y = phase_mean_sums(ph, yr, w * mult, yv)
        dsum_base = float(sum(boost_y) - sum(base_y))
        dsum_b7 = float(sum(boost_y) - sum(boost_b7_y))
        years = []
        for y in range(5):
            msk = yr == y
            rm = float(mult[msk].mean()) if msk.any() else 1.0
            norm = float(boost_y[y]) / rm if rm else 0.0
            years.append({"year": ANCH[y].date().isoformat(),
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
            print(f"  {r['year']} base={r['base']} boosted={r['boosted']} "
                  f"norm={r['norm']} gBase={r['gain_vs_base']} gB7={r['gain_vs_B7']}",
                  flush=True)

        uni = {}
        for y in range(5):
            lo = ANCH[y]
            hi = ANCH[y + 1] if y < 4 else YEAR_END
            for s in SHIFTS:
                t_ns = per_shift_d[s]["t_ns"]
                col = per_shift_d[s]["flag"].astype(float)
                lo_ns, hi_ns = np.int64(lo.value), np.int64(hi.value)
                msk = (t_ns >= lo_ns) & (t_ns < hi_ns)
                uni[(y, s)] = col[msk].astype(float)

        pos_of = {}
        for (y, s), arr in uni.items():
            t_ns = per_shift_d[s]["t_ns"]
            lo = ANCH[y]
            hi = ANCH[y + 1] if y < 4 else YEAR_END
            msk = (t_ns >= np.int64(lo.value)) & (t_ns < np.int64(hi.value))
            idx = {int(tt): j for j, tt in enumerate(t_ns[msk])}
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
            timing.append({"year": ANCH[y].date().isoformat(),
                           "actual_norm": round(actual, 6),
                           "percentile": round(float(pct), 2)})
            print(f"timing {variant} y={y} pct={pct:.2f}", flush=True)

        block = []
        for y in range(5):
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
            block.append({"year": ANCH[y].date().isoformat(),
                          "actual_norm": round(actual, 6),
                          "percentile": round(float(pct), 2)})
            print(f"block {variant} y={y} pct={pct:.2f}", flush=True)

        norms = np.array([r["norm"] for r in years])
        dev4_f = float(norms[:4].sum())
        dev4_b7 = float(norm_b7[:4].sum())
        res[variant] = {"per_year": years, "timing_placebo": timing,
                        "block_placebo": block,
                        "dSum5y_vs_base": round(dsum_base, 6),
                        "dSum5y_vs_B7": round(dsum_b7, 6),
                        "dev4_sum_vs_B7": round(dev4_f - dev4_b7, 6)}

    (HERE / "tmp").mkdir(exist_ok=True)
    (HERE / "tmp/replica_deep.json").write_text(json.dumps(res, indent=1))
    print("wrote tmp/replica_deep.json", flush=True)


if __name__ == "__main__":
    main()
