"""oc_crashgate replica + placebo gate: gated C2 tilt on the reused D0+B1 ledger.

Method = copy of research/tournament/oc_chronos/compute_placebo.py with the
CRASH-gated multipliers:
  base = C2 mult (risk = -ch_q10, frozen oc_chronos fits.json; hi/lo 1.25/0.75,
    missing -> 1); gated = base if trailing-30d BTC depth(shift,T) < X else 1.0.
  V1 X = 0.15; V2 X = 0.10 (frozen, never fit).
Depth (read-only crash_depth_4shift.parquet from build_crash.py): exact match on
  (shift, T), fallback to latest grid time <= T (ffill, causal); NaN -> allow.
Ledger REUSED read-only from oc_k2placebo/tmp (ledger.npz + bt_all.npy;
  reproduction gate: n == 22312 and base 4-phase-mean sum5y == 7.718304 +- 0.002).

Per year y: base(y), gated(y), realised_mean(y), norm(y) = gated(y)/realised_mean.
Gate (IDEAS5 header): sum-half (gated >= base in >= 4/5 years) PLUS
  dSum5y >= +0.273. Timing/block placebo (1000 perms, seeds 20261007+y /
  20261008+y, percentile = 100*(1+#{perm<=actual})/1001, signif iff >= 95)
  reported as supporting evidence. CPU-only (numpy).
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
CH = ROOT / "research/tournament/oc_chronos"

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
VARIANTS = {"V1": 0.15, "V2": 0.10}

sys.path.insert(0, str(HERE))
from tilt_rule import assign_mult, gate_mult  # noqa: E402


def phase_mean_sums(ph, yr, wv, yv):
    out = []
    for y in range(5):
        ss = []
        for p in PHASES:
            m = (ph == p) & (yr == y)
            ss.append(float((wv[m] * yv[m]).sum()) if m.any() else 0.0)
        out.append(float(np.mean(ss)))
    return out


def load_depth_lut():
    d = pd.read_parquet(HERE / "crash_depth_4shift.parquet",
                        columns=["shift", "T", "depth"])
    d["T"] = pd.to_datetime(d["T"], utc=True)
    exact = {}
    per_shift = {}
    for sh in PHASES:
        sub = d[d["shift"] == sh].sort_values("T")
        t_ns = sub["T"].values.astype("datetime64[ns]").astype(np.int64)
        v = sub["depth"].to_numpy(dtype=float)
        per_shift[sh] = (t_ns, v)
        for t, dd in zip(sub["T"], v):
            exact[(int(sh), pd.Timestamp(t))] = float(dd)
    del d
    return exact, per_shift


def depth_at(shift, t, exact, per_shift):
    key = (int(shift), pd.Timestamp(t))
    dd = exact.get(key)
    if dd is not None:
        return float(dd)
    t_ns, v = per_shift[int(shift)]
    q = pd.Timestamp(t)
    if q.tzinfo is None:
        q = q.tz_localize("UTC")
    pos = int(np.searchsorted(t_ns, np.int64(q.value), side="right")) - 1
    if pos < 0:
        return float("nan")
    return float(v[pos])


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

    fits = json.loads((CH / "fits.json").read_text())
    feat = pd.read_parquet(CH / "chronos_features_4shift.parquet",
                           columns=["sym", "shift", "T", "ch_q10"])
    lut = {}
    for s, sh, t, q in zip(feat["sym"], feat["shift"], feat["T"], feat["ch_q10"]):
        lut[(str(s), int(sh), pd.Timestamp(t))] = float(q)
    del feat

    exact, per_shift = load_depth_lut()

    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    co = led["coin"].astype(int)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)

    base_y = phase_mean_sums(ph, yr, w, yv)
    got5 = float(sum(base_y))
    print(f"base 4-phase-mean sums={[round(v, 6) for v in base_y]} sum5y={got5:.6f}", flush=True)
    assert abs(got5 - BASE_GATE) <= 0.002, f"base {got5} != {BASE_GATE}"

    res = {
        "config": {
            "ledger": "oc_k2placebo/tmp/ledger.npz + bt_all.npy read-only (identical build_base)",
            "depth": "crash_depth_4shift.parquet (BTC 4h closes, trailing-30d max peak-to-trough, closes <= T only)",
            "seed_timing": SEED_TIMING,
            "seed_block": SEED_BLOCK,
            "n_perm": N_PERM,
            "block": BLOCK,
            "rule": "gated C2 1.25 fav outer quintile / 0.75 unfav / 1 else; risk=-ch_q10; frozen fits; depth<X else 1 (V1 X=0.15, V2 X=0.10)",
            "normalisation": "norm(y)=gated(y)/realised_mean(y); perm norms use the ACTUAL denominator",
            "percentile": "100*(1+#{perm<=actual})/1001; significant iff >=95",
            "gate": "sum-half (gated>=base in >=4/5y) PLUS dSum5y>=+0.273; replica DD-half not scored from this ledger (no daily path) — binding DD check is the 4-phase engine",
        },
        "reproduction": {"base_sum5y_gate": BASE_GATE, "base_sums": [round(v, 6) for v in base_y],
                         "base_sum5y": round(got5, 6), "n_fills": int(n)},
    }

    for variant, x in VARIANTS.items():
        mult = np.ones(n, dtype=float)
        allow = np.zeros(n, dtype=bool)
        miss = 0
        for i in range(n):
            bt = pd.Timestamp(bt_all[i])
            key = (MAJORS[int(co[i])], int(ph[i]), bt)
            q = lut.get(key)
            y = int(yr[i])
            f = fits[ANCH5[y]]
            risk = -q if q is not None and np.isfinite(q) else float("nan")
            if q is None:
                miss += 1
            m0 = assign_mult(risk, f["direction"], f["q20"], f["q80"], 1.25, 0.75)
            dd = depth_at(int(ph[i]), bt, exact, per_shift)
            allow[i] = (not np.isfinite(dd)) or (dd < x)
            mult[i] = gate_mult(m0, dd, x)
        print(f"{variant} (X={x}): join n={n} missing={miss} "
              f"mult values={sorted(set(np.round(mult, 6)))} "
              f"allow_share={float(allow.mean()):.4f}", flush=True)

        gated_y = phase_mean_sums(ph, yr, w * mult, yv)
        dsum = float(sum(gated_y) - sum(base_y))
        sum_ge = sum(1 for y in range(5) if gated_y[y] >= base_y[y] - 1e-12)
        years = []
        for y in range(5):
            m = yr == y
            rm = float(mult[m].mean()) if m.any() else 1.0
            base_rm_note = None
            years.append({"year": ANCH[y].date().isoformat(),
                          "n_fills": int(m.sum()),
                          "base": round(float(base_y[y]), 6),
                          "gated": round(float(gated_y[y]), 6),
                          "realised_mean": round(rm, 6),
                          "norm": round(float(gated_y[y]) / rm, 6) if rm else 0.0,
                          "allow_share_fills": round(float(allow[m].mean()), 4) if m.any() else None})
        for r in years:
            print(f"  {r['year']} n={r['n_fills']} base={r['base']} gated={r['gated']} "
                  f"rm={r['realised_mean']} norm={r['norm']} allow={r['allow_share_fills']}", flush=True)
        print(f"{variant}: dSum5y={dsum:.6f} (gate >= {DSUM_GATE}); "
              f"sum-half years>=base: {sum_ge}/5", flush=True)

        # ---- bar universe with gated mults (for placebo + bars allow-share) ----
        feat3 = pd.read_parquet(CH / "chronos_features_4shift.parquet",
                                columns=["sym", "shift", "T", "ch_q10"])
        bar_mults, bar_keys_per_year, bar_allow_share = [], [], []
        for y in range(5):
            lo_a = ANCH[y]
            hi_a = ANCH[y + 1] if y < 4 else YEAR_END
            sub = feat3[(feat3["T"] >= lo_a) & (feat3["T"] < hi_a)].copy()
            sub = sub.sort_values(["sym", "shift", "T"]).reset_index(drop=True)
            f = fits[ANCH5[y]]
            r = -sub["ch_q10"].to_numpy(dtype=float)
            if f["direction"] > 0:
                mm0 = np.where(~np.isfinite(r), 1.0,
                               np.where(r >= f["q80"], 1.25,
                                        np.where(r <= f["q20"], 0.75, 1.0)))
            else:
                mm0 = np.array([assign_mult(v, -1, f["q20"], f["q80"], 1.25, 0.75) for v in r])
            dd_arr = np.array([depth_at(int(sh), t, exact, per_shift)
                               for sh, t in zip(sub["shift"].to_numpy(),
                                                pd.to_datetime(sub["T"], utc=True))])
            allow_b = ~np.isfinite(dd_arr) | (dd_arr < x)
            mm = np.where(allow_b, mm0, 1.0)
            keys = list(zip(sub["sym"].astype(str), sub["shift"].astype(int),
                            pd.to_datetime(sub["T"], utc=True)))
            bar_mults.append(mm.astype(float))
            bar_keys_per_year.append(keys)
            bar_allow_share.append(round(float(allow_b.mean()), 4))
        del feat3
        print(f"bar universes: {[len(b) for b in bar_mults]} allow={bar_allow_share}", flush=True)

        bar_pos = []
        for y in range(5):
            keys = bar_keys_per_year[y]
            idx = {k: i for i, k in enumerate(keys)}
            pos = np.full(int((yr == y).sum()), -1, dtype=np.int64)
            fill_idx = np.where(yr == y)[0]
            for j, i in enumerate(fill_idx):
                key = (MAJORS[int(co[i])], int(ph[i]), pd.Timestamp(bt_all[i]))
                pos[j] = idx.get(key, -1)
            assert (pos >= 0).all(), f"year {y}: {(pos < 0).sum()} fills w/o bar"
            bar_pos.append(pos)

        timing = []
        for y in range(5):
            rng = np.random.default_rng(SEED_TIMING + y)
            mm = bar_mults[y]
            pos = bar_pos[y]
            actual = float(gated_y[y]) / float(mult[yr == y].mean())
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
            actual = float(gated_y[y]) / float(mult[yr == y].mean())
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

        res[variant] = {"X": x, "per_year": years, "timing_placebo": timing,
                        "block_placebo": block,
                        "dSum5y": round(dsum, 6),
                        "sum_half_years_ge": int(sum_ge),
                        "gate_sum_half": bool(sum_ge >= 4),
                        "gate_dsum": bool(dsum >= DSUM_GATE),
                        "gate_pass": bool(sum_ge >= 4 and dsum >= DSUM_GATE),
                        "bars_allow_share": bar_allow_share}

    (HERE / "tmp/placebo_crashgate.json").write_text(json.dumps(res, indent=1))
    print("wrote tmp/placebo_crashgate.json", flush=True)
    for variant in VARIANTS:
        r = res[variant]
        print(f"{variant}: dSum5y={r['dSum5y']} sum_half={r['sum_half_years_ge']}/5 "
              f"gate_pass={r['gate_pass']}", flush=True)


if __name__ == "__main__":
    main()
