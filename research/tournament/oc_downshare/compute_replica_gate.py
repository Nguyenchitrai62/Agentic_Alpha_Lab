"""oc_downshare replica + placebo gate: D1/D2 downside-share tilts on the reused D0+B1 ledger.

Method = copy of research/tournament/oc_voltilt/compute_placebo.py with the
D1 risk (risk_D1, trailing-6d downside share) and D2 risk (risk_D2, HAR-RS
0.6/0.4 daily/weekly blend) instead of RV6/GARCH, plus the IDEAS5 gate:
sum-half (tilt >= base in >= 4/5 years) PLUS dSum5y >= +0.273.
The D0+B1 replica ledger is REUSED read-only from oc_k2placebo/tmp
(ledger.npz + bt_all.npy; identical build_base output, reproduction gate:
n == 22312 and base 4-phase-mean sum5y == 7.718304 +- 0.002). No heavy rebuild.

Per year y: base(y), tilt(y), realised_mean(y), norm(y) = tilt(y)/realised_mean(y).
Timing placebo (supporting): 1000 uniform bar-level permutations of the variant
multipliers over decision bars (seed 20261007+y), normalised by the ACTUAL
realised mean. Block placebo: 42-bar blocks per (sym, shift) (seed 20261008+y).
Percentile = 100*(1+#{perm<=actual})/1001; significant iff >= 95. Focus = Y4.
CPU-only (numpy).
"""
from __future__ import annotations

import json
import sys
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
DSUM_GATE = 0.273
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
PHASES = (0, 1, 2, 3)
VARIANTS = ("D1", "D2")
FEAT_COL = {"D1": "risk_D1", "D2": "risk_D2"}


def phase_mean_sums(ph, yr, wv, yv):
    out = []
    for y in range(5):
        ss = []
        for p in PHASES:
            m = (ph == p) & (yr == y)
            ss.append(float((wv[m] * yv[m]).sum()) if m.any() else 0.0)
        out.append(float(np.mean(ss)))
    return out


def variant_mults(variant, lut, fits_v, ph, yr, co, bt_all, n):
    sys.path.insert(0, str(HERE))
    from tilt_rule import assign_mult  # noqa: E402
    mult = np.ones(n, dtype=float)
    miss = 0
    for i in range(n):
        bt = pd.to_datetime(bt_all[i], utc=True)
        key = (MAJORS[int(co[i])], int(ph[i]), bt)
        q = lut.get(key)
        y = int(yr[i])
        f = fits_v[ANCH5[y]]
        risk = float(q) if q is not None and np.isfinite(q) else float("nan")
        if q is None:
            miss += 1
        mult[i] = assign_mult(risk, f["direction"], f["q20"], f["q80"], 1.25, 0.75)
    return mult, miss


def bar_universe(variant, fits_v):
    feat3 = pd.read_parquet(HERE / "downshare_features_4shift.parquet",
                            columns=["sym", "shift", "T", FEAT_COL[variant]])
    feat3["T"] = pd.to_datetime(feat3["T"], utc=True)
    sys.path.insert(0, str(HERE))
    from tilt_rule import assign_mult  # noqa: E402
    bar_mults, bar_keys_per_year = [], []
    for y in range(5):
        lo_a = ANCH[y]
        hi_a = ANCH[y + 1] if y < 4 else YEAR_END
        sub = feat3[(feat3["T"] >= lo_a) & (feat3["T"] < hi_a)].copy()
        sub = sub.sort_values(["sym", "shift", "T"]).reset_index(drop=True)
        f = fits_v[ANCH5[y]]
        r = sub[FEAT_COL[variant]].to_numpy(dtype=float)
        if f["direction"] > 0:
            mm = np.where(~np.isfinite(r), 1.0,
                          np.where(r >= f["q80"], 1.25,
                                   np.where(r <= f["q20"], 0.75, 1.0)))
        else:
            mm = np.array([assign_mult(v, -1, f["q20"], f["q80"], 1.25, 0.75) for v in r])
        keys = list(zip(sub["sym"].astype(str), sub["shift"].astype(int),
                        pd.to_datetime(sub["T"], utc=True)))
        bar_mults.append(mm.astype(float))
        bar_keys_per_year.append(keys)
    del feat3
    return bar_mults, bar_keys_per_year


