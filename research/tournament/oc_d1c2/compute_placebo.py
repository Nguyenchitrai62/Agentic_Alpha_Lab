"""oc_d1c2 timing placebo: AVG + AGREE ensemble timing vs random timing.

Method = exact copy of research/tournament/oc_chronos/compute_placebo.py with
the AVG (resp. AGREE) ensemble multiplier instead of C2. The D0+B1 replica
ledger is REUSED read-only from oc_k2placebo/tmp (ledger.npz + bt_all.npy;
reproduction gate: n == 22312 and base 4-phase-mean sum5y == 7.718304 +- 0.002).

Per year y: base(y), ens(y), realised_mean(y), norm(y) = ens(y)/realised_mean(y).
Timing placebo (primary): 1000 uniform bar-level permutations of the ensemble
multipliers over decision bars (seed 20261007+y), normalised by the ACTUAL
realised mean. Block placebo: 42-bar blocks per (sym, shift) (seed 20261008+y).
Percentile = 100*(1+#{perm<=actual})/1001; significant iff >= 95.
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
DS = ROOT / "research/tournament/oc_downshare"
CH = ROOT / "research/tournament/oc_chronos"
K2P = ROOT / "research/tournament/oc_k2placebo"

sys.path.insert(0, str(HERE))
from tilt_rule import assign_mult, ensemble_agree, ensemble_avg  # noqa: E402

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


def build_ens_mult(variant):
    """Per-fill ensemble multipliers on the reused ledger (frozen fits)."""
    led = dict(np.load(K2P / "tmp/ledger.npz"))
    for k in ("phase", "coin", "year", "bar_time", "rung"):
        led[k] = led[k].astype(np.int64)
    for k in ("w", "y10"):
        led[k] = led[k].astype(np.float64)
    bt_all = np.load(K2P / "tmp/bt_all.npy", allow_pickle=True)
    n = len(led["w"])
    assert n == N_GATE, f"ledger size {n} != {N_GATE}"

    fits_d1 = json.loads((DS / "fits.json").read_text())["D1"]
    fits_c2 = json.loads((CH / "fits.json").read_text())
    feat_d = pd.read_parquet(DS / "downshare_features_4shift.parquet",
                             columns=["sym", "shift", "T", "risk_D1"])
    lut_d = {(str(s), int(sh), pd.Timestamp(t)): float(r)
             for s, sh, t, r in zip(feat_d["sym"], feat_d["shift"], feat_d["T"], feat_d["risk_D1"])}
    del feat_d
    feat_c = pd.read_parquet(CH / "chronos_features_4shift.parquet",
                             columns=["sym", "shift", "T", "ch_q10"])
    lut_c = {(str(s), int(sh), pd.Timestamp(t)): float(q)
             for s, sh, t, q in zip(feat_c["sym"], feat_c["shift"], feat_c["T"], feat_c["ch_q10"])}
    del feat_c

    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    co = led["coin"].astype(int)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)
    bt_ord = led["bar_time"].astype(np.int64)
    START = pd.Timestamp("2020-08-01", tz="UTC")

    mult = np.ones(n, dtype=float)
    miss = 0
    for i in range(n):
        bt = START + pd.Timedelta(minutes=int(bt_ord[i]))
        key = (MAJORS[int(co[i])], int(ph[i]), bt)
        rd = lut_d.get(key)
        q = lut_c.get(key)
        y = int(yr[i])
        f1 = fits_d1[ANCH5[y]]
        f2 = fits_c2[ANCH5[y]]
        risk_d = float(rd) if rd is not None and np.isfinite(rd) else float("nan")
        risk_c = -q if q is not None and np.isfinite(q) else float("nan")
        if rd is None or q is None:
            miss += 1
        m1 = assign_mult(risk_d, f1["direction"], f1["q20"], f1["q80"], 1.25, 0.75)
        m2 = assign_mult(risk_c, f2["direction"], f2["q20"], f2["q80"], 1.25, 0.75)
        mult[i] = ensemble_avg(m1, m2) if variant == "AVG" else ensemble_agree(m1, m2)
    print(f"{variant} join: n={n} missing={miss} values={sorted(set(np.round(mult, 6)))}", flush=True)
    return led, bt_all, mult


def bar_universe(variant):
    """Per-year decision-bar multiplier arrays + fill->bar positions."""
    fits_d1 = json.loads((DS / "fits.json").read_text())["D1"]
    fits_c2 = json.loads((CH / "fits.json").read_text())
    feat_d = pd.read_parquet(DS / "downshare_features_4shift.parquet",
                             columns=["sym", "shift", "T", "risk_D1"])
    feat_c = pd.read_parquet(CH / "chronos_features_4shift.parquet",
                             columns=["sym", "shift", "T", "ch_q10"])
    j = feat_d.merge(feat_c, on=["sym", "shift", "T"], how="inner")
    del feat_d, feat_c
    j["T"] = pd.to_datetime(j["T"], utc=True)
    led = dict(np.load(K2P / "tmp/ledger.npz"))
    bt_all = np.load(K2P / "tmp/bt_all.npy", allow_pickle=True)
    yr = led["year"].astype(int)
    ph = led["phase"].astype(int)
    co = led["coin"].astype(int)

    bar_mults, bar_keys, bar_pos = [], [], []
    for y in range(5):
        lo_a = ANCH[y]
        hi_a = ANCH[y + 1] if y < 4 else YEAR_END
        sub = j[(j["T"] >= lo_a) & (j["T"] < hi_a)].copy()
        sub = sub.sort_values(["sym", "shift", "T"]).reset_index(drop=True)
        f1 = fits_d1[ANCH5[y]]
        f2 = fits_c2[ANCH5[y]]
        mm = np.empty(len(sub))
        for i, r in enumerate(sub.itertuples()):
            rd = float(r.risk_D1)
            q = float(r.ch_q10)
            rc = -q if np.isfinite(q) else float("nan")
            m1 = assign_mult(rd, f1["direction"], f1["q20"], f1["q80"], 1.25, 0.75)
            m2 = assign_mult(rc, f2["direction"], f2["q20"], f2["q80"], 1.25, 0.75)
            mm[i] = ensemble_avg(m1, m2) if variant == "AVG" else ensemble_agree(m1, m2)
        keys = list(zip(sub["sym"].astype(str), sub["shift"].astype(int),
                        pd.to_datetime(sub["T"], utc=True)))
        idx = {k: i for i, k in enumerate(keys)}
        bar_mults.append(mm.astype(float))
        bar_keys.append(keys)
        pos = np.full(int((yr == y).sum()), -1, dtype=np.int64)
        for jj, i in enumerate(np.where(yr == y)[0]):
            key = (MAJORS[int(co[i])], int(ph[i]), pd.Timestamp(bt_all[i]))
            pos[jj] = idx.get(key, -1)
        assert (pos >= 0).all(), f"{variant} year {y}: {(pos < 0).sum()} fills w/o bar"
        bar_pos.append(pos)
    print(f"{variant} bar universes: {[len(b) for b in bar_mults]}", flush=True)
    return bar_mults, bar_keys, bar_pos


def run_variant(variant):
    led, bt_all, mult = build_ens_mult(variant)
    _ = bt_all
    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)

    base_y = phase_mean_sums(ph, yr, w, yv)
    ens_y = phase_mean_sums(ph, yr, w * mult, yv)
    got5 = float(sum(base_y))
    print(f"{variant} base sums={[round(v, 6) for v in base_y]} sum5y={got5:.6f}", flush=True)
    assert abs(got5 - BASE_GATE) <= 0.002, f"base {got5} != {BASE_GATE}"
    years = []
    for y in range(5):
        m = yr == y
        rmv = float(mult[m].mean()) if m.any() else 1.0
        years.append({"year": ANCH[y].date().isoformat(),
                      "n_fills": int(m.sum()),
                      "base": round(float(base_y[y]), 6),
                      "ens": round(float(ens_y[y]), 6),
                      "realised_mean": round(rmv, 6),
                      "norm": round(float(ens_y[y]) / rmv, 6) if rmv else 0.0})
        print(f"  {years[-1]}", flush=True)

    bar_mults, bar_keys, bar_pos = bar_universe(variant)

    timing = []
    for y in range(5):
        rng = np.random.default_rng(SEED_TIMING + y)
        mm = bar_mults[y]
        pos = bar_pos[y]
        actual = float(ens_y[y]) / float(mult[yr == y].mean())
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
        print(f"{variant} timing y={y} actual={actual:.6f} pct={pct:.2f}", flush=True)

    block = []
    for y in range(5):
        rng = np.random.default_rng(SEED_BLOCK + y)
        keys = bar_keys[y]
        mm = bar_mults[y]
        groups: dict = {}
        for i, k in enumerate(keys):
            groups.setdefault((k[0], k[1]), []).append(i)
        group_blocks = {}
        for g, idxs in groups.items():
            idxs = sorted(idxs, key=lambda i: keys[i][2])
            group_blocks[g] = [idxs[b:b + BLOCK] for b in range(0, len(idxs), BLOCK)]
        pos = bar_pos[y]
        actual = float(ens_y[y]) / float(mult[yr == y].mean())
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
        print(f"{variant} block y={y} actual={actual:.6f} pct={pct:.2f}", flush=True)

    res = {"config": {"ledger": "oc_k2placebo/tmp/ledger.npz + bt_all.npy read-only",
                       "seed_timing": SEED_TIMING, "seed_block": SEED_BLOCK,
                       "n_perm": N_PERM, "block": BLOCK,
                       "rule": f"{variant} of frozen D1xC2 legs (1.25/0.75); missing->1",
                       "normalisation": "norm(y)=ens(y)/realised_mean(y); perm norms use ACTUAL denominator",
                       "percentile": "100*(1+#{perm<=actual})/1001; significant iff >=95"},
           "reproduction": {"base_sum5y_gate": BASE_GATE, "base_sums": [r["base"] for r in years],
                            "base_sum5y": round(got5, 6)},
           "per_year": years, "timing_placebo": timing, "block_placebo": block}
    out = HERE / f"tmp/placebo_{variant.lower()}.json"
    out.write_text(json.dumps(res, indent=1))
    print(f"wrote {out}", flush=True)


def main() -> None:
    for variant in ("AVG", "AGREE"):
        run_variant(variant)


if __name__ == "__main__":
    main()
