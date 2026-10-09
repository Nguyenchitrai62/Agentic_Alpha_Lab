"""oc_b7patient SECONDARY: patient exits on the 2021-2026 ledger (CONTAMINATED, info only).

Same joint-null method as the PRIMARY, 5 years, with y_pat from
tmp/patient_outcomes_4shift.npz (exact O/sg recompute, zero fallback) and B7
mults read-only from oc_cascadeboost/boost_mult_4shift.parquet. Ledger
REUSED read-only (n == 22312, base sum5y == 7.718304 +- 0.002).
Gate rows (dSum5y >= +0.273, timing >= 95) labelled CONTAMINATED/INFO-ONLY.
CPU-only.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
K2P = ROOT / "research/tournament/oc_k2placebo"
CB = ROOT / "research/tournament/oc_cascadeboost"

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
HB_S = 600


def phase_mean_sums(ph, yr, wv, yv, n_years=5):
    out = []
    for y in range(n_years):
        ss = []
        for p in PHASES:
            m = (ph == p) & (yr == y)
            ss.append(float((wv[m] * yv[m]).sum()) if m.any() else 0.0)
        out.append(float(np.mean(ss)))
    return out


def load_mult():
    d = pd.read_parquet(CB / "boost_mult_4shift.parquet")
    d["T"] = pd.to_datetime(d["T"], utc=True)
    exact, per_shift = {}, {}
    for s in SHIFTS:
        sub = d[d["shift"] == s].sort_values("T")
        t_ns = sub["T"].values.astype("datetime64[ns]").astype(np.int64)
        per_shift[s] = {"mult": sub["mult_B7"].to_numpy(dtype=float), "t_ns": t_ns,
                        "T": pd.to_datetime(sub["T"], utc=True).tolist()}
        for t, a in zip(per_shift[s]["T"], per_shift[s]["mult"]):
            exact[(int(s), pd.Timestamp(t))] = float(a)
    return exact, per_shift


def mult_at(shift, t, exact, per_shift):
    hit = exact.get((int(shift), pd.Timestamp(t)))
    if hit is not None:
        return hit
    t_ns = per_shift[int(shift)]["t_ns"]
    q = pd.Timestamp(t)
    if q.tzinfo is None:
        q = q.tz_localize("UTC")
    pos = int(np.searchsorted(t_ns, np.int64(q.value), side="right")) - 1
    if pos < 0:
        return 1.0
    return float(per_shift[int(shift)]["mult"][pos])


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
    assert n == N_GATE, n
    out = dict(np.load(HERE / "tmp/patient_outcomes_4shift.npz"))
    ypat = {"V1": out["yv1"].astype(float), "V2": out["yv2"].astype(float)}
    assert np.isfinite(ypat["V1"]).all() and np.isfinite(ypat["V2"]).all()

    exact, per_shift = load_mult()
    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    w = led["w"].astype(float)
    y10 = led["y10"].astype(float)
    mult_b7 = np.array([mult_at(int(ph[i]), bt_all[i], exact, per_shift)
                        for i in range(n)], dtype=float)
    is_b = mult_b7 == 1.5
    base_y = phase_mean_sums(ph, yr, w, y10)
    assert abs(sum(base_y) - BASE_GATE) <= 0.002, sum(base_y)
    boost_b7_y = phase_mean_sums(ph, yr, w * mult_b7, y10)
    rm_b7 = np.array([float(mult_b7[yr == y].mean()) for y in range(5)])
    norm_b7 = np.array([boost_b7_y[y] / rm_b7[y] for y in range(5)])
    print(f"B7 dSum5y={sum(boost_b7_y) - sum(base_y):.6f}", flush=True)

    uni = {}
    for y in range(5):
        lo = ANCH[y]
        hi = ANCH[y + 1] if y < 4 else YEAR_END
        for s in SHIFTS:
            t_ns = per_shift[s]["t_ns"]
            col = per_shift[s]["mult"]
            m = (t_ns >= np.int64(lo.value)) & (t_ns < np.int64(hi.value))
            uni[(y, s)] = col[m].astype(float)
    pos_of = {}
    for (y, s) in uni:
        t_ns = per_shift[s]["t_ns"]
        lo = ANCH[y]
        hi = ANCH[y + 1] if y < 4 else YEAR_END
        m = (t_ns >= np.int64(lo.value)) & (t_ns < np.int64(hi.value))
        pos_of[(y, s)] = {int(tt): j for j, tt in enumerate(t_ns[m])}
    fill_pos = np.full(n, -1, dtype=np.int64)
    for i in range(n):
        q = pd.Timestamp(bt_all[i])
        if q.tzinfo is None:
            q = q.tz_localize("UTC")
        fill_pos[i] = pos_of[(int(yr[i]), int(ph[i]))].get(int(q.value), -1)
    assert (fill_pos >= 0).all()

    res = {
        "config": {
            "ledger": "oc_k2placebo/tmp/ledger.npz + bt_all.npy read-only",
            "boost": "oc_cascadeboost/boost_mult_4shift.parquet mult_B7 read-only",
            "outcomes": "tmp/patient_outcomes_4shift.npz (exact O/sg VERBATIM recompute; V1 mu=1.5 / V2 +1 bar for boosted)",
            "gate": "sum-half + dSum5y>=+0.273 — CONTAMINATED INFO-ONLY (idea derived from cascade results covering these years)",
            "placebo_null": "JOINT (mult, flag) time-bar WITHIN (year, shift), 1000 uniform + block-42",
        },
        "reproduction": {"base_sum5y": round(sum(base_y), 6), "n_fills": int(n),
                         "b7_norms": [round(v, 6) for v in norm_b7],
                         "b7_dSum5y": round(float(sum(boost_b7_y) - sum(base_y)), 6)},
    }
    for variant in VARIANTS:
        yp = ypat[variant]
        boost_y = phase_mean_sums(ph, yr, w * mult_b7, np.where(is_b, yp, y10))
        dsum = float(sum(boost_y) - sum(base_y))
        dsum_b7 = float(sum(boost_y) - sum(boost_b7_y))
        sum_ge = sum(1 for y in range(5) if boost_y[y] >= base_y[y] - 1e-12)
        years = []
        for y in range(5):
            m = yr == y
            rm = float(mult_b7[m].mean())
            norm = float(boost_y[y]) / rm
            years.append({"year": ANCH[y].date().isoformat(), "n_fills": int(m.sum()),
                          "base": round(float(base_y[y]), 6),
                          "boosted": round(float(boost_y[y]), 6),
                          "realised_mean": round(rm, 6), "norm": round(norm, 6),
                          "gain_vs_base": round(norm - float(base_y[y]), 6),
                          "gain_vs_B7": round(norm - float(norm_b7[y]), 6)})
        dev4_v = float(sum(years[y]["norm"] for y in range(4)))
        dev4_b7 = float(norm_b7[:4].sum())
        print(f"{variant}: dSum5y={dsum:.6f} vsB7={dsum_b7:.6f} sum-half={sum_ge}/5 "
              f"dev4 {dev4_v:.6f} vs B7 {dev4_b7:.6f}", flush=True)
        timing = []
        for y in range(5):
            rng = np.random.default_rng(SEED_TIMING + y)
            my = (yr == y)
            actual = float(boost_y[y]) / float(mult_b7[my].mean())
            fw, fy10, fyp = w[my], y10[my], yp[my]
            fph, fp = ph[my], fill_pos[my]
            denom = float(mult_b7[my].mean())
            perms = np.empty(N_PERM)
            for k in range(N_PERM):
                fm = np.empty(my.sum())
                bp = np.empty(my.sum(), dtype=bool)
                for s in SHIFTS:
                    loc = np.where(fph == s)[0]
                    pm = rng.permutation(uni[(y, s)])
                    vals = pm[fp[loc]]
                    fm[loc] = vals
                    bp[loc] = vals == 1.5
                yperm = np.where(bp, fyp, fy10)
                s_sum = sum(float((fw[fph == p] * fm[fph == p] * yperm[fph == p]).sum())
                            for p in PHASES)
                perms[k] = (s_sum / 4.0) / denom
                if time.time() - last_hb > HB_S:
                    print(f"[hb] timing {variant} y={y} {k}/{N_PERM}", flush=True)
                    last_hb = time.time()
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            timing.append({"year": ANCH[y].date().isoformat(), "actual_norm": round(actual, 6),
                           "percentile": round(float(pct), 2)})
            print(f"timing {variant} y={y} pct={pct:.2f}", flush=True)
        block = []
        for y in range(5):
            rng = np.random.default_rng(SEED_BLOCK + y)
            my = (yr == y)
            actual = float(boost_y[y]) / float(mult_b7[my].mean())
            fw, fy10, fyp = w[my], y10[my], yp[my]
            fph, fp = ph[my], fill_pos[my]
            denom = float(mult_b7[my].mean())
            perms = np.empty(N_PERM)
            for k in range(N_PERM):
                fm = np.empty(my.sum())
                bp = np.empty(my.sum(), dtype=bool)
                for s in SHIFTS:
                    loc = np.where(fph == s)[0]
                    arr = uni[(y, s)]
                    blks = [arr[b:b + BLOCK] for b in range(0, len(arr), BLOCK)]
                    seq = np.concatenate([blks[b] for b in rng.permutation(len(blks))])
                    vals = seq[fp[loc]]
                    fm[loc] = vals
                    bp[loc] = vals == 1.5
                yperm = np.where(bp, fyp, fy10)
                s_sum = sum(float((fw[fph == p] * fm[fph == p] * yperm[fph == p]).sum())
                            for p in PHASES)
                perms[k] = (s_sum / 4.0) / denom
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            block.append({"year": ANCH[y].date().isoformat(), "actual_norm": round(actual, 6),
                          "percentile": round(float(pct), 2)})
        res[variant] = {"per_year": years, "timing_placebo": timing, "block_placebo": block,
                        "dSum5y": round(dsum, 6), "dSum5y_vs_B7": round(dsum_b7, 6),
                        "dev4_sum_norm": round(dev4_v, 6),
                        "dev4_sum_norm_B7": round(dev4_b7, 6),
                        "dev4_gain_vs_B7": round(dev4_v - dev4_b7, 6),
                        "sum_half_years_ge": int(sum_ge),
                        "gate_sum_half": bool(sum_ge >= 4),
                        "gate_dsum": bool(dsum >= DSUM_GATE),
                        "gate_pass": bool(sum_ge >= 4 and dsum >= DSUM_GATE)}
    (HERE / "tmp").mkdir(exist_ok=True)
    (HERE / "tmp/replica_patient.json").write_text(json.dumps(res, indent=1))
    print("wrote tmp/replica_patient.json", flush=True)


if __name__ == "__main__":
    main()