def run_variant(variant, fits_v, ph, yr, co, w, yv, bt_all, n):
    col = FEAT_COL[variant]
    feat = pd.read_parquet(HERE / "downshare_features_4shift.parquet",
                           columns=["sym", "shift", "T", col])
    feat["T"] = pd.to_datetime(feat["T"], utc=True)
    lut: dict = {}
    for s, sh, t, q in zip(feat["sym"], feat["shift"], feat["T"], feat[col]):
        lut[(str(s), int(sh), pd.to_datetime(t, utc=True))] = float(q)
    del feat

    mult, miss = variant_mults(variant, lut, fits_v, ph, yr, co, bt_all, n)
    print(f"{variant} join: n={n} missing={miss} mult values={sorted(set(np.round(mult, 6)))}",
          flush=True)

    base_y = phase_mean_sums(ph, yr, w, yv)
    v_y = phase_mean_sums(ph, yr, w * mult, yv)
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
                      variant.lower(): round(float(v_y[y]), 6),
                      "realised_mean": round(rm, 6),
                      "norm": round(float(v_y[y]) / rm, 6) if rm else 0.0})
    for r in years:
        print(f"  {r['year']} n={r['n_fills']} base={r['base']} {variant.lower()}={r[variant.lower()]} "
              f"rm={r['realised_mean']} norm={r['norm']}", flush=True)

    bar_mults, bar_keys_per_year = bar_universe(variant, fits_v)
    bar_pos = []
    for y in range(5):
        keys = bar_keys_per_year[y]
        idx = {k: i for i, k in enumerate(keys)}
        pos = np.full(int((yr == y).sum()), -1, dtype=np.int64)
        fill_idx = np.where(yr == y)[0]
        for j, i in enumerate(fill_idx):
            key = (MAJORS[int(co[i])], int(ph[i]), pd.to_datetime(bt_all[i], utc=True))
            pos[j] = idx.get(key, -1)
        assert (pos >= 0).all(), f"year {y}: {(pos < 0).sum()} fills w/o bar"
        bar_pos.append(pos)
    print(f"bar universes: {[len(b) for b in bar_mults]}", flush=True)

    timing = []
    for y in range(5):
        rng = np.random.default_rng(SEED_TIMING + y)
        mm = bar_mults[y]
        pos = bar_pos[y]
        actual = float(v_y[y]) / float(mult[yr == y].mean())
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
        print(f"timing {variant} y={y} actual={actual:.6f} "
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
        actual = float(v_y[y]) / float(mult[yr == y].mean())
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
        print(f"block {variant} y={y} actual={actual:.6f} "
              f"p5={np.quantile(perms, 0.05):.6f} p50={np.quantile(perms, 0.50):.6f} "
              f"p95={np.quantile(perms, 0.95):.6f} pct={pct:.2f}", flush=True)

    dsum = float(sum(v_y) - sum(base_y))
    sum_ge = sum(1 for y in range(5) if v_y[y] >= base_y[y] - 1e-12)
    return years, timing, block, dsum, sum_ge, base_y, v_y


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

    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    co = led["coin"].astype(int)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)

    res = {
        "config": {
            "ledger": "oc_k2placebo/tmp/ledger.npz + bt_all.npy read-only (identical build_base)",
            "features": "downshare_features_4shift.parquet (D1 trailing-6d downside share; D2 0.6/0.4 daily/weekly blend; returns <= T only)",
            "seed_timing": SEED_TIMING,
            "seed_block": SEED_BLOCK,
            "n_perm": N_PERM,
            "block": BLOCK,
            "rule": "D 1.25 fav outer quintile / 0.75 unfav / 1 else; risk=risk_D1 (D1) or risk_D2 (D2); fits.json per-year dir/q20/q80; missing->1",
            "normalisation": "norm(y)=tilt(y)/realised_mean(y); perm norms use the ACTUAL denominator",
            "percentile": "100*(1+#{perm<=actual})/1001; significant iff >=95",
            "gate": "sum-half (tilt>=base in >=4/5y) PLUS dSum5y>=+0.273; replica DD-half not scored from this ledger (no daily path) — binding DD check is the 4-phase engine",
        },
        "reproduction": {"base_sum5y_gate": BASE_GATE, "n_fills": int(n)},
    }
    for variant in VARIANTS:
        years, timing, block, dsum, sum_ge, base_y, v_y = run_variant(
            variant, fits[variant], ph, yr, co, w, yv, bt_all, n)
        res[variant] = {"per_year": years, "timing_placebo": timing, "block_placebo": block,
                        "dSum5y": round(dsum, 6),
                        "sum_half_years_ge": int(sum_ge),
                        "gate_sum_half": bool(sum_ge >= 4),
                        "gate_dsum": bool(dsum >= DSUM_GATE),
                        "gate_pass": bool(sum_ge >= 4 and dsum >= DSUM_GATE)}
        print(f"{variant}: dSum5y={dsum:.6f} sum_half={sum_ge}/5 gate_pass={res[variant]['gate_pass']}",
              flush=True)
    (HERE / "tmp/replica_downshare.json").write_text(json.dumps(res, indent=1))
    print("wrote tmp/replica_downshare.json", flush=True)


if __name__ == "__main__":
    main()
