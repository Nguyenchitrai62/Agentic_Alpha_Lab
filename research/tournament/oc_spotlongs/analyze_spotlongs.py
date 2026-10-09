"""oc_spotlongs scoring (CPU-only): gate + dev4 / Y4-diagnostic / 5y + full-path DD.

Reads tmp/runs_<stage>_<fric>.pkl (V0/V1/V2 full-window runs per shift),
scores with reset_metric.year_reset + v388.mix, checks the reproduction gate
(V0 dev years 0..3 == v421 G2 to the digit; pick-last years 0..3 == pick-dev),
derives CTRL (exposure-matched: same closes + funding saved back, no borrow)
and APR15 stress (borrow x1.5) as accounting overlays on identical fills
(disclosed approximation for eq_min scaling), writes
tmp/spotlongs_table.json + results.json. REPORT.md is written from that table
only. REF full-window numbers are the stored v421 row (labelled, never
recomputed); REF_S5 side-by-side is read from oc_c2bybit (never recomputed).
"""
from __future__ import annotations

import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
TMP = HERE / "tmp"
C2B = ROOT / "research/tournament/oc_c2bybit"
VARIANTS = ("V0", "V1", "V2")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def geo(rs, nd=3):
    return round(100 * (float(np.prod([1 + r / 100 for r in rs])) ** (1 / len(rs)) - 1), nd)


def score_runs(runs, key, g1, v388, rm, years):
    """Score one variant key from {shift: {key: rec}} on valid year indices.

    years: subset of 0..4 present in these runs (dev stage -> [0,1,2,3]).
    Dev stats (Rdev4/W/DDdev4/losing) use years 0..3; 5y/full only when all
    five years are present, else None.
    """
    years = list(years)
    rr = {s: {key: runs[s][key]["run"]} for s in range(4)}
    all_yrs = [rm.year_reset(rr, key, y) for y in years]
    Rs = [y["R"] for y in all_yrs]
    DDs = [y["DD"] for y in all_yrs]
    y2r = dict(zip(years, Rs))
    y2d = dict(zip(years, DDs))
    dev_yrs = [y for y in years if y < 4]
    dev = [y2r[y] for y in dev_yrs]
    e, mn = v388.mix(rr, key, g1)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    fulldd = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
    wins = []
    for y in range(5):
        if y in years:
            nb = sum(runs[s][key]["wins"][y]["nb"] for s in range(4))
            wb = sum(runs[s][key]["wins"][y]["wb"] for s in range(4))
            nr = sum(runs[s][key]["wins"][y]["nr"] for s in range(4))
            wr = sum(runs[s][key]["wins"][y]["wr"] for s in range(4))
        else:
            nb = wb = nr = wr = 0
        wins.append(dict(nb=nb, wb=wb, nr=nr, wr=wr,
                         book_win=round(wb / nb, 4) if nb else None,
                         rung_win=round(wr / nr, 4) if nr else None,
                         all_win=round((wb + wr) / (nb + nr), 4) if (nb + nr) else None))
    out = dict(years_R=Rs, years_DD=DDs, years_idx=years,
               Rdev4=geo(dev), Wdev4=round(min(dev), 3),
               DDdev4=round(max(y2d[y] for y in dev_yrs), 2),
               losing_dev4=sum(r < 0 for r in dev),
               wins=wins)
    if set(years) == {0, 1, 2, 3, 4}:
        out.update(R5y=geo(Rs), W5y=round(min(Rs), 3),
                   DD5y=round(max(DDs), 2),
                   losing_5y=sum(r < 0 for r in Rs),
                   full_path_dd=fulldd,
                   DDmax_full=round(max(max(DDs), fulldd), 2))
    else:
        out.update(R5y=None, W5y=None, DD5y=None, losing_5y=None,
                   full_path_dd=None, DDmax_full=round(max(max(DDs), fulldd), 2))
    return out


