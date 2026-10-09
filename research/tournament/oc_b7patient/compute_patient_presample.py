"""oc_b7patient PRIMARY: patient exits on the pre-sample ledger.

Method inherited from oc_cboostpre/compute_boost_presample.py +
oc_b7taper/compute_taper_presample.py, with patient outcomes from
tmp/patient_outcomes.npz (1m recompute; V1 mu=1.5 TP / V2 one-bar extension
for B7-boosted fills only; same B7 sizing mults 1.5/7d market-wide per shift).
Ledger REUSED read-only from oc_presampletilt/tmp (n == 9731, per-leg
909/2986/3115/2721, base sums == (2.313362, 2.678870, 0.577643, 0.297538) +- 1e-6).
B7 reference mults read-only from oc_cboostpre/boost_mult_presample.parquet.

Per year: base(y), B7(y), V(y) = w*mult_B7*y_V, realised_mean (same mults),
norm = V/realised_mean, gain_vs_base = norm-base, gain_vs_B7 = norm-norm_B7.
Timing/block placebo (1000 perms, seeds 20261007+y / 20261008+y, y=0..3) with
the JOINT (mult, flag) time-bar-within-(year,shift) null (perm takes the
permuted flag's choice of y: y_pat if permuted-boosted else ledger y10).
Stop/TP/timeout splits from recomputed kinds (known only). CPU-only.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PST = ROOT / "research/tournament/oc_presampletilt"
CBP = ROOT / "research/tournament/oc_cboostpre"

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
HB_S = 600
KIND_UNKNOWN = -1
KIND_STOP = (0, 2)
KIND_TP = (1,)
KIND_TIME = (3,)


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
    d = pd.read_parquet(CBP / "boost_mult_presample.parquet")
    d["T"] = pd.to_datetime(d["T"], utc=True)
    exact = {}
    per_shift = {}
    for s in SHIFTS:
        sub = d[d["shift"] == s].sort_values("T")
        t_ns = sub["T"].values.astype("datetime64[ns]").astype(np.int64)
        per_shift[s] = {"mult": sub["mult_B7"].to_numpy(dtype=float), "t_ns": t_ns,
                        "T": pd.to_datetime(sub["T"], utc=True).tolist()}
        for t, a in zip(per_shift[s]["T"], per_shift[s]["mult"]):
            exact[(int(s), pd.Timestamp(t))] = float(a)
    return exact, per_shift


def mult_at(shift, t, exact, per_shift):
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
        return 1.0
    return float(per_shift[int(shift)]["mult"][pos])


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
    assert n == N_GATE, n
    for y, g in enumerate(PER_LEG_GATE):
        assert int((led["year"] == y).sum()) == g

    out = dict(np.load(HERE / "tmp/patient_outcomes.npz"))
    yv1_raw, yv2_raw = out["yv1"].astype(float), out["yv2"].astype(float)
    kv1_raw, kv2_raw = out["kv1"].astype(int), out["kv2"].astype(int)
    kb_raw = out["kb"].astype(int)
    print(f"outcomes: yv1 ok={np.isfinite(yv1_raw).sum()} yv2 ok={np.isfinite(yv2_raw).sum()} "
          f"ext_fallback={int(out['n_unknown_ext'])} fill_mismatch={int(out['n_fill_mismatch'])}",
          flush=True)

    exact, per_shift = load_mult()
    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    w = led["w"].astype(float)
    y10 = led["y10"].astype(float)

    mult_b7 = np.array([mult_at(int(ph[i]), bt_all[i], exact, per_shift)
                        for i in range(n)], dtype=float)
    assert set(np.round(mult_b7, 6)) <= {1.0, 1.5}
    is_b = mult_b7 == 1.5

    base_y = phase_mean_sums(ph, yr, w, y10)
    for y in range(4):
        assert abs(base_y[y] - BASE_GATE[y]) <= 1e-6, (y, base_y[y])
    boost_b7_y = phase_mean_sums(ph, yr, w * mult_b7, y10)
    rm_b7 = np.array([float(mult_b7[yr == y].mean()) for y in range(4)])
    norm_b7 = np.array([boost_b7_y[y] / rm_b7[y] for y in range(4)])
    print(f"base sums={[round(v, 6) for v in base_y]}", flush=True)
    print(f"B7 norms={[round(v, 6) for v in norm_b7]} sum4={float(norm_b7.sum()):.6f}", flush=True)

    # patient y arrays with fallback to ledger y10 where recompute missing
    ypat = {}
    for name, raw in (("V1", yv1_raw), ("V2", yv2_raw)):
        arr = raw.copy()
        miss = ~np.isfinite(arr)
        arr[miss] = y10[miss]
        ypat[name] = arr
        print(f"{name}: fallback fills={int(miss.sum())}", flush=True)

    # time-bar universes (binary mult series) per (y, s) for the joint null
    uni = {}
    for y in range(4):
        lo, hi = LEG_BOUNDS[LEG_ORDER[y]]
        for s in SHIFTS:
            t_ns = per_shift[s]["t_ns"]
            col = per_shift[s]["mult"]
            m = (t_ns >= np.int64(lo.value)) & (t_ns < np.int64(hi.value))
            uni[(y, s)] = col[m].astype(float)
    pos_of = {}
    for (y, s) in uni:
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
    assert (fill_pos >= 0).all(), int((fill_pos < 0).sum())

    res = {
        "config": {
            "ledger": "oc_presampletilt/tmp/ledger_presample.npz + bt_presample.npy read-only (D0+B1, no budget/cap; SPOT fills/exits)",
            "boost": "oc_cboostpre/boost_mult_presample.parquet mult_B7 read-only (closes-only >4sg, union per shift; 1.5 in (tc,tc+7d])",
            "outcomes": "tmp/patient_outcomes.npz (1m recompute VERBATIM outcome_mu mu=1.0/1.5 + holdext one-bar extension; fallback to ledger y10 on 15 rebuild misses + ext fallbacks)",
            "rule": "V1: boosted TP 1.0->1.5sg (4sg stop kept); V2: boosted timeouts +1 bar to T+480 same sl/bl/tp, maker-first taker fallback, mid+end funding; else base",
            "normalisation": "norm(y)=V(y)/realised_mean_B7(y); gain_vs_base=norm-base; gain_vs_B7=norm-norm_B7; perm norms use the ACTUAL denominator",
            "percentile": "100*(1+#{perm<=actual})/1001; significant iff >=95",
            "placebo_null": "JOINT (mult, flag) time-bar permutation WITHIN (year, shift) (1000 uniform; block-42 chronological within (year, shift)); perm fill takes permuted flag's y (y_pat if boosted else y10)",
            "beater": "sum4 norm_V > sum4 norm_B7 (strict) is the only gate to the engine",
            "contamination": "PRIMARY clean test: pre-sample years unseen when the cascade idea was formed; 2021-2026 is contaminated (secondary only)",
            "seed_timing": SEED_TIMING, "seed_block": SEED_BLOCK,
            "n_perm": N_PERM, "block": BLOCK,
        },
        "reproduction": {"per_leg_gate": list(PER_LEG_GATE),
                         "base_sums": [round(v, 6) for v in base_y], "n_fills": int(n),
                         "b7_norms": [round(v, 6) for v in norm_b7],
                         "b7_sum4_norm": round(float(norm_b7.sum()), 6)},
    }

    for variant in VARIANTS:
        yp = ypat[variant]
        boost_y = phase_mean_sums(ph, yr, w * mult_b7, np.where(is_b, yp, y10))
        years = []
        for y in range(4):
            m = yr == y
            rm = float(mult_b7[m].mean())
            norm = float(boost_y[y]) / rm
            years.append({"year": LEG_ORDER[y], "n_fills": int(m.sum()),
                          "base": round(float(base_y[y]), 6),
                          "boosted_B7": round(float(boost_b7_y[y]), 6),
                          "patient": round(float(boost_y[y]), 6),
                          "realised_mean": round(rm, 6),
                          "norm": round(norm, 6),
                          "gain_vs_base": round(norm - float(base_y[y]), 6),
                          "gain_vs_B7": round(norm - float(norm_b7[y]), 6),
                          "boosted_share_fills": round(float(is_b[m].mean()), 4)})
        for r in years:
            print(f"  {variant} {r['year']} base={r['base']} norm={r['norm']} "
                  f"gBase={r['gain_vs_base']} gB7={r['gain_vs_B7']}", flush=True)

        # joint placebo: permute (mult, flag) together; y follows permuted flag
        timing = []
        for y in range(4):
            rng = np.random.default_rng(SEED_TIMING + y)
            my = (yr == y)
            actual = float(boost_y[y]) / float(mult_b7[my].mean())
            fw, fy10, fyp = w[my], y10[my], yp[my]
            fph, fp = ph[my], fill_pos[my]
            slices = {s: (np.where(fph == s)[0], uni[(y, s)]) for s in SHIFTS}
            denom = float(mult_b7[my].mean())
            perms = np.empty(N_PERM)
            for k in range(N_PERM):
                fm = np.empty(my.sum())
                bp = np.empty(my.sum(), dtype=bool)
                for s in SHIFTS:
                    loc, arr = slices[s]
                    pm = rng.permutation(arr)
                    upos = fp[loc]
                    vals = pm[upos]
                    fm[loc] = vals
                    bp[loc] = vals == 1.5
                yperm = np.where(bp, fyp, fy10)
                s_sum = 0.0
                for p in PHASES:
                    mp = fph == p
                    s_sum += float((fw[mp] * fm[mp] * yperm[mp]).sum())
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

        block = []
        for y in range(4):
            rng = np.random.default_rng(SEED_BLOCK + y)
            my = (yr == y)
            actual = float(boost_y[y]) / float(mult_b7[my].mean())
            fw, fy10, fyp = w[my], y10[my], yp[my]
            fph, fp = ph[my], fill_pos[my]
            denom = float(mult_b7[my].mean())
            blk_of = {}
            for s in SHIFTS:
                arr = uni[(y, s)]
                blk_of[s] = [arr[b:b + BLOCK] for b in range(0, len(arr), BLOCK)]
            perms = np.empty(N_PERM)
            for k in range(N_PERM):
                fm = np.empty(my.sum())
                bp = np.empty(my.sum(), dtype=bool)
                for s in SHIFTS:
                    loc = np.where(fph == s)[0]
                    blks = blk_of[s]
                    order = rng.permutation(len(blks))
                    seq = np.concatenate([blks[b] for b in order]) if blks else np.array([])
                    vals = seq[fp[loc]]
                    fm[loc] = vals
                    bp[loc] = vals == 1.5
                yperm = np.where(bp, fyp, fy10)
                s_sum = 0.0
                for p in PHASES:
                    mp = fph == p
                    s_sum += float((fw[mp] * fm[mp] * yperm[mp]).sum())
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

        # exit splits from recomputed kinds (known only)
        kpat = kv1_raw if variant == "V1" else kv2_raw
        stops, tps, times = [], [], []
        for y in range(4):
            idx_y = np.where(yr == y)[0]
            known_b = kb_raw[idx_y] != KIND_UNKNOWN
            known_p = kpat[idx_y] != KIND_UNKNOWN
            row = {"year": LEG_ORDER[y]}
            if known_b.any():
                row["base_stop_rate"] = round(float(np.isin(kb_raw[idx_y[known_b]], KIND_STOP).mean()), 4)
                row["base_tp_rate"] = round(float(np.isin(kb_raw[idx_y[known_b]], KIND_TP).mean()), 4)
                row["base_time_rate"] = round(float(np.isin(kb_raw[idx_y[known_b]], KIND_TIME).mean()), 4)
            else:
                row["base_stop_rate"] = row["base_tp_rate"] = row["base_time_rate"] = None
            mb = is_b[idx_y] & (kpat[idx_y] != KIND_UNKNOWN)
            row["boosted_share"] = round(float(is_b[idx_y].mean()), 4)
            if mb.any():
                row["boosted_stop_rate"] = round(float(np.isin(kpat[idx_y[mb]], KIND_STOP).mean()), 4)
                row["boosted_tp_rate"] = round(float(np.isin(kpat[idx_y[mb]], KIND_TP).mean()), 4)
                row["boosted_time_rate"] = round(float(np.isin(kpat[idx_y[mb]], KIND_TIME).mean()), 4)
                row["stop_delta"] = round(row["boosted_stop_rate"] - row["base_stop_rate"], 4)
            else:
                row["boosted_stop_rate"] = row["boosted_tp_rate"] = None
                row["boosted_time_rate"] = None
                row["stop_delta"] = None
            stops.append(row)
            print(f"exit {variant} {row}", flush=True)
        known_all = (kpat != KIND_UNKNOWN) & (kb_raw != KIND_UNKNOWN)
        is_bk = is_b & (kpat != KIND_UNKNOWN)
        pooled = {"boosted_share": round(float(is_b.mean()), 4),
                  "base_stop_rate": round(float(np.isin(kb_raw[kb_raw != KIND_UNKNOWN], KIND_STOP).mean()), 4),
                  "boosted_stop_rate": round(float(np.isin(kpat[is_bk], KIND_STOP).mean()), 4)
                  if is_bk.any() else None}
        if pooled["boosted_stop_rate"] is not None:
            pooled["stop_delta"] = round(pooled["boosted_stop_rate"] - pooled["base_stop_rate"], 4)
        print(f"exit {variant} pooled {pooled}", flush=True)

        norms = np.array([r["norm"] for r in years])
        res[variant] = {"per_year": years, "timing_placebo": timing,
                        "block_placebo": block, "exits": stops, "pooled_exit": pooled,
                        "sum4_norm": round(float(norms.sum()), 6),
                        "sum4_gain_vs_base": round(float((norms - np.array(base_y)).sum()), 6),
                        "sum4_gain_vs_B7": round(float((norms - norm_b7).sum()), 6),
                        "beats_B7": bool(float(norms.sum()) > float(norm_b7.sum()))}

    (HERE / "tmp").mkdir(exist_ok=True)
    (HERE / "tmp/patient_presample.json").write_text(json.dumps(res, indent=1))
    print("wrote tmp/patient_presample.json", flush=True)
    for variant in VARIANTS:
        r = res[variant]
        print(f"{variant}: sum4_norm={r['sum4_norm']} vs B7 {res['reproduction']['b7_sum4_norm']} "
              f"gain_vs_B7={r['sum4_gain_vs_B7']} beats_B7={r['beats_B7']}", flush=True)


if __name__ == "__main__":
    main()
