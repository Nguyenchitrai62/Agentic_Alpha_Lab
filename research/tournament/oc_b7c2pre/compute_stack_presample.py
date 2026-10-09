"""oc_b7c2pre replica + placebo: B7 x C2 product stack on the pre-sample ledger.

Verbatim oc_b7c2 product arithmetic applied to the pre-sample grid/ledger:
  m_B7(T,shift) from boost_mult_presample.parquet (market-wide per shift, 1.5/1.0);
  m_C2(sym,T,shift) from chronos_features_presample risk=-ch_q10 with the FROZEN
  anchor-2021 C2 fit (dir +1, q20/q80, hi/lo 1.25/0.75, missing->1, labelled
  "fit from later data, rule frozen");
  m_stack = m_B7*m_C2; m_cap = min(m_stack, 1.5).
Ledger REUSED read-only from oc_presampletilt/tmp (D0+B1, no budget/cap; SPOT
fills/exits, perp gate costs inside; spot-vs-perp caveat on every number).

Per year y: base(y), tilted(y), realised_mean(y), norm(y)=tilted/realised_mean,
gain_vs_base=norm-base, gain_vs_B7=norm_stack-norm_B7_copy,
gain_vs_C2=norm_stack-norm_C2_copy. Timing/block placebo (1000 perms, seeds
20261007+y/20261008+y, y=0..3, percentile=100*(1+#{perm<=actual})/1001, signif
iff >=95) with the pre-registered JOINT null: bar-level permutation over that
year's (sym,shift,T) decision-bar universe (block-42 per (sym,shift) for block).
CPU-only (numpy). Heartbeat every 600 s.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PST = ROOT / "research/tournament/oc_presampletilt"
CBP = ROOT / "research/tournament/oc_cboostpre"

sys.path.insert(0, str(HERE))
from stack_rule import (  # noqa: E402
    B7_BOOST,
    C2_DIRECTION,
    C2_HI,
    C2_LO,
    C2_Q20,
    C2_Q80,
    STACK_CAP,
    assign_c2,
    stack_mult,
    stack_mult_cap,
)

LEG_ORDER = ("Y2017", "Y2018", "Y2019", "Y2020p")
LEG_BOUNDS = {
    "Y2017": (pd.Timestamp("2017-10-16", tz="UTC"), pd.Timestamp("2018-01-01", tz="UTC")),
    "Y2018": (pd.Timestamp("2018-01-01", tz="UTC"), pd.Timestamp("2019-01-01", tz="UTC")),
    "Y2019": (pd.Timestamp("2019-01-01", tz="UTC"), pd.Timestamp("2020-01-01", tz="UTC")),
    "Y2020p": (pd.Timestamp("2020-01-01", tz="UTC"), pd.Timestamp("2020-09-01", tz="UTC")),
}
MAJORS4 = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT")
XRP_WARM = pd.Timestamp("2018-07-03", tz="UTC")
SEED_TIMING = 20261007
SEED_BLOCK = 20261008
N_PERM = 1000
BLOCK = 42
N_GATE = 9731
PER_LEG_GATE = (909, 2986, 3115, 2721)
BASE_GATE = (2.313362, 2.678870, 0.577643, 0.297538)
PHASES = (0, 1, 2, 3)
SHIFTS = (0, 1, 2, 3)
VARIANTS = ("B7C2", "B7C2_cap")
HB_S = 600


def phase_mean_sums(ph, yr, wv, yv, n_years=4):
    out = []
    for y in range(n_years):
        ss = []
        for p in PHASES:
            m = (ph == p) & (yr == y)
            ss.append(float((wv[m] * yv[m]).sum()) if m.any() else 0.0)
        out.append(float(np.mean(ss)))
    return out


def warmed(sym: str, t: pd.Timestamp) -> bool:
    if sym in ("BTCUSDT", "ETHUSDT"):
        return True
    if sym == "BNBUSDT":
        return True  # BNB warm from 2018-01-05; Y2017 universe excludes BNB entirely
    if sym == "XRPUSDT":
        return t >= XRP_WARM
    return False


def load_boost():
    d = pd.read_parquet(CBP / "boost_mult_presample.parquet")
    d["T"] = pd.to_datetime(d["T"], utc=True)
    exact = {}
    per_shift = {}
    for s in SHIFTS:
        sub = d[d["shift"] == s].sort_values("T")
        t_ns = sub["T"].values.astype("datetime64[ns]").astype(np.int64)
        per_shift[s] = {
            "mult_B7": sub["mult_B7"].to_numpy(dtype=float),
            "t_ns": t_ns,
            "T": pd.to_datetime(sub["T"], utc=True).tolist(),
        }
        for t, a in zip(per_shift[s]["T"], per_shift[s]["mult_B7"]):
            exact[(int(s), pd.Timestamp(t))] = float(a)
    return exact, per_shift


def boost_at(shift, t, exact, per_shift):
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
    return float(per_shift[int(shift)]["mult_B7"][pos])


def main() -> None:
    t0 = time.time()
    last_hb = t0
    assert B7_BOOST == 1.5 and STACK_CAP == 1.5
    assert C2_HI == 1.25 and C2_LO == 0.75
    print("[oc_b7c2pre] loading ledger + frozen tables...", flush=True)
    led = dict(np.load(PST / "tmp/ledger_presample.npz"))
    for k in ("phase", "coin", "year", "t_ord", "rung"):
        led[k] = led[k].astype(np.int64)
    for k in ("w", "y10"):
        led[k] = led[k].astype(np.float64)
    bt_all = np.load(PST / "tmp/bt_presample.npy", allow_pickle=True)
    n = len(led["w"])
    print(f"loaded presample ledger n={n}", flush=True)
    assert n == N_GATE, f"ledger size {n} != {N_GATE}"
    for y, g in enumerate(PER_LEG_GATE):
        got = int((led["year"] == y).sum())
        assert got == g, f"leg {LEG_ORDER[y]} n {got} != {g}"

    exact, per_shift = load_boost()
    ch = pd.read_parquet(
        PST / "chronos_features_presample.parquet",
        columns=["sym", "shift", "T", "ch_q10"],
    )
    ch["T"] = pd.to_datetime(ch["T"], utc=True)
    c2_lut: dict = {}
    for s, sh, t, q in zip(ch["sym"], ch["shift"], ch["T"], ch["ch_q10"]):
        c2_lut[(str(s), int(sh), pd.Timestamp(t))] = float(q)
    del ch

    ph = led["phase"].astype(int)
    yr = led["year"].astype(int)
    co = led["coin"].astype(int)
    w = led["w"].astype(float)
    yv = led["y10"].astype(float)

    base_y = phase_mean_sums(ph, yr, w, yv)
    print(f"base 4-phase-mean sums={[round(v, 6) for v in base_y]}", flush=True)
    for y in range(4):
        assert abs(base_y[y] - BASE_GATE[y]) <= 1e-6, \
            f"base {LEG_ORDER[y]} {base_y[y]} != {BASE_GATE[y]}"

    # ---- copy gates: B7 / C2 frozen numbers match sources to the digit ----
    cbp_res = json.loads((CBP / "results.json").read_text())
    pst_res = json.loads((PST / "results.json").read_text())
    for v, src in (("B7", cbp_res["B7"]["per_year"]), ("C2", pst_res["presample"]["C2"]["per_year"])):
        print(f"copy-gate {v}: " + ", ".join(
            f"{r['year']} base={r['base']} norm={r['norm']} gain={r['gain']}" for r in src),
            flush=True)
    # strict digit gates on the copy rows (base/norm/gain per year)
    assert [r["base"] for r in cbp_res["B7"]["per_year"]] == [round(b, 6) for b in BASE_GATE]
    assert [r["base"] for r in pst_res["presample"]["C2"]["per_year"]] == [round(b, 6) for b in BASE_GATE]
    b7_copy = {r["year"]: r for r in cbp_res["B7"]["per_year"]}
    c2_copy = {r["year"]: r for r in pst_res["presample"]["C2"]["per_year"]}
    b7_timing_copy = {r["year"]: r["percentile"] for r in cbp_res["B7"]["timing_placebo"]}
    b7_block_copy = {r["year"]: r["percentile"] for r in cbp_res["B7"]["block_placebo"]}
    c2_timing_copy = {r["year"]: r["percentile"] for r in pst_res["presample"]["C2"]["timing_placebo"]}
    c2_block_copy = {r["year"]: r["percentile"] for r in pst_res["presample"]["C2"]["block_placebo"]}

    # ---- per-fill stack mults ----
    m_b7 = np.array([boost_at(int(ph[i]), bt_all[i], exact, per_shift)
                     for i in range(n)], dtype=float)
    assert set(np.unique(m_b7)) <= {1.0, 1.5}
    m_c2 = np.ones(n, dtype=float)
    nmiss_c2 = 0
    for i in range(n):
        key = (MAJORS4[int(co[i])], int(ph[i]), pd.Timestamp(bt_all[i]))
        q = c2_lut.get(key)
        if q is None or not np.isfinite(q):
            nmiss_c2 += 1
            m_c2[i] = 1.0
        else:
            m_c2[i] = assign_c2(-float(q), C2_DIRECTION, C2_Q20, C2_Q80)
    print(f"C2 join: missing->1 count={nmiss_c2} (expect 5547 per presampletilt features note)",
          flush=True)
    assert set(np.unique(np.round(m_c2, 6))) <= {0.75, 1.0, 1.25}
    mult = {
        "B7C2": np.array([stack_mult(a, b) for a, b in zip(m_b7, m_c2)], dtype=float),
        "B7C2_cap": np.array([stack_mult_cap(a, b) for a, b in zip(m_b7, m_c2)], dtype=float),
    }
    assert set(np.unique(np.round(mult["B7C2"], 6))) <= {0.75, 1.0, 1.125, 1.25, 1.5, 1.875}
    assert set(np.unique(np.round(mult["B7C2_cap"], 6))) <= {0.75, 1.0, 1.125, 1.25, 1.5}
    for v in VARIANTS:
        print(f"{v}: boosted(mult>1) share={float((mult[v] > 1.0).mean()):.4f} "
              f"deboosted(mult<1) share={float((mult[v] < 1.0).mean()):.4f} "
              f"values={sorted(set(np.round(mult[v], 6)))}", flush=True)

    # ---- decision-bar universes per year from bars_4h_presample ----
    bars = pd.read_parquet(PST / "bars_4h_presample.parquet", columns=["sym", "shift", "T"])
    bars["T"] = pd.to_datetime(bars["T"], utc=True)
    uni_mult = {}  # y -> (keys, mult array)
    for y in range(4):
        lo, hi = LEG_BOUNDS[LEG_ORDER[y]]
        sub = bars[(bars["T"] >= lo) & (bars["T"] < hi)].copy()
        if LEG_ORDER[y] == "Y2017":
            sub = sub[sub["sym"].isin(["BTCUSDT", "ETHUSDT"])]
        else:
            sub = sub[sub["sym"].isin(["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT"])]
            sub = sub[~( (sub["sym"] == "XRPUSDT") & (sub["T"] < XRP_WARM))]
        sub = sub.sort_values(["sym", "shift", "T"]).reset_index(drop=True)
        keys = list(zip(sub["sym"].astype(str), sub["shift"].astype(int),
                        pd.to_datetime(sub["T"], utc=True)))
        uni_mult[y] = (keys, sub)
        print(f"universe {LEG_ORDER[y]}: bars={len(sub)}", flush=True)
    del bars

    # per-variant universe mult arrays + fill positions
    res = {
        "config": {
            "ledger": "oc_presampletilt/tmp/ledger_presample.npz + bt_presample.npy read-only (D0+B1, no budget/cap; SPOT fills/exits)",
            "boost": "boost_mult_presample.parquet B7 col (closes-only >4sg, union per shift; 1.5 in (tc,tc+7d])",
            "c2": "chronos_features_presample risk=-ch_q10 with FROZEN anchor-2021 fit (dir +1, q20 1.110054237503456, q80 2.8608138206510407, hi/lo 1.25/0.75, missing->1; labelled fit from later data, rule frozen)",
            "rule": "m_stack=m_B7*m_C2; m_cap=min(m_stack,1.5); multisets B7C2 {0.75,1.0,1.125,1.25,1.5,1.875}, cap {0.75,1.0,1.125,1.25,1.5}",
            "seed_timing": SEED_TIMING, "seed_block": SEED_BLOCK,
            "n_perm": N_PERM, "block": BLOCK,
            "normalisation": "norm(y)=tilted(y)/realised_mean(y); gain_vs_base=norm-base; gain_vs_B7=norm_stack-norm_B7_copy; gain_vs_C2=norm_stack-norm_C2_copy; perm norms use the ACTUAL denominator",
            "percentile": "100*(1+#{perm<=actual})/1001; significant iff >=95",
            "placebo_null": "JOINT bar-level permutation over the year's (sym,shift,T) decision-bar universe (1000 uniform; block-42 per (sym,shift) within year)",
            "diagnostic": "no gate, no selection, no engine (unseen-years diagnostic only)",
        },
        "reproduction": {"per_leg_gate": list(PER_LEG_GATE),
                          "base_sums": [round(v, 6) for v in base_y],
                          "n_fills": int(n), "c2_missing_to_1": int(nmiss_c2)},
        "copies": {
            "B7_per_year": cbp_res["B7"]["per_year"],
            "B7_timing": cbp_res["B7"]["timing_placebo"],
            "B7_block": cbp_res["B7"]["block_placebo"],
            "C2_per_year": pst_res["presample"]["C2"]["per_year"],
            "C2_timing": pst_res["presample"]["C2"]["timing_placebo"],
            "C2_block": pst_res["presample"]["C2"]["block_placebo"],
        },
    }

    for variant in VARIANTS:
        cap = variant.endswith("_cap")
        tilt_y = phase_mean_sums(ph, yr, w * mult[variant], yv)
        years = []
        for y in range(4):
            m = yr == y
            rm = float(mult[variant][m].mean()) if m.any() else 1.0
            norm = float(tilt_y[y]) / rm if rm else 0.0
            years.append({
                "year": LEG_ORDER[y], "n_fills": int(m.sum()),
                "base": round(float(base_y[y]), 6),
                "tilted": round(float(tilt_y[y]), 6),
                "realised_mean": round(rm, 6),
                "norm": round(norm, 6),
                "gain_vs_base": round(norm - float(base_y[y]), 6),
                "gain_vs_B7": round(norm - float(b7_copy[LEG_ORDER[y]]["norm"]), 6),
                "gain_vs_C2": round(norm - float(c2_copy[LEG_ORDER[y]]["norm"]), 6),
                "boosted_share_mult_gt1": round(float((mult[variant][m] > 1.0).mean()), 4),
                "deboosted_share_mult_lt1": round(float((mult[variant][m] < 1.0).mean()), 4),
            })
        for r in years:
            print(f"  {variant} {r['year']} n={r['n_fills']} base={r['base']} "
                  f"tilted={r['tilted']} rm={r['realised_mean']} norm={r['norm']} "
                  f"g_base={r['gain_vs_base']} g_B7={r['gain_vs_B7']} g_C2={r['gain_vs_C2']} "
                  f"boosted={r['boosted_share_mult_gt1']}", flush=True)

        # universe mults for this variant + fill positions
        bar_keys, bar_mults, bar_pos = [], [], []
        for y in range(4):
            keys, sub = uni_mult[y]
            arr = np.empty(len(keys), dtype=float)
            for j, (s, sh, t) in enumerate(keys):
                a = boost_at(int(sh), t, exact, per_shift)
                q = c2_lut.get((str(s), int(sh), pd.Timestamp(t)))
                b = assign_c2(-float(q), C2_DIRECTION, C2_Q20, C2_Q80) \
                    if q is not None and np.isfinite(float(q)) else 1.0
                arr[j] = stack_mult_cap(a, b) if cap else stack_mult(a, b)
            bar_keys.append(keys)
            bar_mults.append(arr)
            idx = {k: i for i, k in enumerate(keys)}
            pos = np.full(int((yr == y).sum()), -1, dtype=np.int64)
            for j, i in enumerate(np.where(yr == y)[0]):
                pos[j] = idx.get((MAJORS4[int(co[i])], int(ph[i]),
                                  pd.Timestamp(bt_all[i])), -1)
            nmiss = int((pos < 0).sum())
            print(f"{variant} {LEG_ORDER[y]}: universe={len(keys)} fills_missing_bar={nmiss}",
                  flush=True)
            if nmiss:
                ones = np.where(arr == 1.0)[0]
                assert len(ones), f"{variant} {LEG_ORDER[y]}: no mult-1 bar for missing fills"
                pos[pos < 0] = int(ones[0])
            assert (pos >= 0).all()
            bar_pos.append(pos)
        print(f"bar universes {variant}: {[len(b) for b in bar_mults]}", flush=True)

        timing = []
        for y in range(4):
            rng = np.random.default_rng(SEED_TIMING + y)
            mm_uni, pos = bar_mults[y], bar_pos[y]
            denom = float(mult[variant][yr == y].mean())
            actual = float(tilt_y[y]) / denom
            fw, fy, fp = w[yr == y], yv[yr == y], ph[yr == y]
            perms = np.empty(N_PERM)
            for k in range(N_PERM):
                fm = rng.permutation(mm_uni)[pos]
                s = sum(float((fw[fp == p] * fm[fp == p] * fy[fp == p]).sum())
                        for p in PHASES) / 4.0
                perms[k] = s / denom
                if time.time() - last_hb >= HB_S:
                    last_hb = time.time()
                    print(f"[hb] timing {variant} y={y} perm {k}/{N_PERM} "
                          f"elapsed={time.time() - t0:.0f}s", flush=True)
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            timing.append({"year": LEG_ORDER[y], "actual_norm": round(actual, 6),
                           "p5": round(float(np.quantile(perms, 0.05)), 6),
                           "p50": round(float(np.quantile(perms, 0.50)), 6),
                           "p95": round(float(np.quantile(perms, 0.95)), 6),
                           "percentile": round(float(pct), 2)})
            print(f"timing {variant} {LEG_ORDER[y]} actual={actual:.6f} "
                  f"p5={np.quantile(perms, 0.05):.6f} p50={np.quantile(perms, 0.50):.6f} "
                  f"p95={np.quantile(perms, 0.95):.6f} pct={pct:.2f}", flush=True)

        block = []
        for y in range(4):
            rng = np.random.default_rng(SEED_BLOCK + y)
            keys, mm_uni, pos = bar_keys[y], bar_mults[y], bar_pos[y]
            groups: dict = {}
            for i, k in enumerate(keys):
                groups.setdefault((k[0], k[1]), []).append(i)
            gblocks = {}
            for g, idxs in groups.items():
                idxs = sorted(idxs, key=lambda i: keys[i][2])
                gblocks[g] = [idxs[b:b + BLOCK] for b in range(0, len(idxs), BLOCK)]
            denom = float(mult[variant][yr == y].mean())
            actual = float(tilt_y[y]) / denom
            fw, fy, fp = w[yr == y], yv[yr == y], ph[yr == y]
            perms = np.empty(N_PERM)
            cur = np.empty_like(mm_uni)
            for k in range(N_PERM):
                for g, blks in gblocks.items():
                    order = rng.permutation(len(blks))
                    seq = []
                    for b in order:
                        seq.extend(mm_uni[blks[b]])
                    for i, v in zip(sorted(groups[g], key=lambda i: keys[i][2]), seq):
                        cur[i] = v
                fm = cur[pos]
                s = sum(float((fw[fp == p] * fm[fp == p] * fy[fp == p]).sum())
                        for p in PHASES) / 4.0
                perms[k] = s / denom
                if time.time() - last_hb >= HB_S:
                    last_hb = time.time()
                    print(f"[hb] block {variant} y={y} perm {k}/{N_PERM} "
                          f"elapsed={time.time() - t0:.0f}s", flush=True)
            pct = 100.0 * (1 + int((perms <= actual).sum())) / (N_PERM + 1)
            block.append({"year": LEG_ORDER[y], "actual_norm": round(actual, 6),
                          "p5": round(float(np.quantile(perms, 0.05)), 6),
                          "p50": round(float(np.quantile(perms, 0.50)), 6),
                          "p95": round(float(np.quantile(perms, 0.95)), 6),
                          "percentile": round(float(pct), 2)})
            print(f"block {variant} {LEG_ORDER[y]} actual={actual:.6f} pct={pct:.2f}",
                  flush=True)

        res[variant] = {"per_year": years, "timing_placebo": timing,
                        "block_placebo": block}

    (HERE / "tmp").mkdir(exist_ok=True)
    (HERE / "tmp/stack_presample.json").write_text(json.dumps(res, indent=1))
    print("wrote tmp/stack_presample.json", flush=True)


if __name__ == "__main__":
    main()