def overlay_runs(runs, src_key, kind):
    """CTRL / APR15 close-equity overlays on identical fills (per shift).

    Per-bar borrow/funding_saved (fractions of bar-start equity) are aligned
    to the run's close series by timestamp (holding-bar open T = run t - 4h;
    missing bars -> 0.0). kind CTRL: same closes + funding saved back, no
    borrow. kind APR15: borrow x1.5. eq_min scaled proportionally (labelled).
    """
    assert kind in ("CTRL", "APR15")
    out = {}
    for s in range(4):
        rec = runs[s][src_key]
        ts = [str(t) for t in rec["run"]["t"]]
        e = np.array(rec["run"]["eq"], dtype=float)
        em = np.array(rec["run"]["eq_min"], dtype=float)
        bd = {str(b["t"]): b for b in rec["bars_lite"]}
        bo = np.zeros(len(e))
        fs = np.zeros(len(e))
        for j, t in enumerate(ts):
            T = str(pd.Timestamp(t) - pd.Timedelta(hours=4))
            b = bd.get(T)
            if b is not None:
                bo[j] = float(b["borrow"])
                fs[j] = float(b["funding_saved"])
        x = np.empty_like(e)
        x[0] = e[0] - 1.0 + bo[0]  # ex-cost return bar 0 (e[0] vs base 1.0)
        x[1:] = e[1:] / e[:-1] - 1.0 + bo[1:]
        if kind == "CTRL":
            adj = fs
        else:  # APR15: same fills, borrow charged at 1.5x the in-engine 10%
            adj = 1.5 * bo
        c = np.empty_like(e)
        c[0] = 1.0 * (1 + x[0] - adj[0])
        for i in range(1, len(e)):
            c[i] = c[i - 1] * (1 + x[i] - adj[i])
        scale = np.divide(c, e, out=np.ones_like(c), where=e != 0)
        key = f"{src_key}_{kind}"
        out[s] = {key: dict(run=dict(t=ts, eq=c.tolist(),
                                     eq_min=(em * scale).tolist()),
                            wins=rec["wins"], bars_lite=rec["bars_lite"])}
    return out


