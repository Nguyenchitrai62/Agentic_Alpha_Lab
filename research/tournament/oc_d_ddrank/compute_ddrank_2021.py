"""DD-rank 2021-2026 replica gate (CPU-only).

Reuses oc_k2placebo ledger read-only (gate n==22312, base sums ==
0.911273/0.832599/2.099814/3.197390/0.677229, sum5y 7.718304 +-0.002).
Joins per-fill (sym, shift=phase, T) frozen DD-rank mults (V1/V2) with causal
ffill fallback; missing -> 1.0. Per-year norm/gain; dSum5y + sum-half gate
(dSum5y>=+0.273 AND gain>0 in >=4/5). Rank-shuffle/timing/block placebos
reported (seeds 20261007/20261009/20261008 + y 0..4). Heartbeat 600 s.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
K2 = ROOT / "research/tournament/oc_k2placebo"

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
ANCH = [pd.Timestamp(a, tz="UTC") for a in ANCH5]
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
SEED_RANK = 20261007
SEED_BLOCK = 20261008
SEED_TIMING = 20261009
N_PERM = 1000
BLOCK = 42
BASE_GATE = 7.718304
BASE_Y = (0.911273, 0.832599, 2.099814, 3.197390, 0.677229)
PHASES = (0, 1, 2, 3)
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


def main() -> None:
    t0 = time.time()
    last_hb = t0
    led = dict(np.load(K2 / "tmp/ledger.npz"))
    for k in ("phase", "coin", "year", "bar_time", "rung"):
        led[k] = led[k].astype(np.int64)
    for k in ("w", "y10"):
        led[k] = led[k].astype(np.float64)
    bt_all = np.load(K2 / "tmp/bt_all.npy", allow_pickle=True)
    n = len(led["w"])
    print(f"loaded k2placebo ledger n={n}", flush=True)
    assert n == 22312, f"ledger size {n} != 22312"
    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    co = led["coin"].astype(int)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)
    base_y = phase_mean_sums(ph, yr, w, yv)
    got5 = float(sum(base_y))
    print(f"base sums={[round(v,6) for v in base_y]} sum5y={got5:.6f}", flush=True)
    assert abs(got5 - BASE_GATE) <= 0.002, "base sum5y gate fail"
    for y in range(5):
        assert abs(base_y[y] - BASE_Y[y]) <= 0.002, f"base y{y} fail"

    panel = pd.read_parquet(HERE / "ddrank_mult_2021.parquet")
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    exact = {}
    per_sym_shift = {}
    for (sym, s), sub in panel.groupby(["sym", "shift"]):
        sub = sub.sort_values("T")
        t_ns = sub["T"].values.astype("datetime64[ns]").astype(np.int64)
        per_sym_shift[(str(sym), int(s))] = (
            t_ns, sub["mult_V1"].to_numpy(float), sub["mult_V2"].to_numpy(float))
        for t, a, e in zip(sub["T"], sub["mult_V1"], sub["mult_V2"]):
            exact[(str(sym), int(s), pd.Timestamp(t))] = (float(a), float(e))

    def mult_at(sym, shift, t, variant):
        hit = exact.get((sym, int(shift), pd.Timestamp(t)))
        if hit is not None:
            return hit[0] if variant == "V1" else hit[1]
        key = (sym, int(shift))
        if key not in per_sym_shift:
            return 1.0
        t_ns, a, e = per_sym_shift[key]
        q = pd.Timestamp(t)
        if q.tzinfo is None:
            q = q.tz_localize("UTC")
        pos = int(np.searchsorted(t_ns, np.int64(q.value), side="right")) - 1
        if pos < 0:
            return 1.0
        return float((a if variant == "V1" else e)[pos])

    fill_sym = np.array([MAJORS[int(c)] for c in co])
    res = {"config": {
        "ledger": "oc_k2placebo/tmp/ledger.npz read-only (D0+B1 2021-2026)",
        "mult": "ddrank_mult_2021.parquet (frozen 180/60 DD rank)",
        "gate": "dSum5y>=+0.273 AND gain>0 in >=4/5 years",
        "seeds": [SEED_RANK, SEED_BLOCK, SEED_TIMING], "n_perm": N_PERM},
        "reproduction": {"base_sums": [round(v, 6) for v in base_y],
                         "base_sum5y": round(got5, 6), "n_fills": int(n)}}
    for variant in VARIANTS:
        mult = np.array([mult_at(fill_sym[i], int(ph[i]), bt_all[i], variant)
                         for i in range(n)], dtype=float)
        print(f"{variant}: boosted={(mult==1.25).mean():.4f} "
              f"deweighted={(mult==0.75).mean():.4f}", flush=True)
        tilt_y = phase_mean_sums(ph, yr, w * mult, yv)
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
                          "boosted_share": round(float((mult[m] == 1.25).mean()), 4),
                          "deweighted_share": round(float((mult[m] == 0.75).mean()), 4)})
            print(f"  {ANCH5[y]} base={base_y[y]:.6f} tilt={tilt_y[y]:.6f} "
                  f"rm={rm:.6f} norm={norm:.6f} gain={norm-base_y[y]:+.6f}", flush=True)
        dsum = float(sum(r["gain"] for r in years))
        nhalf = int(sum(1 for r in years if r["gain"] > 0))
        print(f"{variant}: dSum5y={dsum:+.6f} sum-half={nhalf}/5 "
              f"gate={'PASS' if (dsum>=0.273 and nhalf>=4) else 'FAIL'}", flush=True)

        rank, timing, block = [], [], []
        for y in range(5):
            my = np.where(yr == y)[0]
            denom = float(mult[my].mean())
            actual = float(tilt_y[y]) / denom
            fill_w = w[my]
            fill_y = yv[my]
            fill_ph = ph[my]
            # rank-shuffle within (phase, T) bars
            rng = np.random.default_rng(SEED_RANK + y)
            groups: dict = {}
            for j in my:
                groups.setdefault((int(ph[j]), pd.Timestamp(bt_all[j]).value), []).append(j)
            idx_of = {j: k for k, j in enumerate(my)}
            perms = np.empty(N_PERM)
            for k in range(N_PERM):
                fm = np.empty(len(my))
                for members in groups.values():
                    fm[[idx_of[j] for j in members]] = rng.permutation(mult[members])
                s_sum = sum(float((fill_w[fill_ph == p] * fm[fill_ph == p] * fill_y[fill_ph == p]).sum())
                            for p in PHASES)
                perms[k] = (s_sum / 4.0) / denom
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            rank.append({"year": ANCH5[y], "actual_norm": round(actual, 6),
                         "p5": round(float(np.quantile(perms, 0.05)), 6),
                         "p50": round(float(np.quantile(perms, 0.50)), 6),
                         "p95": round(float(np.quantile(perms, 0.95)), 6),
                         "percentile": round(float(pct), 2)})
            print(f"rank {variant} y={y} pct={pct:.2f}", flush=True)
            if time.time() - last_hb > HB_S:
                print(f"[hb] {variant} y={y} rank done", flush=True)
                last_hb = time.time()
            # timing uniform
            rng = np.random.default_rng(SEED_TIMING + y)
            m0 = mult[my]
            perms = np.empty(N_PERM)
            for k in range(N_PERM):
                fm = rng.permutation(m0)
                s_sum = sum(float((fill_w[fill_ph == p] * fm[fill_ph == p] * fill_y[fill_ph == p]).sum())
                            for p in PHASES)
                perms[k] = (s_sum / 4.0) / denom
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            timing.append({"year": ANCH5[y], "actual_norm": round(actual, 6),
                           "p5": round(float(np.quantile(perms, 0.05)), 6),
                           "p50": round(float(np.quantile(perms, 0.50)), 6),
                           "p95": round(float(np.quantile(perms, 0.95)), 6),
                           "percentile": round(float(pct), 2)})
            print(f"timing {variant} y={y} pct={pct:.2f}", flush=True)
            # block-42 per (sym, shift)
            rng = np.random.default_rng(SEED_BLOCK + y)
            lo_a = ANCH[y]
            hi_a = ANCH[y + 1] if y < 4 else YEAR_END
            lo_ns, hi_ns = np.int64(lo_a.value), np.int64(hi_a.value)
            blk_of = {}
            for key, (t_ns, a, e) in per_sym_shift.items():
                arr = (a if variant == "V1" else e)
                m = (t_ns >= lo_ns) & (t_ns < hi_ns)
                seq = arr[m].astype(float)
                blk_of[key] = [seq[b:b + BLOCK] for b in range(0, len(seq), BLOCK)]
            pos = np.empty(len(my), dtype=np.int64)
            for k2, j in enumerate(my):
                key = (fill_sym[j], int(ph[j]))
                t_ns, _, _ = per_sym_shift[key]
                m = (t_ns >= lo_ns) & (t_ns < hi_ns)
                grid = t_ns[m]
                q = pd.Timestamp(bt_all[j])
                if q.tzinfo is None:
                    q = q.tz_localize("UTC")
                pos[k2] = int(np.searchsorted(grid, np.int64(q.value), side="right")) - 1
            assert (pos >= 0).all()
            perms = np.empty(N_PERM)
            for k in range(N_PERM):
                fm = np.empty(len(my))
                perm_seq = {}
                for key, blks in blk_of.items():
                    order = rng.permutation(len(blks)) if blks else np.array([], dtype=int)
                    perm_seq[key] = np.concatenate([blks[b] for b in order]) if blks else np.array([])
                for t, j in enumerate(my):
                    fm[t] = perm_seq[(fill_sym[j], int(ph[j]))][pos[t]]
                s_sum = sum(float((fill_w[fill_ph == p] * fm[fill_ph == p] * fill_y[fill_ph == p]).sum())
                            for p in PHASES)
                perms[k] = (s_sum / 4.0) / denom
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            block.append({"year": ANCH5[y], "actual_norm": round(actual, 6),
                          "p5": round(float(np.quantile(perms, 0.05)), 6),
                          "p50": round(float(np.quantile(perms, 0.50)), 6),
                          "p95": round(float(np.quantile(perms, 0.95)), 6),
                          "percentile": round(float(pct), 2)})
            print(f"block {variant} y={y} pct={pct:.2f}", flush=True)
        res[variant] = {"per_year": years, "dSum5y": round(dsum, 6),
                        "sum_half": f"{nhalf}/5",
                        "gate": "PASS" if (dsum >= 0.273 and nhalf >= 4) else "FAIL",
                        "rank_placebo": rank, "timing_placebo": timing,
                        "block_placebo": block}
    (HERE / "tmp/ddrank_2021.json").write_text(json.dumps(res, indent=1))
    print("wrote tmp/ddrank_2021.json", flush=True)


if __name__ == "__main__":
    main()
