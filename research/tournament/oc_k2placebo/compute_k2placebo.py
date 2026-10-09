"""oc_k2placebo: is the K2 dip tilt's post-release gain distinguishable from random timing?

Pre-registered in PLAN.md (read it first). Diagnostic only.

Pipeline:
  1. rebuild the oc_placebo_dip D0+B1 4-phase replica verbatim (build_base),
     gate on base_sum5y == 7.718304 +- 0.002, n == 22312.
  2. join each rung fill's (sym, shift=phase, T=bar open) to
     oc_kronoshidden kronos_features_4shift.low1, assign the K2 multiplier
     (hi/lo 1.25/0.75, fits.json per-year direction/q20/q80, missing -> 1).
  3. per year 4-phase-mean base sum, K2 sum, realised mean, normalised sum.
  4. timing placebo: 1000 uniform bar-level permutations of K2 multipliers
     within each year (seed 20261007+y). block placebo: 1000 permutations in
     blocks of 42 consecutive bars per (sym, shift) within each year
     (seed 20261008+y). Percentile = 100*(1+#{perm<=actual})/1001.

Usage (heavy rebuild through the shared semaphore):
  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_k2placebo \\
    --min-free-gb 2.0 -- .venv/Scripts/python.exe \\
    research/tournament/oc_k2placebo/compute_k2placebo.py
  .venv/Scripts/python.exe research/tournament/oc_k2placebo/compute_k2placebo.py --permutations-only  # light re-run, needs tmp/ledger.npz
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TMP = HERE / "tmp"
KH = ROOT / "research/tournament/oc_kronoshidden"
PDIP = ROOT / "research/tournament/oc_placebo_dip"

sys.path.insert(0, str(PDIP))

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
ANCH = [pd.Timestamp(a, tz="UTC") for a in ANCH5]
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
START = pd.Timestamp("2020-08-01", tz="UTC")
SEED_TIMING = 20261007
SEED_BLOCK = 20261008
N_PERM = 1000
BLOCK = 42
BASE_GATE = 7.718304
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
PHASES = (0, 1, 2, 3)


def assign_mult(risk: float, direction: int, q20: float, q80: float,
                hi: float = 1.25, lo: float = 0.75) -> float:
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


def year_of(t) -> int | None:
    t = pd.Timestamp(t)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    for i in range(5):
        lo = ANCH[i]
        hi = ANCH[i + 1] if i < 4 else YEAR_END
        if lo <= t < hi:
            return i
    return None


def phase_mean_sums(ph, yr, wv, yv):
    """Per-year 4-phase-mean sums (same as compute_placebo_dip scoring)."""
    out = []
    for y in range(5):
        ss = []
        for p in PHASES:
            m = (ph == p) & (yr == y)
            ss.append(float((wv[m] * yv[m]).sum()) if m.any() else 0.0)
        out.append(float(np.mean(ss)))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--permutations-only", action="store_true",
                    help="skip heavy rebuild; load tmp/ledger.npz + tmp/mult.npy")
    ap.add_argument("--n-perm", type=int, default=N_PERM)
    args = ap.parse_args()
    TMP.mkdir(parents=True, exist_ok=True)
    n_perm = int(args.n_perm)

    import compute_placebo_dip as cpd  # noqa: E402  (read-only import)

    if args.permutations_only:
        led = dict(np.load(TMP / "ledger.npz"))
        for k in ("phase", "coin", "year", "bar_time", "rung"):
            led[k] = led[k].astype(np.int64)
        for k in ("w", "y10"):
            led[k] = led[k].astype(np.float64)
        mult = np.load(TMP / "mult.npy")
        bt_all = np.load(TMP / "bt_all.npy", allow_pickle=True)
        print(f"loaded ledger n={len(led['w'])} mult n={len(mult)}", flush=True)
    else:
        led = cpd.build_base()
        n = len(led["w"])
        print(f"ledger fills={n}", flush=True)
        base_sc = cpd.score_assignment(led["phase"], led["year"], led["w"],
                                       led["y10"], led["d10"])
        got5 = float(sum(r["S"] for r in base_sc["per_year"]))
        print(f"base 4-phase-mean sums={[round(r['S'], 6) for r in base_sc['per_year']]} sum5y={got5:.6f}", flush=True)
        assert n == 22312, f"ledger size {n} != 22312"
        assert abs(got5 - BASE_GATE) <= 0.002, f"base {got5} != {BASE_GATE}"
        np.savez_compressed(TMP / "ledger.npz",
                            phase=led["phase"], coin=led["coin"],
                            year=led["year"], bar_time=led["bar_time"],
                            rung=led["rung"], w=led["w"], y10=led["y10"])
        print("ledger saved to tmp/ledger.npz", flush=True)

        # ---- K2 join ----
        fits = json.loads((KH / "fits.json").read_text())
        feat = pd.read_parquet(KH / "kronos_features_4shift.parquet",
                               columns=["sym", "shift", "T", "low1"])
        lut: dict = {}
        for s, sh, t, lo in zip(feat["sym"], feat["shift"], feat["T"],
                                feat["low1"]):
            lut[(str(s), int(sh), pd.Timestamp(t))] = float(lo)
        del feat
        ph = led["phase"].astype(int)
        yr = led["year"].astype(int)
        co = led["coin"].astype(int)
        bt_ord = led["bar_time"].astype(np.int64)
        mult = np.ones(n, dtype=float)
        bt_all = np.empty(n, dtype=object)
        miss = 0
        for i in range(n):
            bt = START + pd.Timedelta(minutes=int(bt_ord[i]))
            bt_all[i] = bt
            key = (MAJORS[int(co[i])], int(ph[i]), bt)
            lo = lut.get(key)
            y = int(yr[i])
            f = fits[ANCH5[y]]
            risk = -lo if lo is not None and np.isfinite(lo) else float("nan")
            if lo is None:
                miss += 1
            mult[i] = assign_mult(risk, f["direction"], f["q20"], f["q80"])
        print(f"K2 join: n={n} missing={miss} "
              f"mult values={sorted(set(np.round(mult, 6)))}", flush=True)
        np.save(TMP / "mult.npy", mult)
        np.save(TMP / "bt_all.npy", bt_all)
        print("mult saved", flush=True)

    fits = json.loads((KH / "fits.json").read_text())
    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    co = led["coin"].astype(int)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)
    if "bt_all" not in dir():
        bt_all = np.load(TMP / "bt_all.npy", allow_pickle=True)
    if "mult" not in dir():
        mult = np.load(TMP / "mult.npy")

    # ---- per-year base / K2 / normalised ----
    base_y = phase_mean_sums(ph, yr, w, yv)
    k2_y = phase_mean_sums(ph, yr, w * mult, yv)
    years = []
    for y in range(5):
        m = yr == y
        rm = float(mult[m].mean()) if m.any() else 1.0
        years.append({"year": ANCH[y].date().isoformat(),
                      "n_fills": int(m.sum()),
                      "base": round(float(base_y[y]), 6),
                      "k2": round(float(k2_y[y]), 6),
                      "realised_mean": round(rm, 6),
                      "norm": round(float(k2_y[y]) / rm, 6) if rm else 0.0})
    print("per-year (base/k2/realmean/norm):", flush=True)
    for r in years:
        print(f"  {r['year']} n={r['n_fills']} base={r['base']} k2={r['k2']} "
              f"rm={r['realised_mean']} norm={r['norm']}", flush=True)

    # decision means (diagnostic): all feature rows with T open in year y
    feat2 = pd.read_parquet(KH / "kronos_features_4shift.parquet",
                            columns=["sym", "shift", "T", "low1"])
    dec_mean, dec_n = [], []
    for y in range(5):
        lo_a = ANCH[y]
        hi_a = ANCH[y + 1] if y < 4 else YEAR_END
        sub = feat2[(feat2["T"] >= lo_a) & (feat2["T"] < hi_a)]
        f = fits[ANCH5[y]]
        r = -sub["low1"].to_numpy(dtype=float)
        mm = np.where(~np.isfinite(r), 1.0,
                      np.where(r >= f["q80"], 1.25,
                               np.where(r <= f["q20"], 0.75, 1.0)))
        # direction is +1 for all anchors; generic path matches assign_mult
        if f["direction"] <= 0:
            mm = np.array([assign_mult(v, -1, f["q20"], f["q80"])
                           for v in r])
        dec_mean.append(round(float(mm.mean()), 6))
        dec_n.append(int(len(mm)))
    del feat2
    print(f"decision means K2: {dec_mean} n={dec_n}", flush=True)

    # ---- build bar-level decision tables per year for permutations ----
    feat3 = pd.read_parquet(KH / "kronos_features_4shift.parquet",
                            columns=["sym", "shift", "T", "low1"])
    bar_pos = []  # per fill: index into its year's bar array
    bar_mults = []  # per year: mult array over decision bars
    bar_keys_per_year = []
    for y in range(5):
        lo_a = ANCH[y]
        hi_a = ANCH[y + 1] if y < 4 else YEAR_END
        sub = feat3[(feat3["T"] >= lo_a) & (feat3["T"] < hi_a)].copy()
        sub = sub.sort_values(["sym", "shift", "T"]).reset_index(drop=True)
        f = fits[ANCH5[y]]
        r = -sub["low1"].to_numpy(dtype=float)
        mm = np.where(~np.isfinite(r), 1.0,
                      np.where(r >= f["q80"], 1.25,
                               np.where(r <= f["q20"], 0.75, 1.0)))
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

    # ---- timing placebo ----
    timing = []
    for y in range(5):
        rng = np.random.default_rng(SEED_TIMING + y)
        mm = bar_mults[y]
        pos = bar_pos[y]
        actual = float(k2_y[y]) / float(mult[yr == y].mean())
        fill_w = w[yr == y]
        fill_y = yv[yr == y]
        fill_ph = ph[yr == y]
        perms = np.empty(n_perm)
        for k in range(n_perm):
            pm = rng.permutation(mm)
            fm = pm[pos]
            s = 0.0
            for p in PHASES:
                mp = fill_ph == p
                s += float((fill_w[mp] * fm[mp] * fill_y[mp]).sum())
            perms[k] = (s / 4.0) / float(mult[yr == y].mean())
        pct = 100.0 * (1 + int((perms <= actual).sum())) / (n_perm + 1)
        timing.append({"year": ANCH[y].date().isoformat(),
                       "actual_norm": round(actual, 6),
                       "p5": round(float(np.quantile(perms, 0.05)), 6),
                       "p50": round(float(np.quantile(perms, 0.50)), 6),
                       "p95": round(float(np.quantile(perms, 0.95)), 6),
                       "percentile": round(float(pct), 2),
                       "perms": [round(float(v), 6) for v in perms]})
        print(f"timing y={y} actual={actual:.6f} "
              f"p5={np.quantile(perms, 0.05):.6f} p50={np.quantile(perms, 0.50):.6f} "
              f"p95={np.quantile(perms, 0.95):.6f} pct={pct:.2f}", flush=True)

    # ---- block placebo (42-bar blocks per (sym, shift)) ----
    block = []
    for y in range(5):
        rng = np.random.default_rng(SEED_BLOCK + y)
        keys = bar_keys_per_year[y]
        mm = bar_mults[y]
        # group indices per (sym, shift) in T order (keys already sorted)
        groups: dict = {}
        for i, k in enumerate(keys):
            groups.setdefault((k[0], k[1]), []).append(i)
        # block structure per group: list of lists of bar positions
        group_blocks = {}
        for g, idxs in groups.items():
            idxs = sorted(idxs, key=lambda i: keys[i][2])
            group_blocks[g] = [idxs[b:b + BLOCK]
                               for b in range(0, len(idxs), BLOCK)]
        pos = bar_pos[y]
        actual = float(k2_y[y]) / float(mult[yr == y].mean())
        fill_w = w[yr == y]
        fill_y = yv[yr == y]
        fill_ph = ph[yr == y]
        denom = float(mult[yr == y].mean())
        perms = np.empty(n_perm)
        cur = np.empty_like(mm)
        for k in range(n_perm):
            for g, blks in group_blocks.items():
                order = rng.permutation(len(blks))
                dst = 0
                # rebuild group's mult sequence in permuted block order
                seq = []
                for b in order:
                    seq.extend(mm[blks[b]])
                for i, v in zip(sorted(groups[g],
                                       key=lambda i: keys[i][2]), seq):
                    cur[i] = v
            fm = cur[pos]
            s = 0.0
            for p in PHASES:
                mp = fill_ph == p
                s += float((fill_w[mp] * fm[mp] * fill_y[mp]).sum())
            perms[k] = (s / 4.0) / denom
        pct = 100.0 * (1 + int((perms <= actual).sum())) / (n_perm + 1)
        block.append({"year": ANCH[y].date().isoformat(),
                      "actual_norm": round(actual, 6),
                      "p5": round(float(np.quantile(perms, 0.05)), 6),
                      "p50": round(float(np.quantile(perms, 0.50)), 6),
                      "p95": round(float(np.quantile(perms, 0.95)), 6),
                      "percentile": round(float(pct), 2),
                      "perms": [round(float(v), 6) for v in perms]})
        print(f"block y={y} actual={actual:.6f} "
              f"p5={np.quantile(perms, 0.05):.6f} p50={np.quantile(perms, 0.50):.6f} "
              f"p95={np.quantile(perms, 0.95):.6f} pct={pct:.2f}", flush=True)

    res = {
        "config": {
            "seed_timing": SEED_TIMING,
            "seed_block": SEED_BLOCK,
            "n_perm": n_perm,
            "block": BLOCK,
            "rule": "K2 1.25 fav outer quintile / 0.75 unfav / 1 else; "
                    "risk=-low1; fits.json per-year dir/q20/q80; missing->1",
            "replica": "compute_placebo_dip.build_base verbatim; w*y 4-phase mean",
            "normalisation": "norm(y)=k2(y)/realised_mean(y); realised_mean = "
                             "mean K2 mult over fills in year y; perm norms use "
                             "the ACTUAL denominator (constant per year)",
            "percentile": "100*(1+#{perm<=actual})/1001; significant iff >=95",
        },
        "reproduction": {"base_sum5y_gate": BASE_GATE,
                         "base_sums": [r["base"] for r in years],
                         "base_sum5y": round(float(sum(r["base"] for r in years)), 6),
                         "n_fills": int(len(w))},
        "per_year": years,
        "decision_mean_K2": [{"year": ANCH[y].date().isoformat(),
                              "mean": dec_mean[y], "n": dec_n[y]}
                             for y in range(5)],
        "timing_placebo": timing,
        "block_placebo": block,
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print("wrote results.json", flush=True)


if __name__ == "__main__":
    main()
