"""oc_k2seeds placebo: per-seed K2 dip-replica gain + timing/block percentiles (clean year only).

Reuses oc_k2placebo/tmp/ledger.npz read-only (gate n=22312, base_sum5y=7.718304
not rescored). Per seed S in {1234,1,2,3,4}: K2 mult from that seed's low1
(1234 = frozen oc_kronoshidden file; 1-4 = kronos_features_seed{S}.parquet),
fits = frozen fits.json anchor-2025 fit for the clean year (shortcut row).
Joins clean-year fills (sym,shift=phase,T) only. Timing placebo: 1000 uniform
bar-level perms of the seed's clean-year decision-bar multiset (seed
20261007+4); block placebo: 1000 perms in 42-bar blocks per (sym,shift) (seed
20261008+4). Percentile = 100*(1+#{perm<=actual})/1001. Vectorised numpy.
Also: multiplier-change share over clean-year decision bars present in ALL 5
seeds (fraction where NOT all 5 K2 mults agree) + pairwise vs 1234.

Usage: python compute_placebo_seed.py   (light CPU; needs all 4 seed parquets)
Output: tmp/placebo.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
KH = HERE.parent / "oc_kronoshidden"
PLED = HERE.parent / "oc_k2placebo" / "tmp"
TMP = HERE / "tmp"

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
Y4_START = pd.Timestamp("2025-09-24", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
START = pd.Timestamp("2020-08-01", tz="UTC")
SEED_TIMING = 20261007
SEED_BLOCK = 20261008
N_PERM = 1000
BLOCK = 42
SEEDS = (1234, 1, 2, 3, 4)
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
PHASES = (0, 1, 2, 3)


def assign_mult(risk, direction, q20, q80, hi=1.25, lo=0.75):
    r = float(risk)
    if not np.isfinite(r):
        return 1.0
    if direction > 0:
        if r >= q80:
            return hi
        if r <= q20:
            return lo
        return 1.0
    if r >= q80:
        return lo
    if r <= q20:
        return hi
    return 1.0


def load_feat(seed):
    path = KH / "kronos_features_4shift.parquet" if seed == 1234 else HERE / f"kronos_features_seed{seed}.parquet"
    return pd.read_parquet(path, columns=["sym", "shift", "T", "low1"])


def main():
    TMP.mkdir(parents=True, exist_ok=True)
    fits = json.loads((KH / "fits.json").read_text())
    f4 = fits["2025-09-24"]
    led = dict(np.load(PLED / "ledger.npz"))
    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    co = led["coin"].astype(int)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)
    bt_ord = led["bar_time"].astype(np.int64)
    bt_all = START + pd.to_timedelta(bt_ord, unit="m")
    m4 = yr == 4
    print(f"ledger n={len(w)} clean-year fills={int(m4.sum())}", flush=True)

    # ---- per-seed clean-year K2 mults on fills + decision-bar universes ----
    seed_fill_mult = {}
    seed_bar = {}  # seed -> (keys, mults) over clean-year decision bars
    for seed in SEEDS:
        feat = load_feat(seed)
        sub = feat[(feat["T"] >= Y4_START) & (feat["T"] < YEAR_END)].copy()
        sub = sub.sort_values(["sym", "shift", "T"]).reset_index(drop=True)
        r = -sub["low1"].to_numpy(dtype=float)
        mm = np.where(~np.isfinite(r), 1.0,
                      np.where(r >= f4["q80"], 1.25, np.where(r <= f4["q20"], 0.75, 1.0)))
        keys = list(zip(sub["sym"].astype(str), sub["shift"].astype(int),
                        pd.to_datetime(sub["T"], utc=True)))
        lut = {k: float(v) for k, v in zip(keys, mm)}
        miss = 0
        fm = np.empty(int(m4.sum()))
        idx4 = np.where(m4)[0]
        for j, i in enumerate(idx4):
            key = (MAJORS[int(co[i])], int(ph[i]), pd.Timestamp(bt_all[i]))
            v = lut.get(key)
            if v is None:
                miss += 1
                v = 1.0
            fm[j] = v
        print(f"seed {seed}: universe={len(keys)} fill-mults={sorted(set(np.round(fm, 6)))} missing={miss}", flush=True)
        assert miss == 0, f"seed {seed}: {miss} fills w/o feature"
        seed_fill_mult[seed] = fm
        seed_bar[seed] = (keys, mm)

    # ---- per-seed normalised replica gain (clean year) ----
    fw, fy, fph = w[m4], yv[m4], ph[m4]
    base = float(sum(float(((fph == p) & True).sum() and (fw[fph == p] * fy[fph == p]).sum()) for p in PHASES)) / 4.0
    out_seeds = {}
    for seed in SEEDS:
        fm = seed_fill_mult[seed]
        k2 = float(sum(float((fw[(fph == p)] * fm[(fph == p)] * fy[(fph == p)]).sum()) for p in PHASES)) / 4.0
        rm = float(fm.mean())
        norm = float(k2 / rm)
        out_seeds[str(seed)] = {"k2": round(k2, 6), "realised_mean": round(rm, 6),
                                "norm": round(norm, 6), "base": round(base, 6)}
        print(f"seed {seed}: base={base:.6f} k2={k2:.6f} rm={rm:.6f} norm={norm:.6f}", flush=True)

    # ---- placebos per seed (clean year y=4 only) ----
    for seed in SEEDS:
        keys, mm = seed_bar[seed]
        idx = {k: i for i, k in enumerate(keys)}
        pos = np.array([idx[(MAJORS[int(co[i])], int(ph[i]), pd.Timestamp(bt_all[i]))] for i in np.where(m4)[0]])
        fm = seed_fill_mult[seed]
        denom = float(fm.mean())
        actual = float(sum(float((fw[fph == p] * fm[fph == p] * fy[fph == p]).sum()) for p in PHASES) / 4.0) / denom
        rng = np.random.default_rng(SEED_TIMING + 4)
        tp = np.empty(N_PERM)
        for k in range(N_PERM):
            pm = rng.permutation(mm)
            cur = pm[pos]
            tp[k] = float(sum(float((fw[fph == p] * cur[fph == p] * fy[fph == p]).sum()) for p in PHASES) / 4.0) / denom
        pct_t = 100.0 * (1 + int((tp <= actual).sum())) / (N_PERM + 1)
        # block placebo
        groups: dict = {}
        for i, k in enumerate(keys):
            groups.setdefault((k[0], k[1]), []).append(i)
        gblocks = {}
        for g, idxs in groups.items():
            idxs = sorted(idxs, key=lambda i: keys[i][2])
            gblocks[g] = [idxs[b:b + BLOCK] for b in range(0, len(idxs), BLOCK)]
        rng2 = np.random.default_rng(SEED_BLOCK + 4)
        bp = np.empty(N_PERM)
        cur = np.empty_like(mm)
        for k in range(N_PERM):
            for g, blks in gblocks.items():
                order = rng2.permutation(len(blks))
                seq = []
                for b in order:
                    seq.extend(mm[blks[b]])
                for i, v in zip(sorted(groups[g], key=lambda i: keys[i][2]), seq):
                    cur[i] = v
            curf = cur[pos]
            bp[k] = float(sum(float((fw[fph == p] * curf[fph == p] * fy[fph == p]).sum()) for p in PHASES) / 4.0) / denom
        pct_b = 100.0 * (1 + int((bp <= actual).sum())) / (N_PERM + 1)
        out_seeds[str(seed)].update({
            "timing": {"actual_norm": round(actual, 6), "p5": round(float(np.quantile(tp, 0.05)), 6),
                       "p50": round(float(np.quantile(tp, 0.50)), 6), "p95": round(float(np.quantile(tp, 0.95)), 6),
                       "percentile": round(float(pct_t), 2)},
            "block": {"actual_norm": round(actual, 6), "p5": round(float(np.quantile(bp, 0.05)), 6),
                      "p50": round(float(np.quantile(bp, 0.50)), 6), "p95": round(float(np.quantile(bp, 0.95)), 6),
                      "percentile": round(float(pct_b), 2)}})
        print(f"seed {seed}: norm={actual:.6f} timing_pct={pct_t:.2f} block_pct={pct_b:.2f}", flush=True)

    # ---- multiplier-change share (clean-year bars present in ALL 5 seeds) ----
    common = set(seed_bar[1234][0])
    for seed in (1, 2, 3, 4):
        common &= set(seed_bar[seed][0])
    print(f"common clean-year bars: {len(common)}", flush=True)
    maps = {s: {k: v for k, v in zip(*seed_bar[s])} for s in SEEDS}
    keys_sorted = sorted(common)
    mat = np.array([[maps[s][k] for k in keys_sorted] for s in SEEDS])
    disagree = (mat.max(axis=0) != mat.min(axis=0)).mean()
    pairwise = {str(s): round(float((mat[0] != mat[SEEDS.index(s)]).mean()), 6) for s in (1, 2, 3, 4)}
    print(f"change-share: any-disagree={disagree:.6f} pairwise_vs1234={pairwise}", flush=True)

    res = {"config": {"rule": "K2 1.25/0.75 risk=-low1 fits.json 2025-09-24 dir/q20/q80 missing->1",
                      "replica": "oc_k2placebo ledger.npz read-only; clean year only",
                      "seeds_timing": SEED_TIMING + 4, "seeds_block": SEED_BLOCK + 4,
                      "n_perm": N_PERM, "block": BLOCK,
                      "percentile": "100*(1+#{perm<=actual})/1001"},
           "base_clean": round(base, 6),
           "per_seed": out_seeds,
           "change_share": {"n_common_bars": len(keys_sorted),
                            "any_disagree": round(float(disagree), 6),
                            "pairwise_vs_1234": pairwise}}
    (TMP / "placebo.json").write_text(json.dumps(res, indent=1))
    print("wrote tmp/placebo.json", flush=True)


if __name__ == "__main__":
    main()