def main():
    v388 = _load("v388_spot", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("reset_spot", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    exp = json.loads((RD / "v421/v421_result.json").read_text())["rows"]["R2B1D17BFG2"]

    p = TMP / "runs_dev_base.pkl"
    assert p.exists(), f"missing {p} — run compute_spotlongs_engine.py --stage dev first"
    runs = pickle.loads(p.read_bytes())
    assert set(runs) == {0, 1, 2, 3}, sorted(runs)
    for s in range(4):
        assert set(runs[s]) >= {"V0"}, (s, sorted(runs[s]))
    dev_years = [0, 1, 2, 3]

    table = {}
    for v in VARIANTS:
        if v not in runs[0]:
            continue
        table[v] = score_runs(runs, v, g1, v388, rm, dev_years)

    # ---- reproduction gate: V0 dev years 0..3 == v421 G2 to the digit ----
    for y in dev_years:
        er, ed = exp["years"][y]
        assert table["V0"]["years_R"][y] == er, (y, table["V0"]["years_R"][y], er)
        assert table["V0"]["years_DD"][y] == ed, (y, table["V0"]["years_DD"][y], ed)
    print("V0 reproduces v421 G2 dev years 0..3 EXACTLY:",
          table["V0"]["years_R"], flush=True)

    # ---- overlays: CTRL + APR15 for V1/V2 (identical fills) ----
    for v in ("V1", "V2"):
        if v not in runs[0]:
            continue
        for kind in ("CTRL", "APR15"):
            ov = overlay_runs(runs, v, kind)
            key = f"{v}_{kind}"
            table[key] = score_runs(
                {s: {key: ov[s][key]} for s in range(4)}, key, g1, v388, rm,
                dev_years)
            table[key]["wins"] = table[v]["wins"]  # identical fills

    # ---- dev4 robust pick (V1 vs V2 only) ----
    cand = {v: table[v] for v in ("V1", "V2") if v in table}
    elig = {v: t for v, t in cand.items()
            if t["DDmax_full"] <= 20 and t["losing_dev4"] == 0}
    pool = elig or cand
    above = {v: t for v, t in pool.items() if t["Rdev4"] >= 5}
    pool2 = above or pool
    best = max(sorted(pool2), key=lambda v: (pool2[v]["Wdev4"], pool2[v]["Rdev4"]))

    # ---- last-year window (pick only, scored ONCE) ----
    plast = TMP / "runs_last_base.pkl"
    if plast.exists():
        last = pickle.loads(plast.read_bytes())
        assert set(last) == {0, 1, 2, 3}, sorted(last)
        assert set(last[0]) == {best}, (best, sorted(last[0]))
        full = score_runs(last, best, g1, v388, rm, [0, 1, 2, 3, 4])
        for y in dev_years:  # last-stage run must match dev-stage on years 0..3
            assert full["years_R"][y] == table[best]["years_R"][y], (y, full, table[best])
            assert full["years_DD"][y] == table[best]["years_DD"][y], (y, full, table[best])
        print(f"{best} last-stage matches dev on years 0..3; Y4:",
              full["years_R"][4], full["years_DD"][4], flush=True)
        table[f"{best}_full"] = full
        for kind in ("CTRL", "APR15"):
            ov = overlay_runs(last, best, kind)
            srckey = f"{best}_{kind}"
            key = f"{srckey}_full"
            table[key] = score_runs(
                {s: {key: ov[s][srckey]} for s in range(4)}, key, g1, v388, rm,
                [0, 1, 2, 3, 4])
            table[key]["wins"] = full["wins"]

    # ---- S5 Bybit dev window (pick only) + REF_S5 side-by-side ----
    ps5 = TMP / "runs_dev_S5.pkl"
    if ps5.exists():
        s5 = pickle.loads(ps5.read_bytes())
        assert set(s5[0]) == {best}, (best, sorted(s5[0]))
        table[f"{best}_S5"] = score_runs(s5, best, g1, v388, rm, dev_years)
    c2b = json.loads((C2B / "tmp/c2bybit_table.json").read_text())["table"]
    table["REF_S5_side"] = {k: c2b["REF_S5"][k] for k in
                            ("years_R", "years_DD", "Rdev4", "Wdev4", "DDdev4",
                             "R5y", "W5y", "full_path_dd", "DDmax_full")}

    # ---- stored REF full-window row (labelled, never recomputed) ----
    table["REF_stored"] = dict(
        years_R=[r for r, _ in exp["years"]],
        years_DD=[d for _, d in exp["years"]],
        R5y=exp["R"], W5y=exp["W"], DD5y=exp["DD"],
        losing_5y=exp.get("losing", 0), full_path_dd=exp["full_path_dd"],
        Rdev4=geo([r for r, _ in exp["years"]][:4]),
        Wdev4=min(r for r, _ in exp["years"][:4]),
        DDdev4=max(d for _, d in exp["years"][:4]),
        losing_dev4=sum(r < 0 for r, _ in exp["years"][:4]))

    (TMP / "spotlongs_table.json").write_text(json.dumps(
        {"table": table,
         "pick": best,
         "ref_gate": {"years": exp["years"], "R": exp["R"], "DD": exp["DD"],
                      "full_path_dd": exp["full_path_dd"]}}, indent=1))
    print("dev table:", {v: (table[v]["Rdev4"], table[v]["Wdev4"],
                             table[v]["DDmax_full"], table[v]["losing_dev4"])
                         for v in cand}, flush=True)
    print("dev4 robust pick:", best, flush=True)

    out = {
        "meta": {
            "ref": "v421 R2B1D17BFG2 (V0 gate reproduces dev 0..3 to digit; REF full row stored)",
            "variants": ["V0 gate", "V1 all longs spot APR10", "V2 gated spot APR10",
                         "V1_CTRL/V2_CTRL exposure-matched (same fills + funding back, no borrow)",
                         "V1_APR15/V2_APR15 stress (same fills, borrow x1.5)",
                         "S5 Bybit-price row for the pick (short 2021 window labelled)"],
            "costs": "maker 0.0002 / taker 0.00055, book longs spot 0 funding, borrow APR 10/15% on max(0, spot-long - equity)",
            "metric": "reset_metric.year_reset per anchor year + v388.mix full-path DD; robust pick on dev4 only",
            "overlay_note": ("CTRL/APR15 are accounting overlays on identical fills "
                             "(close equity iterated per bar; eq_min scaled proportionally)"),
        },
        "table": table,
        "pick": best,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print("saved results.json + tmp/spotlongs_table.json", flush=True)


if __name__ == "__main__":
    main()
