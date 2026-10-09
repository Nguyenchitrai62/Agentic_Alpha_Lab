"""oc_timesfm timing placebo: is the T3 tilt's post-release gain distinguishable from random timing?

Method = exact copy of research/tournament/oc_k2placebo/compute_k2placebo.py
with the T3 multiplier (risk = -f_q10, fits.json here) instead of K2.
The D0+B1 replica ledger is REUSED read-only from oc_k2placebo/tmp
(ledger.npz + bt_all.npy; identical build_base output, reproduction gate:
n == 22312 and base 4-phase-mean sum5y == 7.718304 +- 0.002). No heavy rebuild.

Per year y: base(y), t3(y), realised_mean(y), norm(y) = t3(y)/realised_mean(y).
Timing placebo (primary): 1000 uniform bar-level permutations of the T3
multipliers over decision bars (seed 20261007+y), normalised by the ACTUAL
realised mean. Block placebo: 42-bar blocks per (sym, shift) (seed 20261008+y).
Percentile = 100*(1+#{perm<=actual})/1001; significant iff >= 95. Focus = Y4.
CPU-only (numpy).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
K2P = ROOT / "research/tournament/oc_k2placebo"

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
ANCH = [pd.Timestamp(a, tz="UTC") for a in ANCH5]
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
SEED_TIMING = 20261007
SEED_BLOCK = 20261008
N_PERM = 1000
BLOCK = 42
BASE_GATE = 7.718304
N_GATE = 22312
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
PHASES = (0, 1, 2, 3)


def phase_mean_sums(ph, yr, wv, yv):
    out = []
    for y in range(5):
        ss = []
        for p in PHASES:
            m = (ph == p) & (yr == y)
            ss.append(float((wv[m] * yv[m]).sum()) if m.any() else 0.0)
        out.append(float(np.mean(ss)))
    return out


def main() -> None:
    led = dict(np.load(K2P / "tmp/ledger.npz"))
    for k in ("phase", "coin", "year", "bar_time", "rung"):
        led[k] = led[k].astype(np.int64)
    for k in ("w", "y10"):
        led[k] = led[k].astype(np.float64)
    bt_all = np.load(K2P / "tmp/bt_all.npy", allow_pickle=True)
    n = len(led["w"])
    print(f"loaded ledger n={n}", flush=True)
    assert n == N_GATE, f"ledger size {n} != {N_GATE}"

    fits = json.loads((HERE / "fits.json").read_text())
    feat = pd.read_parquet(HERE / "timesfm_features_4shift.parquet",
                           columns=["sym", "shift", "T", "f_q10"])
    lut: dict = {}
    for s, sh, t, q in zip(feat["sym"], feat["shift"], feat["T"], feat["f_q10"]):
        lut[(str(s), int(sh), pd.Timestamp(t))] = float(q)
    del feat

    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    co = led["coin"].astype(int)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)
    bt_ord = led["bar_time"].astype(np.int64)
    START = pd.Timestamp("2020-08-01", tz="UTC")

    import sys
    sys.path.insert(0, str(HERE))
    from tilt_rule import assign_mult  # noqa: E402

    mult = np.ones(n, dtype=float)
    miss = 0
    for i in range(n):
        bt = START + pd.Timedelta(minutes=int(bt_ord[i]))
        key = (MAJORS[int(co[i])], int(ph[i]), bt)
        q = lut.get(key)
        y = int(yr[i])
        f = fits[ANCH5[y]]
        risk = -q if q is not None and np.isfinite(q) else float("nan")
        if q is None:
            miss += 1
        mult[i] = assign_mult(risk, f["direction"], f["q20"], f["q80"], 1.25, 0.75)
    print(f"T3 join: n={n} missing={miss} mult values={sorted(set(np.round(mult, 6)))}", flush=True)

    base_y = phase_mean_sums(ph, yr, w, yv)
    t3_y = phase_mean_sums(ph, yr, w * mult, yv)
    got5 = float(sum(base_y))
    print(f"base 4-phase-mean sums={[round(v, 6) for v in base_y]} sum5y={got5:.6f}", flush=True)
    assert abs(got5 - BASE_GATE) <= 0.002, f"base {got5} != {BASE_GATE}"
    years = []
    for y in range(5):
        m = yr == y
        rm = float(mult[m].mean()) if m.any() else 1.0
        years.append({"year": ANCH[y].date().isoformat(),
                      "n_fills": int(m.sum()),
                      "base": round(float(base_y[y]), 6),
                      "t3": round(float(t3_y[y]), 6),
                      "realised_mean": round(rm, 6),
                      "norm": round(float(t3_y[y]) / rm, 6) if rm else 0.0})
    for r in years:
        print(f"  {r['year']} n={r['n_fills']} base={r['base']} t3={r['t3']} "
              f"rm={r['realised_mean']} norm={r['norm']}", flush=True)

    feat3 = pd.read_parquet(HERE / "timesfm_features_4shift.parquet",
                            columns=["sym", "shift", "T", "f_q10"])
    bar_pos = []
    bar_mults = []
    bar_keys_per_year = []
    for y in range(5):
        lo_a = ANCH[y]
        hi_a = ANCH[y + 1] if y < 4 else YEAR_END
        sub = feat3[(feat3["T"] >= lo_a) & (feat3["T"] < hi_a)].copy()
        sub = sub.sort_values(["sym", "shift", "T"]).reset_index(drop=True)
        f = fits[ANCH5[y]]
        r = -sub["f_q10"].to_numpy(dtype=float)
        if f["direction"] > 0:
            mm = np.where(~np.isfinite(r), 1.0,
                          np.where(r >= f["q80"], 1.25,
                                   np.where(r <= f["q20"], 0.75, 1.0)))
        else:
            mm = np.array([assign_mult(v, -1, f["q20"], f["q80"], 1.25, 0.75) for v in r])
        keys = list(zip(sub["sym"].astype(str), sub["shift"].astype(int),
                        pd.to_datetime(sub["T"], utc=True)))
        idx = {k: i for i, k in enumerate(keys)}
        bar_mults.append(mm.astype(float))
        bar_keys_per_year.append(keys)
        pos = np.full(int((yr == y).sum()), -1, dtype=np.int64)
        fill_idx = np.where(yr == y)[0]
        for j, i in enumerate(fill_idx):
            key = (MAJORS[int(co[i])], int(ph[i]), pd.Timestamp(bt_all[i]))
            pos[j] = idx.get(key, -1)
        assert (pos >= 0).all(), f"year {y}: {(pos < 0).sum()} fills w/o bar"
        bar_pos.append(pos)
    del feat3
    print(f"bar universes: {[len(b) for b in bar_mults]}", flush=True)

    timing = []
    for y in range(5):
        rng = np.random.default_rng(SEED_TIMING + y)
        mm = bar_mults[y]
        pos = bar_pos[y]
        actual = float(t3_y[y]) / float(mult[yr == y].mean())
        fill_w = w[yr == y]
        fill_y = yv[yr == y]
        fill_ph = ph[yr == y]
        denom = float(mult[yr == y].mean())
        perms = np.empty(N_PERM)
        for k in range(N_PERM):
            pm = rng.permutation(mm)
            fm = pm[pos]
            s = 0.0
            for p in PHASES:
                mp = fill_ph == p
                s += float((fill_w[mp] * fm[mp] * fill_y[mp]).sum())
            perms[k] = (s / 4.0) / denom
        pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
        timing.append({"year": ANCH[y].date().isoformat(),
                       "actual_norm": round(actual, 6),
                       "p5": round(float(np.quantile(perms, 0.05)), 6),
                       "p50": round(float(np.quantile(perms, 0.50)), 6),
                       "p95": round(float(np.quantile(perms, 0.95)), 6),
                       "percentile": round(float(pct), 2)})
        print(f"timing y={y} actual={actual:.6f} "
              f"p5={np.quantile(perms, 0.05):.6f} p50={np.quantile(perms, 0.50):.6f} "
              f"p95={np.quantile(perms, 0.95):.6f} pct={pct:.2f}", flush=True)

    block = []
    for y in range(5):
        rng = np.random.default_rng(SEED_BLOCK + y)
        keys = bar_keys_per_year[y]
        mm = bar_mults[y]
        groups: dict = {}
        for i, k in enumerate(keys):
            groups.setdefault((k[0], k[1]), []).append(i)
        group_blocks = {}
        for g, idxs in groups.items():
            idxs = sorted(idxs, key=lambda i: keys[i][2])
            group_blocks[g] = [idxs[b:b + BLOCK] for b in range(0, len(idxs), BLOCK)]
        pos = bar_pos[y]
        actual = float(t3_y[y]) / float(mult[yr == y].mean())
        fill_w = w[yr == y]
        fill_y = yv[yr == y]
        fill_ph = ph[yr == y]
        denom = float(mult[yr == y].mean())
        perms = np.empty(N_PERM)
        cur = np.empty_like(mm)
        for k in range(N_PERM):
            for g, blks in group_blocks.items():
                order = rng.permutation(len(blks))
                seq = []
                for b in order:
                    seq.extend(mm[blks[b]])
                for i, v in zip(sorted(groups[g], key=lambda i: keys[i][2]), seq):
                    cur[i] = v
            fm = cur[pos]
            s = 0.0
            for p in PHASES:
                mp = fill_ph == p
                s += float((fill_w[mp] * fm[mp] * fill_y[mp]).sum())
            perms[k] = (s / 4.0) / denom
        pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
        block.append({"year": ANCH[y].date().isoformat(),
                      "actual_norm": round(actual, 6),
                      "p5": round(float(np.quantile(perms, 0.05)), 6),
                      "p50": round(float(np.quantile(perms, 0.50)), 6),
                      "p95": round(float(np.quantile(perms, 0.95)), 6),
                      "percentile": round(float(pct), 2)})
        print(f"block y={y} actual={actual:.6f} "
              f"p5={np.quantile(perms, 0.05):.6f} p50={np.quantile(perms, 0.50):.6f} "
              f"p95={np.quantile(perms, 0.95):.6f} pct={pct:.2f}", flush=True)

    res = {
        "config": {
            "ledger": "oc_k2placebo/tmp/ledger.npz + bt_all.npy read-only (identical build_base)",
            "seed_timing": SEED_TIMING,
            "seed_block": SEED_BLOCK,
            "n_perm": N_PERM,
            "block": BLOCK,
            "rule": "T3 1.25 fav outer quintile / 0.75 unfav / 1 else; "
                    "risk=-f_q10; fits.json per-year dir/q20/q80; missing->1",
            "normalisation": "norm(y)=t3(y)/realised_mean(y); perm norms use the ACTUAL denominator",
            "percentile": "100*(1+#{perm<=actual})/1001; significant iff >=95",
        },
        "reproduction": {"base_sum5y_gate": BASE_GATE,
                         "base_sums": [r["base"] for r in years],
                         "base_sum5y": round(got5, 6),
                         "n_fills": int(n)},
        "per_year": years,
        "timing_placebo": timing,
        "block_placebo": block,
    }
    (HERE / "tmp/placebo_t3.json").write_text(json.dumps(res, indent=1))
    print("wrote tmp/placebo_t3.json", flush=True)


if __name__ == "__main__":
    main()
