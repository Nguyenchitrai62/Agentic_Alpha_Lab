"""oc_carryfric: frozen cash-carry sleeve overlaid on friction-scenario rows.

Assignment (docs/opencode/OPENCODE_W_oc_carryfric.md): for each friction
scenario x {D13BF, R2B1D17BFG2} x carry f in {0, 0.25, 0.5} report per anchor
year %/month and DD, 5y mean, worst year, max yearly DD, full-path DD, losing
years; answer (a) does D13BF + carry keep max yearly DD < 15 AND 5y >= 5.0
under each friction, (b) does G2 + carry keep 5y >= 5.0 under each friction.

Method reuse (NOT reimplemented): the equity-level combination with the
pre-registered carry sleeve, hourly mark, and reset metric is reused UNCHANGED
from research/tournament/oc_carryd13/combine_carryd13.py -- this script imports
that module (last_close_before, grid/time constants, fee constant, trade
assertions) and applies the identical combination arithmetic (per anchor year:
4-phase mix reset to 1.0 via reset_metric.year_reset + carry sleeve at f of
year-start equity, carry marked hourly causal from the last CLOSED hourly bar
strictly before t, rebased to 0 at the anchor; combined es/ms = base es/ms +
carry curve; 5y mean = geometric mean of yearly monthly factors; full-path DD
= chained-reset path, labelled). Only the S1 carry-cost parameter differs, as
the assignment orders (see S1 note below).

Base rows (stored per-phase equity runs, no engine reruns):
- D13BF (v424 R2B1D13BF): research/diagnostics/oc_d13robust/runs_D13BF_{base,
  S1,S2,S3,S4,S5}.pkl (that study's stored per-phase equity runs).
- G2 (R2B1D17BFG2): research/parallel/rounds/parallel-20260906-r2/v421_audit/
  runs_G2_{base,S1,S2,S3,S4,S5}.pkl (the v421 audit's stored per-phase runs;
  oc_d13robust/results.json references the same rows' aggregated metrics).
Friction definitions exactly as oc_d13robust/ROBUST.md (S1 cost stress MAKER
0.0004/TAKER 0.0012, S2 latency 15/16, S3 latency 30/31, S4 stop slip 50%, S5
Bybit prices from 2021-11-15).

S1 carry-cost stress (labelled assumption): base pair drag 0.00275 (spot
0.001/side + fut 0.00055 entry + 0.0002 delivery). Stressed: spot taker 0.0015
per side, futures taker 0.0012 at entry, delivery fee unchanged at 0.0002, so
stressed drag = 2*0.0015 + 0.0012 + 0.0002 = 0.0044; MtM-while-open entry-paid
fee 0.0015 + 0.0012 = 0.0027; realized ret_alloc stressed = frozen ret_alloc
- 0.00165. The 33 trades stay net positive (min checked in-script).

POST-HOC, REPORTING ONLY: every base row here was already scored on all five
years (oc_d13robust / v411+v421 audits); the carry rule was fixed before any
combination (oc_cashcarry PLAN pre-registered). No selection claim.

Usage: .venv/Scripts/python.exe research/tournament/oc_carryfric/combine_carryfric.py
Reads: oc_carryd13/combine_carryd13.py (imported, not modified),
  oc_cashcarry/results.json, oc_d13robust/{results.json,runs_D13BF_*.pkl},
  v421_audit/runs_G2_*.pkl, research/tournament/ext/hourly_ext.parquet
  (t < 2026-09-24, asserted), data/raw/qbasis_20261003/um_*_1h.parquet, one
  spot-4h file (delivery grid).
Writes: research/tournament/oc_carryfric/results.json
One process, 4h+1h data only (no 1m), RAM < 2 GB, no engine reruns.
"""

from __future__ import annotations

import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
CC = ROOT / "research/tournament/oc_cashcarry"
D13R = ROOT / "research/diagnostics/oc_d13robust"
V421A = RD / "v421_audit"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"
QDIR = ROOT / "data/raw/qbasis_20261003"
SDIR = ROOT / "data/raw/spot_majors_20260925"

