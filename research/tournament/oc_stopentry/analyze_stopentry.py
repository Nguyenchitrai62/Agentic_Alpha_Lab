"""oc_stopentry scoring (CPU-only): gate + dev4 / Y4-diagnostic / 5y + full-path DD.

Reads tmp/runs_<stage>_<fric>.pkl (REF/V1/V2/C_* full-window runs per shift),
scores with reset_metric.year_reset + v388.mix, checks the reproduction gate
(REF == v421 G2 to the digit), builds tmp/ctrl.json (per-year constant
exposure multipliers c_y = V_filled / REF_filled from book_fill |weight| sums,
fallback 1.0) for the C rows, writes tmp/stopentry_table.json + results.json.
REPORT.md is written from that table only.
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
VARIANTS = ("REF", "V1", "V2", "C_V1", "C_V2")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def geo(rs, nd=3):
    return round(100 * (float(np.prod([1 + r / 100 for r in rs])) ** (1 / len(rs)) - 1), nd)


def score_runs(runs, key, g1, v388, rm, years=(0, 1, 2, 3)):
    """Score one variant key from {shift: {key: run}} like analyze_c2bybit.

    years: which anchor years to score (dev runs cover 0..3 only; the dev run's
    hourly path ends at DEV1 so year 4 would score a flat forward-fill — never
    scored from dev runs). Last/S5 runs pass years=(0..4) / (0..3, short-2021).
    """
    rr = {s: {key: runs[s][key]["run"]} for s in range(4)}
    yl = list(years)
    yrs = [rm.year_reset(rr, key, y) for y in yl]
    Rs = [y["R"] for y in yrs]
    DDs = [y["DD"] for y in yrs]
    e, mn = v388.mix(rr, key, g1)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    pathdd = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
    wins = []
    fg = []
    stop = []
    for y in yl:
        nb = sum(runs[s][key]["wins"][y]["nb"] for s in range(4))
        wb = sum(runs[s][key]["wins"][y]["wb"] for s in range(4))
        nr = sum(runs[s][key]["wins"][y]["nr"] for s in range(4))
        wr = sum(runs[s][key]["wins"][y]["wr"] for s in range(4))
        wins.append(
            dict(
                nb=nb,
                wb=wb,
                nr=nr,
                wr=wr,
                book_win=round(wb / nb, 4) if nb else None,
                rung_win=round(wr / nr, 4) if nr else None,
                all_win=round((wb + wr) / (nb + nr), 4) if (nb + nr) else None,
            )
        )
        f = sum(float(runs[s][key]["fills"][y]["fg"]) for s in range(4))
        ns = sum(int(runs[s][key]["fills"][y]["nstop"]) for s in range(4))
        nl = sum(int(runs[s][key]["fills"][y]["nlim"]) for s in range(4))
        fg.append(round(f, 6))
        stop.append(dict(nstop=ns, nlim=nl, stop_share=round(ns / (ns + nl), 4) if (ns + nl) else None))
    dev = Rs[:4] if len(Rs) >= 4 else Rs
    full5 = (len(yl) == 5)
    return dict(
        years=yl,
        years_R=Rs,
        years_DD=DDs,
        Rdev4=geo(dev),
        Wdev4=round(min(dev), 3),
        DDdev4=round(max(DDs[:4]), 2),
        losing_dev4=sum(r < 0 for r in dev),
        R5y=(geo(Rs) if full5 else None),
        W5y=(round(min(Rs), 3) if full5 else None),
        DD5y=(round(max(DDs), 2) if full5 else None),
        losing_5y=(sum(r < 0 for r in Rs) if full5 else None),
        full_path_dd=pathdd,
        DDmax_full=round(max(max(DDs), pathdd), 2),
        wins=wins,
        fill_gross=fg,
        stop_counts=stop,
    )


def build_ctrl(runs) -> dict[str, list[float]]:
    """c_y(V) = sum_s V_fg[y] / sum_s REF_fg[y] per year (dev runs).

    Year 4 has no dev bars (appended zeros) -> c_4 = 1.0 fallback (unused in dev,
    used only if a control ever ran last, which it never does). Fallback 1.0 when
    REF sum is 0/non-finite. Written to tmp/ctrl.json; diagnostic in-year.
    """
    import sys

    sys.path.insert(0, str(HERE))
    import stop_rule  # noqa: E402

    ref = [sum(float(runs[s]["REF"]["fills"][y]["fg"]) for s in range(4)) for y in range(5)]
    out = {}
    for v in ("V1", "V2"):
        cy = []
        for y in range(5):
            vv = sum(float(runs[s][v]["fills"][y]["fg"]) for s in range(4))
            cy.append(stop_rule.control_mult(vv, ref[y]) if y < 4 else 1.0)
        out[v] = [round(float(c), 6) for c in cy]
    (TMP / "ctrl.json").write_text(json.dumps(out, indent=1))
    print("ctrl.json:", out, flush=True)
    return out


def main():
    v388 = _load("v388_se", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("reset_se", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    exp = json.loads((RD / "v421/v421_result.json").read_text())["rows"]["R2B1D17BFG2"]

    p = TMP / "runs_dev_base.pkl"
    assert p.exists(), f"missing {p} — run compute_stopentry_engine.py --stage dev first"
    runs = pickle.loads(p.read_bytes())
    assert set(runs) == {0, 1, 2, 3}, sorted(runs)
    for s in range(4):
        assert "REF" in runs[s], (s, sorted(runs[s]))

    table = {}
    for v in VARIANTS:
        if v not in runs[0]:
            continue
        table[v] = score_runs(runs, v, g1, v388, rm, years=(0, 1, 2, 3))

    # ---- reproduction gate (dev stage): REF years 0..3 == v421 G2 to the digit.
    # The full 5y gate (years 0..4 + R + full-path) is asserted on the last-stage
    # REF run below; dev runs end at DEV1 so year 4 is never scored from them.
    for y in range(4):
        er, ed = exp["years"][y]
        assert table["REF"]["years_R"][y] == er, (y, table["REF"]["years_R"][y], er)
        assert table["REF"]["years_DD"][y] == ed, (y, table["REF"]["years_DD"][y], ed)
    print("REF dev gate PASS (years 0..3):", table["REF"]["years_R"], flush=True)

    # ---- exposure controls: (re)build c_y when V rows exist (idempotent) ----
    ctrls = None
    if "V1" in runs[0] and "V2" in runs[0]:
        ctrls = build_ctrl(runs)

    # ---- last-year window (REF + pick only): full 5y gate here ----
    plast = TMP / "runs_last_base.pkl"
    if plast.exists():
        last = pickle.loads(plast.read_bytes())
        for v in last.get(0, {}):
            table[f"{v}_last"] = score_runs(last, v, g1, v388, rm, years=(0, 1, 2, 3, 4))
        if "REF_last" in table:
            for y in range(5):
                er, ed = exp["years"][y]
                assert table["REF_last"]["years_R"][y] == er, (y, table["REF_last"]["years_R"][y], er)
                assert table["REF_last"]["years_DD"][y] == ed, (y, table["REF_last"]["years_DD"][y], ed)
            assert table["REF_last"]["R5y"] == exp["R"], (table["REF_last"]["R5y"], exp["R"])
            assert table["REF_last"]["DD5y"] == exp["DD"], table["REF_last"]["DD5y"]
            assert table["REF_last"]["full_path_dd"] == exp["full_path_dd"], table["REF_last"]
            print(
                "REF_last reproduces v421 G2 EXACTLY:",
                table["REF_last"]["years_R"],
                "full",
                table["REF_last"]["full_path_dd"],
                flush=True,
            )

    # ---- S5 Bybit dev window (REF + pick only) + REF_S5 side-by-side ----
    ps5 = TMP / "runs_dev_S5.pkl"
    if ps5.exists():
        s5 = pickle.loads(ps5.read_bytes())
        for v in s5.get(0, {}):
            table[f"{v}_S5"] = score_runs(s5, v, g1, v388, rm, years=(0, 1, 2, 3))
    c2b = json.loads((C2B / "tmp/c2bybit_table.json").read_text())["table"]
    table["REF_S5_side"] = {
        k: c2b["REF_S5"][k]
        for k in ("years_R", "years_DD", "Rdev4", "Wdev4", "DDdev4", "R5y", "W5y", "full_path_dd", "DDmax_full")
    }

    # ---- dev4 robust pick (V1 vs V2 only; controls never eligible) ----
    cand = {v: table[v] for v in ("V1", "V2") if v in table}
    if cand:
        elig = {v: t for v, t in cand.items() if t["DDmax_full"] <= 20 and t["losing_dev4"] == 0}
        pool = elig or cand
        above = {v: t for v, t in pool.items() if t["Rdev4"] >= 5}
        pool2 = above or pool
        best = max(sorted(pool2), key=lambda v: (pool2[v]["Wdev4"], pool2[v]["Rdev4"]))
    else:
        best = "none-eligible"
    (TMP / "stopentry_table.json").write_text(
        json.dumps(
            {
                "table": table,
                "pick": best,
                "ctrls": ctrls,
                "ref_gate": {
                    "years": exp["years"],
                    "R": exp["R"],
                    "DD": exp["DD"],
                    "full_path_dd": exp["full_path_dd"],
                },
            },
            indent=1,
        )
    )
    print(
        "dev table:",
        {v: (table[v]["Rdev4"], table[v]["Wdev4"], table[v]["DDmax_full"], table[v]["losing_dev4"]) for v in cand},
        flush=True,
    )
    print("dev4 robust pick:", best, flush=True)

    out = {
        "meta": {
            "ref": "v421 R2B1D17BFG2 (REF gate reproduces to digit)",
            "variants": [
                "REF gate",
                "V1 all book entries stop 5bps through P0 taker",
                "V2 stop only when |w| > pre-anchor median else passive limit",
                "C_V1/C_V2 exposure-matched (REF mechanism, per-year book_size c_y, diagnostic in-year)",
                "last (Y4 scored once for REF + pick) + S5 Bybit-price row for the pick (short 2021 labelled)",
            ],
            "costs": "maker 0.0002 (passive/TP/closes) / taker 0.00055 (stop entries, stops, market exits), longs pay 0.0001/8h, shorts 0",
            "metric": "reset_metric.year_reset per anchor year + v388.mix full-path DD; robust pick on dev4 only",
            "entry_scope": "flat->open orders only; in-position adds/reduces/closes stay passive G2 limits",
        },
        "table": table,
        "pick": best,
        "ctrls": ctrls,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print("saved results.json + tmp/stopentry_table.json", flush=True)


if __name__ == "__main__":
    main()
