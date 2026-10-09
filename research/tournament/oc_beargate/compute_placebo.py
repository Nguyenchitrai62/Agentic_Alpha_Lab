"""oc_beargate timing placebo: is the GATED tilt gain distinguishable from random timing?

Method = exact copy of research/tournament/oc_voltilt/compute_placebo.py
with the GATED multipliers:
  C2_B: base = C2 mult (risk = -ch_q10, oc_chronos fits.json), gated to 1 when bear.
  GARCH_B: base = V_GARCH mult (risk = risk_GARCH, oc_voltilt fits.json V_GARCH),
  gated to 1 when bear.
Bear = exact v421 series (v421_gross_cap.py:70) ffilled <= each bar/fill T.
The D0+B1 replica ledger is REUSED read-only from oc_k2placebo/tmp
(ledger.npz + bt_all.npy; identical build_base output, reproduction gate:
n == 22312 and base 4-phase-mean sum5y == 7.718304 +- 0.002). No heavy rebuild.

Per year y: base(y), v(y), realised_mean(y), norm(y) = v(y)/realised_mean(y).
Timing placebo (primary): 1000 uniform bar-level permutations of the GATED
multipliers over decision bars (seed 20261007+y), normalised by the ACTUAL
realised mean. Block placebo: 42-bar blocks per (sym, shift) (seed 20261008+y).
Percentile = 100*(1+#{perm<=actual})/1001; significant iff >= 95.
CPU-only (numpy).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
K2P = ROOT / "research/tournament/oc_k2placebo"
CH = ROOT / "research/tournament/oc_chronos"
VT = ROOT / "research/tournament/oc_voltilt"

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
VARIANTS = ("C2_B", "GARCH_B")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_bear():
    er = _load("er_bg_placebo", ROOT / "research/parallel/rounds/parallel-20260906-r2/engine_real/engine_real.py")
    books, opens = er.v154_books()
    btc = opens["BTCUSDT"].reindex(books.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).fillna(False).to_numpy(dtype=bool)
    idx_ns = books.index.values.astype("datetime64[ns]").astype(np.int64)
    order = np.argsort(idx_ns)
    return idx_ns[order], bear[order]


def bear_at_vec(bidx_ns, bval, ask_ns):
    pos = np.searchsorted(bidx_ns, ask_ns, side="right") - 1
    out = np.zeros(len(ask_ns), dtype=bool)
    ok = pos >= 0
    out[ok] = bval[np.clip(pos[ok], 0, len(bval) - 1)]
    return out


def phase_mean_sums(ph, yr, wv, yv):
    out = []
    for y in range(5):
        ss = []
        for p in PHASES:
            m = (ph == p) & (yr == y)
            ss.append(float((wv[m] * yv[m]).sum()) if m.any() else 0.0)
        out.append(float(np.mean(ss)))
    return out


def load_luts():
    c = pd.read_parquet(CH / "chronos_features_4shift.parquet",
                        columns=["sym", "shift", "T", "ch_q10"])
    v = pd.read_parquet(VT / "vol_features_4shift.parquet",
                        columns=["sym", "shift", "T", "risk_GARCH"])
    vg = {}
    for s, sh, t, g in zip(v["sym"], v["shift"], v["T"], v["risk_GARCH"]):
        vg[(str(s), int(sh), pd.Timestamp(t))] = float(g)
    lut_c, lut_g = {}, {}
    for s, sh, t, q in zip(c["sym"], c["shift"], c["T"], c["ch_q10"]):
        key = (str(s), int(sh), pd.Timestamp(t))
        lut_c[key] = float(q)
        lut_g[key] = vg.get(key)
    for key, g in vg.items():
        if key not in lut_g:
            lut_g[key] = g
    del c, v
    return lut_c, lut_g


def bar_universe(variant, fits_v, bidx_ns, bval):
    import sys
    sys.path.insert(0, str(HERE))
    from tilt_rule import assign_mult, gate_mult  # noqa: E402
    c = pd.read_parquet(CH / "chronos_features_4shift.parquet",
                        columns=["sym", "shift", "T", "ch_q10"])
    v = pd.read_parquet(VT / "vol_features_4shift.parquet",
                        columns=["sym", "shift", "T", "risk_GARCH"])
    m = v.merge(c, on=["sym", "shift", "T"], how="outer")
    del c, v
    bar_mults, bar_keys_per_year = [], []
    for y in range(5):
        lo_a = ANCH[y]
        hi_a = ANCH[y + 1] if y < 4 else YEAR_END
        sub = m[(m["T"] >= lo_a) & (m["T"] < hi_a)].copy()
        # keep only rows on a valid shift grid for year y
        keep = np.zeros(len(sub), dtype=bool)
        s_arr = sub["shift"].to_numpy()
        t_arr = pd.to_datetime(sub["T"], utc=True)
        for sh in PHASES:
            lo = ANCH[y] + pd.Timedelta(hours=sh)
            hi = (ANCH[y + 1] + pd.Timedelta(hours=sh)) if y < 4 else (YEAR_END + pd.Timedelta(hours=sh))
            keep |= (s_arr == sh) & (t_arr >= lo) & (t_arr < hi)
        sub = sub[keep].sort_values(["sym", "shift", "T"]).reset_index(drop=True)
        f = fits_v[ANCH5[y]]
        ask = pd.to_datetime(sub["T"], utc=True).values.astype("datetime64[ns]").astype(np.int64)
        bb = bear_at_vec(bidx_ns, bval, ask)
        if variant == "C2_B":
            r = -sub["ch_q10"].to_numpy(dtype=float)
        else:
            r = sub["risk_GARCH"].to_numpy(dtype=float)
        mm = np.array([gate_mult(assign_mult(vv_, f["direction"], f["q20"], f["q80"], 1.25, 0.75), b_)
                       for vv_, b_ in zip(r, bb)], dtype=float)
        keys = list(zip(sub["sym"].astype(str), sub["shift"].astype(int),
                        pd.to_datetime(sub["T"], utc=True)))
        bar_mults.append(mm.astype(float))
        bar_keys_per_year.append(keys)
    del m
    return bar_mults, bar_keys_per_year


def run_variant(variant, fits_v, lut_c, lut_g, bidx_ns, bval,
                led, bt_all, ph, yr, co, w, yv, bt_ord, start, n):
    import sys
    sys.path.insert(0, str(HERE))
    from tilt_rule import assign_mult, gate_mult  # noqa: E402
    mult = np.ones(n, dtype=float)
    miss = 0
    bt_ns_all = (bt_all.astype("datetime64[ns]").astype(np.int64)
                 if np.asarray(bt_all).dtype != object else None)
    for i in range(n):
        bt = start + pd.Timedelta(minutes=int(bt_ord[i]))
        key = (MAJORS[int(co[i])], int(ph[i]), bt)
        y = int(yr[i])
        f = fits_v[ANCH5[y]]
        if variant == "C2_B":
            q = lut_c.get(key)
            risk = -q if q is not None and np.isfinite(q) else float("nan")
            if q is None:
                miss += 1
        else:
            q = lut_g.get(key)
            risk = float(q) if q is not None and np.isfinite(q) else float("nan")
            if q is None:
                miss += 1
        m0 = assign_mult(risk, f["direction"], f["q20"], f["q80"], 1.25, 0.75)
        ask = np.array([bt.value], dtype=np.int64)
        is_bear = bool(bear_at_vec(bidx_ns, bval, ask)[0])
        mult[i] = gate_mult(m0, is_bear)
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

    bar_mults, bar_keys_per_year = bar_universe(variant, fits_v, bidx_ns, bval)
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
                for i, v_ in zip(sorted(groups[g], key=lambda i: keys[i][2]), seq):
                    cur[i] = v_
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
    return years, timing, block


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

    fits_c2 = json.loads((CH / "fits.json").read_text())
    fits_g = json.loads((VT / "fits.json").read_text())["V_GARCH"]
    fits = {"C2_B": fits_c2, "GARCH_B": fits_g}

    bidx_ns, bval = build_bear()
    lut_c, lut_g = load_luts()

    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    co = led["coin"].astype(int)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)
    bt_ord = led["bar_time"].astype(np.int64)
    START = pd.Timestamp("2020-08-01", tz="UTC")

    res = {
        "config": {
            "ledger": "oc_k2placebo/tmp/ledger.npz + bt_all.npy read-only (identical build_base)",
            "seed_timing": SEED_TIMING,
            "seed_block": SEED_BLOCK,
            "n_perm": N_PERM,
            "block": BLOCK,
            "bear": "v421_gross_cap.py:70 ffilled <= T (causal)",
            "rule": "gated 1.25 fav outer quintile / 0.75 unfav / 1 else; base risk=-ch_q10 (C2_B) or risk_GARCH (GARCH_B); frozen fits; bear->1",
            "normalisation": "norm(y)=v(y)/realised_mean(y); perm norms use the ACTUAL denominator",
            "percentile": "100*(1+#{perm<=actual})/1001; significant iff >=95",
        },
        "reproduction": {"base_sum5y_gate": BASE_GATE, "n_fills": int(n)},
    }
    for variant in VARIANTS:
        years, timing, block = run_variant(variant, fits[variant], lut_c, lut_g,
                                           bidx_ns, bval, led, bt_all,
                                           ph, yr, co, w, yv, bt_ord, START, n)
        res[variant] = {"per_year": years, "timing_placebo": timing, "block_placebo": block}
    (HERE / "tmp/placebo_beargate.json").write_text(json.dumps(res, indent=1))
    print("wrote tmp/placebo_beargate.json", flush=True)


if __name__ == "__main__":
    main()