ROWS = ("D13BF", "G2")
SCENS = ("base", "S1", "S2", "S3", "S4", "S5")
F_ROWS = [0.0, 0.25, 0.5]
# S1 carry stress (labelled): spot 0.0015/side, fut entry taker 0.0012,
# delivery 0.0002 unchanged.
S1_ENTRY_PAID = 0.0015 + 0.0012
S1_EXTRA_DRAG = (2 * 0.0015 + 0.0012 + 0.0002) - 0.00275


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    c13 = _load("combine_carryd13_reuse", HERE.parent / "oc_carryd13" / "combine_carryd13.py")
    v388 = _load("v388_for_carryfric", RD / "v388" / "v388_bot_stop_distance.py")
    rm = _load("reset_for_carryfric", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    grid = pd.date_range(c13.G0, g1, freq="1h")
    grid_ns = grid.values.astype("datetime64[ns]").astype(np.int64)

    # ---- frozen carry trades, reused unchanged (same assertions as oc_carryd13) ----
    cc = json.loads((CC / "results.json").read_text())
    assert cc["meta"]["threshold_ann_basis"] == 0.04
    assert len(cc["trades"]) == 33 and cc["n_skipped"] == 13 and cc["n_incomplete"] == 2
    assert cc["pooled"]["n_trades"] == 25

    # ---- hourly spot (causal last-closed-bar marks; verbatim from oc_carryd13) ----
    h = pd.read_parquet(HOURLY, columns=["t", "close", "sym"])
    h["t"] = pd.to_datetime(h["t"], utc=True)
    assert bool((h["t"] < c13.CAP).all()), "hourly data reaches beyond the cap"
    spot: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for coin in ("BTC", "ETH"):
        d = h[h["sym"] == f"{coin}USDT"].sort_values("t")
        spot[coin] = (d["t"].values.astype("datetime64[ns]").astype(np.int64),
                      d["close"].to_numpy(dtype=float))

    # ---- quarterly hourly per traded contract (verbatim from oc_carryd13) ----
    qmap: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}
    for t in cc["trades"]:
        key = (t["coin"], t["delivery"])
        if key in qmap:
            continue
        y, m, dd = t["delivery"].split("-")
        code = f"{y[2:]}{m}{dd}"
        (f,) = sorted(QDIR.glob(f"um_{t['coin']}USDT_{code}_1h.parquet"))
        q = pd.read_parquet(f, columns=["open_time", "close"])
        qo = pd.to_datetime(q["open_time"], utc=True).values.astype("datetime64[ns]").astype(np.int64)
        o = np.argsort(qo)
        qmap[key] = (qo[o], q["close"].to_numpy(dtype=float)[o])

    # ---- entry/settlement timestamps (spot-4h grid; verbatim from oc_carryd13) ----
    s4 = pd.read_parquet(SDIR / "BTCUSDT_spot_4h.parquet", columns=["open_time", "close_time"])
    s4o = pd.to_datetime(s4["open_time"], utc=True)
    s4c = pd.to_datetime(s4["close_time"], utc=True)
    trades = []
    for t in cc["trades"]:
        te = pd.Timestamp(t["entry_open"], tz="UTC")
        tc = te + pd.Timedelta(hours=4)
        assert (s4o == te).any(), t
        D = pd.Timestamp(t["delivery"] + " 08:00", tz="UTC")
        si = int(np.searchsorted(s4c.values.astype("datetime64[ns]").astype(np.int64),
                                 D.value, side="right"))
        assert si < len(s4), t
        ts = s4c.iloc[si]
        assert ts > tc, t
        trades.append({"coin": t["coin"], "delivery": t["delivery"],
                       "F_entry": float(t["F_entry"]), "S_entry": float(t["S_entry"]),
                       "ret_alloc": float(t["ret_alloc"]),
                       "tc_ns": tc.value, "ts_ns": ts.value})

    stressed_ret = [tr["ret_alloc"] - S1_EXTRA_DRAG for tr in trades]
    min_stressed = min(stressed_ret)
    assert min_stressed > 0, min_stressed  # all 33 pairs stay net positive under S1 stress

    def build_raw(fee_entry_paid: float, ret_of) -> tuple[np.ndarray, np.ndarray]:
        """Hourly carry curve (indexed units at f=1) + value at each anchor.

        Verbatim arithmetic from oc_carryd13.py, parametrized only by the
        entry-paid fee and the realized per-trade return (S1 stress variant).
        """
        G_ns = grid_ns
        raw = np.zeros(len(grid))
        for tr, r in zip(trades, ret_of):
            st, sc = spot[tr["coin"]]
            ft, fc = qmap[(tr["coin"], tr["delivery"])]
            S = c13.last_close_before(st, sc, G_ns)
            F = c13.last_close_before(ft, fc, G_ns)
            with np.errstate(divide="ignore", invalid="ignore"):
                mtm = (S / tr["S_entry"] - 1.0) + ((tr["F_entry"] - F) / tr["F_entry"]) - fee_entry_paid
            mtm[~np.isfinite(mtm)] = np.nan
            s = pd.Series(mtm, index=grid)
            s = s.ffill()
            mtm = s.to_numpy()
            v = np.zeros(len(grid))
            open_m = G_ns > tr["tc_ns"]
            settled_m = G_ns >= tr["ts_ns"]
            hold_m = open_m & ~settled_m
            v[hold_m] = mtm[hold_m]
            v[hold_m & ~np.isfinite(mtm)] = 0.0
            v[settled_m] = r
            raw += v
        a_ns = np.array([a.value for a in c13.ANCHORS])
        raw_at_anchor = []
        for a in a_ns:
            tot = 0.0
            qa = np.array([a])
            for tr, r in zip(trades, ret_of):
                if a <= tr["tc_ns"]:
                    continue
                if a >= tr["ts_ns"]:
                    tot += r
                    continue
                st, sc = spot[tr["coin"]]
                ft, fc = qmap[(tr["coin"], tr["delivery"])]
                S = c13.last_close_before(st, sc, qa)[0]
                F = c13.last_close_before(ft, fc, qa)[0]
                if np.isfinite(S) and np.isfinite(F) and tr["F_entry"] and tr["S_entry"]:
                    tot += (S / tr["S_entry"] - 1.0) + ((tr["F_entry"] - F) / tr["F_entry"]) - fee_entry_paid
            raw_at_anchor.append(tot)
        return raw, np.array(raw_at_anchor)

    raw_curves = {
        "base": build_raw(c13.FEE_ENTRY_PAID, [tr["ret_alloc"] for tr in trades]),
        "S1": build_raw(S1_ENTRY_PAID, stressed_ret),
    }

    # ---- stored friction runs (no engine reruns) ----
    runs: dict[str, dict[str, dict]] = {}
    for scen in SCENS:
        d = pickle.loads((D13R / f"runs_D13BF_{scen}.pkl").read_bytes())
        assert set(d) == {0, 1, 2, 3}, scen
        runs[f"D13BF/{scen}"] = {s: {"X": d[s]} for s in range(4)}
    for scen in SCENS:
        g = pickle.loads((V421A / f"runs_G2_{scen}.pkl").read_bytes())
        assert set(g) == {0, 1, 2, 3}, scen
        runs[f"G2/{scen}"] = {s: {"X": g[s]} for s in range(4)}

    # reference aggregates for cross-checks (already-scored rows)
    ref = json.loads((D13R / "results.json").read_text())

    def ref_years(row: str, scen: str):
        if row == "D13BF":
            src = ref["baseline"] if scen == "base" else ref["configs"][scen]
        else:
            src = (ref["reference_R2B1D17BFG2"]["baseline"] if scen == "base"
                   else ref["reference_R2B1D17BFG2"]["configs"][scen])
        return src

    combos = []
    base_rows: dict[str, dict] = {}
    for row in ROWS:
        for scen in SCENS:
            rr = runs[f"{row}/{scen}"]
            raw, raw_at_anchor = raw_curves["S1"] if scen == "S1" else raw_curves["base"]
            base_years = [rm.year_reset(rr, "X", y) for y in range(5)]
            r = ref_years(row, scen)
            base_rows[f"{row}/{scen}"] = {
                "years": base_years,
                "R_5y": round(float(np.prod([1 + yy["R"] / 100 for yy in base_years]) ** (1 / 5) - 1) * 100, 3),
                "W": min(yy["R"] for yy in base_years),
                "DD": max(yy["DD"] for yy in base_years),
                "ref_R_5y": r["mean5y"], "ref_DD": r["maxDD"], "ref_fullDD": r["fullDD"],
                "ref_years": [[yy["R"], yy["DD"]] for yy in r["years"]],
            }
            E, MN = [], []
            for s in range(4):
                e1, m1 = v388.hourly(rr[s]["X"], c13.G0, g1)
                assert (e1.index == grid).all()
                E.append(e1)
                MN.append(m1)
            for f in F_ROWS:
                years = []
                chained_es, chained_ms = [], []
                level = 1.0
                for y, a0 in enumerate(c13.ANCHORS):
                    a1 = a0 + c13.YEAR_LEN
                    seg = (grid > a0) & (grid <= a1)
                    b = np.array([float(e[e.index <= a0].iloc[-1]) if (e.index <= a0).any() else 1.0
                                  for e in E])
                    es = sum(e[seg] / bb for e, bb in zip(E, b)) / 4
                    ms = sum(m[seg] / bb for m, bb in zip(MN, b)) / 4
                    cy = f * (raw[seg] - raw_at_anchor[y])
                    c = pd.Series(cy, index=es.index)
                    es_c = es + c
                    ms_c = ms + c
                    pk = np.maximum.accumulate(es_c.to_numpy())
                    R = round(100 * float(es_c.iloc[-1] ** (1 / 12) - 1), 3)
                    DD = round(100 * float(np.max(1 - ms_c.to_numpy() / pk)), 2)
                    years.append({"anchor": str(a0.date()), "R": R, "DD": DD,
                                  "base_R": base_years[y]["R"], "base_DD": base_years[y]["DD"],
                                  "carry_R_pp": round(R - base_years[y]["R"], 3),
                                  "carry_DD_pp": round(DD - base_years[y]["DD"], 2),
                                  "total_pct": round(float(es_c.iloc[-1] - 1) * 100, 4)})
                    chained_es.append(es_c.to_numpy() * level)
                    chained_ms.append(ms_c.to_numpy() * level)
                    level *= float(es_c.iloc[-1])
                R5 = round(float(np.prod([1 + yy["R"] / 100 for yy in years]) ** (1 / 5) - 1) * 100, 3)
                W = min(yy["R"] for yy in years)
                DDmax = max(yy["DD"] for yy in years)
                fes = np.concatenate(chained_es)
                fms = np.concatenate(chained_ms)
                full_dd = round(100 * float(np.max(1 - fms / np.maximum.accumulate(fes))), 2)
                combos.append({"row": row, "scen": scen, "f": f, "years": years,
                               "R_5y": R5, "W": W, "DD_maxyearly": DDmax,
                               "full_path_dd_chained": full_dd,
                               "losing_years": sum(yy["R"] < 0 for yy in years),
                               "dd_lt_15": bool(DDmax < 15.0),
                               "r_ge_5": bool(R5 >= 5.0),
                               "win_rate_note": ("BOT all-trade win rate unchanged: equity-level overlay "
                                                 "adds zero trades; carry pairs are 33/33 net positive on "
                                                 "allocated capital per oc_cashcarry (min stressed "
                                                 f"{min_stressed:.5f} > 0 under S1), reported separately, "
                                                 "not mixed into a trade win rate.")})

    # ---- checks ----
    gaps_f0, gaps_ref_R, gaps_ref_DD, resid = [], [], [], []
    for c in combos:
        by = base_rows[f"{c['row']}/{c['scen']}"]
        if c["f"] == 0.0:
            for yy, bb in zip(c["years"], by["years"]):
                gaps_f0.append(abs(yy["R"] - bb["R"]))
                gaps_f0.append(abs(yy["DD"] - bb["DD"]))
            gaps_ref_R.append(abs(by["R_5y"] - by["ref_R_5y"]))
            gaps_ref_DD.append(abs(by["DD"] - by["ref_DD"]))
        resid.append(max(abs((1 + yy["total_pct"] / 100) ** (1 / 12) * 100 - 100 - yy["R"])
                         for yy in c["years"]))
    checks = {
        "f0_vs_year_reset_max_gap": round(float(max(gaps_f0)), 6),
        "f0_vs_reference_max_R_gap": round(float(max(gaps_ref_R)), 6),
        "f0_vs_reference_max_DD_gap": round(float(max(gaps_ref_DD)), 6),
        "monthly_total_residual_pp": round(float(max(resid)), 6),
        "s1_min_stressed_ret_alloc": round(float(min_stressed), 6),
        "carry_fee_entry_paid_base": float(c13.FEE_ENTRY_PAID),
        "carry_fee_entry_paid_S1": float(S1_ENTRY_PAID),
        "carry_extra_drag_S1": float(S1_EXTRA_DRAG),
    }

    out = {
        "meta": {
            "rows": list(ROWS), "scens": list(SCENS), "f_rows": list(F_ROWS),
            "friction_defs": ("exactly as oc_d13robust/ROBUST.md: S1 cost stress MAKER 0.0004/TAKER "
                              "0.0012, S2 latency 15/16, S3 latency 30/31, S4 stop slip 50%, S5 Bybit "
                              "prices from 2021-11-15"),
            "carry_rule": ("frozen oc_cashcarry (PLAN pre-registered): roll next-quarter at <=7d, "
                           "enter iff ann basis >= 4%, equal-notional spot long + quarterly short, "
                           "hold to delivery, fees spot 0.001/side + fut 0.00055/0.0002; "
                           "33 entered / 13 skipped / 2 incomplete reused verbatim; "
                           "S1 stress (labelled): spot 0.0015/side + fut 0.0012 entry, "
                           "delivery 0.0002 unchanged (drag 0.0044)"),
            "combination": ("equity-level, method reused UNCHANGED from oc_carryd13/combine_carryd13.py "
                            "(imported): per anchor year, 4-phase mix reset to 1.0 "
                            "(reset_metric.year_reset) + carry sleeve at f of year-start equity, carry "
                            "marked hourly causal (last closed hourly bar strictly before t), rebased to "
                            "0 at anchor; full-path DD = chained-reset path (labelled)"),
            "base_runs": ("D13BF: oc_d13robust/runs_D13BF_{base,S1..S5}.pkl; G2: "
                          "v421_audit/runs_G2_{base,S1..S5}.pkl; stored per-phase equity, no reruns"),
            "g1": str(g1), "data_cap": "2026-09-24T00:00:00Z",
            "post_hoc": True, "reporting_only": True,
        },
        "base_rows": base_rows,
        "combos": combos,
        "checks": checks,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    for c in combos:
        print(f"{c['row']} {c['scen']} f={c['f']}: R5={c['R_5y']} W={c['W']} "
              f"DDmax={c['DD_maxyearly']} fullDD={c['full_path_dd_chained']} "
              f"losing={c['losing_years']} dd<15={c['dd_lt_15']} R>=5={c['r_ge_5']}")
    print("checks:", json.dumps(checks))


if __name__ == "__main__":
    main()
