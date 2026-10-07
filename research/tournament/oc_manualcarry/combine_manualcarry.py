"""oc_manualcarry: overlay the frozen oc_cashcarry sleeve on honest MANUAL rows.

Assignment: docs/opencode/OPENCODE_W_oc_manualcarry.md. LIGHT, RAM < 1.5 GB,
no engine reruns, one process, 4h/JSON data only (no 1m, no hourly downloads).

Base rows (best honest MANUAL rows named in docs/FINAL_REPORT_VI):
- M5_human (15', night-skip, agents ON): research/diagnostics/oc_manualcap/
  results.json row M5_human (R5 3.728, maxDD 17.94, fullDD 17.79, book win
  64.82%, n=3744). Stored equity:
  research/diagnostics/oc_manualcap/oc_manualcap_runs.pkl row M5_human
  (same numbers in research/diagnostics/oc_manualnight/results.json).
- M5_human_G15 / M5_human_G10 (order-placement caps):
  oc_manualcap/results.json rows (3.006/14.93, 2.615/13.54). Stored equity:
  oc_manualcap_runs.pkl rows M5_human_G15 / M5_human_G10.
- M5_humanBF (MANUAL + bear-book, human calendar): research/diagnostics/
  oc_manualbf/results.json row M5_humanBF y5 (R 3.609, DD 21.55, book win
  66.35%, n=3741). Stored equity:
  research/diagnostics/oc_manualbf/oc_manualbf_runs.pkl row M5_humanBF.
- M5_humanBF_top2 (MANUAL top-2 dip): research/diagnostics/oc_manual2/
  results.json row M5_humanBF_top2 y5 (R 3.060, DD 19.53, book win 66.91%,
  n=3844). Stored equity:
  research/diagnostics/oc_manual2/oc_manual2_runs.pkl row M5_humanBF_top2.

Carry sleeve REUSED UNCHANGED from research/tournament/oc_cashcarry
(pre-registered PLAN.md + analyze_cashcarry.py + results.json): one entry per
quarterly contract (next-quarter when front has <= 7 d left), ENTER iff
annualised basis ln(F/S)*365/DTE >= 4 %/yr, equal-notional spot long +
quarterly short, hold to delivery, fees spot 0.001/side + futures 0.00055
entry / 0.0002 delivery (drag 0.00275 of allocated). This script reads the 33
entered trades verbatim (asserted: 33 entered / 13 skipped / 2 incomplete,
threshold 0.04, every entered pair net positive) and reuses the frozen
per-year sums grouped by ENTRY. Same roll rule the assignment names (4 human
roll decisions per year: when <= 7 days remain, check basis >= 4 %/yr; each
entered pair is ~3 manual tickets: spot buy + futures short at entry, spot
sell at delivery while the future auto-settles).

Combination (YEARLY LEVEL, labelled): per anchor year, with base yearly
monthly rate Rb and carry year sum S (sum of ret_alloc over trades entered
that year),
  T_base = (1 + Rb/100)^12 - 1,
  C(f) = f * S  (carry P&L in year-start-equity units; f per-coin sizing,
  yearly rebalance, same convention as oc_cashcarry PLAN + oc_carryd13
  sizing_note),
  T_comb = T_base + C(f),
  R_comb = ((1 + T_comb)^(1/12) - 1) * 100.
Yearly DD_comb = base yearly DD (conservative: no DD benefit claimed; the
carry sleeve's worst 4h-close MtM is -0.25/-0.18/-0.66/-0.10/-0.54% of the
account at f=0.25, small next to MANUAL DD ~13-22%, and troughs do not
coincide -- the equity-level MAN case in oc_carrycombo measured a slight DD
improvement, so holding DD flat is conservative). Full-path DD = base
full-path DD where stored (oc_manualcap rows), else null with the base max
yearly DD as the conservative proxy (labelled). 5y mean = geometric mean of
the yearly monthly factors (same as v424). POST-HOC, REPORTING ONLY: every
input year is research data; the carry rule itself was fixed before any
combination (oc_cashcarry PLAN pre-registered); needs prospective paper like
everything else.

Relation to research/tournament/oc_carryd13/combine_carryd13.py: that script
is the equity-level hourly-mark combination for BOT rows and is reused here
only as the frozen-carry definition (same 33 trades, same fees, same
threshold, same f convention); it is NOT re-run (it needs
research/tournament/ext/hourly_ext.parquet, absent from this checkout, plus
v424_runs.pkl hourly plumbing). MANUAL is combined at the yearly level and
this file says so; the M5_human yearly-level result is cross-checked against
the equity-level M5_human+carry rows in oc_carrycombo/results.json
(MAN_f0.25 3.746 / MAN_f0.5 3.765).

Usage: .venv/Scripts/python.exe research/tournament/oc_manualcarry/combine_manualcarry.py
Reads: oc_manualcap/results.json, oc_manualbf/results.json,
  oc_manual2/results.json, oc_cashcarry/results.json,
  oc_carrycombo/results.json (cross-check only).
Writes: research/tournament/oc_manualcarry/results.json
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
CAP = ROOT / "research/diagnostics/oc_manualcap/results.json"
BF = ROOT / "research/diagnostics/oc_manualbf/results.json"
M2 = ROOT / "research/diagnostics/oc_manual2/results.json"
CC = ROOT / "research/tournament/oc_cashcarry/results.json"
COMBO = ROOT / "research/tournament/oc_carrycombo/results.json"

ANCHORS = ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
F_ROWS = [0.25, 0.5]

# (results file, key path, equity pkl, equity row, years_R key, years_DD key,
#  book_win, book_trades, fullDD-or-None, short label)
BASES = [
    ("oc_manualcap/M5_human", CAP, ("M5_human",),
     "research/diagnostics/oc_manualcap/oc_manualcap_runs.pkl", "M5_human"),
    ("oc_manualcap/M5_human_G15", CAP, ("M5_human_G15",),
     "research/diagnostics/oc_manualcap/oc_manualcap_runs.pkl", "M5_human_G15"),
    ("oc_manualcap/M5_human_G10", CAP, ("M5_human_G10",),
     "research/diagnostics/oc_manualcap/oc_manualcap_runs.pkl", "M5_human_G10"),
    ("oc_manualbf/M5_humanBF", BF, ("M5_humanBF", "y5"),
     "research/diagnostics/oc_manualbf/oc_manualbf_runs.pkl", "M5_humanBF"),
    ("oc_manual2/M5_humanBF_top2", M2, ("M5_humanBF_top2", "y5"),
     "research/diagnostics/oc_manual2/oc_manual2_runs.pkl", "M5_humanBF_top2"),
]


def _monthly_to_total(R: float) -> float:
    return (1.0 + R / 100.0) ** 12 - 1.0


def _total_to_monthly(T: float) -> float:
    return ((1.0 + T) ** (1.0 / 12) - 1.0) * 100.0


def main() -> None:
    cc = json.loads(CC.read_text())
    assert cc["meta"]["threshold_ann_basis"] == 0.04
    assert len(cc["trades"]) == 33 and cc["n_skipped"] == 13 and cc["n_incomplete"] == 2
    assert cc["pooled"]["n_trades"] == 25
    for t in cc["trades"]:
        assert t["ann_basis"] >= 0.04 - 1e-9
        gross = (t["S_del"] - t["S_entry"]) / t["S_entry"] + (t["F_entry"] - t["S_del"]) / t["F_entry"]
        assert abs(t["ret_alloc"] - round(gross - 0.00275, 6)) < 1e-9
        assert t["ret_alloc"] > 0
    assert [y["year"] for y in cc["years"]] == ANCHORS
    carry_sum = [float(y["sum_ret_alloc"]) for y in cc["years"]]
    carry_worst_alloc = [float(y["worst_mtm_alloc"]) for y in cc["years"]]
    in_window = int(cc["pooled"]["n_trades"])

    bases = {}
    for label, path, key, pkl, _row in BASES:
        d = json.loads(path.read_text())
        node = d["rows"]
        for k in key:
            node = node[k]
        if "years_R" in node:
            yrs_R = [float(x) for x in node["years_R"]]
            yrs_DD = [float(x) for x in node["years_DD"]]
            yrs_bw = [float(x) for x in node.get("years_book_win", [])]
            R5, W, maxDD = float(node["R5"]), float(node["W"]), float(node["maxDD"])
            fullDD = float(node["fullDD"]) if node.get("fullDD") is not None else None
            bw, bt = float(node["book_win"]), int(node["book_trades"])
        else:  # oc_manualbf / oc_manual2 y5 shape (single-clock mean over 4 phases)
            yrs_R = [float(x) for x in node["years_monthly"]]
            yrs_DD = [None, None, None, None, None]
            # per-year DD + book-win-by-year not stored for these rows
            yrs_bw = []
            R5, W, maxDD = float(node["R"]), float(node["W"]), float(node["DD"])
            fullDD, bw = None, float(node["book_win"])
            bt = int(node["book_trades"])
        bases[label] = {"years_R": yrs_R, "years_DD": yrs_DD, "years_book_win": yrs_bw,
                        "R5": R5, "W": W, "maxDD": maxDD, "fullDD": fullDD,
                        "book_win": bw, "book_trades": bt, "equity_pkl": pkl, "equity_row": _row}

    combos = []
    for label, b in bases.items():
        for f in F_ROWS:
            years = []
            for i, a in enumerate(ANCHORS):
                Rb = b["years_R"][i]
                Tb = _monthly_to_total(Rb)
                Cf = f * carry_sum[i]
                Tc = Tb + Cf
                Rc = _total_to_monthly(Tc)
                years.append({
                    "anchor": a,
                    "R": round(Rc, 3),
                    "DD": b["years_DD"][i],
                    "base_R": Rb,
                    "base_DD": b["years_DD"][i],
                    "carry_R_pp": round(Rc - Rb, 3),
                    "carry_year_pct": round(Cf * 100, 4),
                    "carry_worst_acct_pct": round(f * carry_worst_alloc[i] * 100, 4),
                    "total_pct": round(Tc * 100, 4),
                })
            R5 = round((__import__("numpy").prod([1 + y["R"] / 100 for y in years]) ** (1 / 5) - 1) * 100, 3)
            W = min(y["R"] for y in years)
            per_year_dd = [y["DD"] for y in years if y["DD"] is not None]
            if per_year_dd:
                DDmax = max(per_year_dd)
                dd_note = None
            else:
                # oc_manualbf / oc_manual2 store only overall DD, no per-year DD:
                # use the overall base DD as the conservative yearly-DD proxy (labelled).
                DDmax = b["maxDD"]
                dd_note = ("no per-year DD stored for this row; base overall DD used as "
                           "the conservative max-yearly-DD proxy (yearly-level, labelled)")
            losing = sum(1 for y in years if y["R"] < 0)
            floor = bool(R5 >= 5.0 and DDmax < 20.0 and b["book_win"] >= 0.55 and losing == 0)
            combos.append({
                "row": label, "f": f, "years": years,
                "R_5y": R5, "W": W, "DD_maxyearly": DDmax,
                "DD_maxyearly_note": dd_note,
                "full_path_dd": b["fullDD"],
                "full_path_dd_note": ("base full-path DD (yearly-level proxy, conservative: "
                                       "equity-level MAN case improves 17.79 -> 17.19/16.61)")
                if b["fullDD"] is not None else
                ("no stored full-path equity DD for this row; base max yearly DD "
                 "is the conservative proxy (yearly-level, labelled)"),
                "losing_years": losing,
                "book_win": b["book_win"], "book_trades": b["book_trades"],
                "carry_note": (f"carry adds zero book trades; {in_window} in-window carry pairs "
                               "(33 entered / 8 pre-window excluded) all net positive on "
                               "allocated capital, reported separately"),
                "manual_floor_all": floor,
            })

    # cross-check M5_human yearly-level vs equity-level oc_carrycombo (tolerance: method gap)
    cb = json.loads(COMBO.read_text())["rows"]
    check = {}
    for f, key in ((0.25, "MAN_f0.25"), (0.5, "MAN_f0.5")):
        mine = next(c for c in combos if c["row"] == "oc_manualcap/M5_human" and c["f"] == f)
        check[key] = {"mine_R5": mine["R_5y"], "equity_R5": cb[key]["R"],
                      "gap": round(abs(mine["R_5y"] - cb[key]["R"]), 4)}

    out = {
        "meta": {
            "bases": {k: {"R5": v["R5"], "W": v["W"], "maxDD": v["maxDD"], "fullDD": v["fullDD"],
                          "book_win": v["book_win"], "book_trades": v["book_trades"],
                          "equity_pkl": v["equity_pkl"], "equity_row": v["equity_row"],
                          "level": "yearly numbers stored; combination at the yearly level (labelled)"}
                      for k, v in bases.items()},
            "carry_rule": ("frozen oc_cashcarry (PLAN pre-registered): roll next-quarter at <=7d, "
                           "enter iff ann basis >= 4%, equal-notional spot long + quarterly short, "
                           "hold to delivery, fees spot 0.001/side + fut 0.00055/0.0002; "
                           "33 entered / 13 skipped / 2 incomplete reused verbatim"),
            "carry_years_ENTRY_grouped": [
                {"anchor": a, "sum_ret_alloc": s, "worst_mtm_alloc": w}
                for a, s, w in zip(ANCHORS, carry_sum, carry_worst_alloc)],
            "combination": ("YEARLY LEVEL (labelled): T_comb = (1+Rb/100)^12 - 1 + f*S; "
                            "R_comb = (1+T_comb)^(1/12) - 1; f of year-start equity, yearly "
                            "rebalance; DD_comb yearly = base yearly DD (conservative); "
                            "full-path DD = base value or conservative proxy (labelled per row)"),
            "sizing_note": ("carry sized f of year-start equity (yearly rebalance), same f "
                            "convention as oc_cashcarry PLAN + oc_carryd13; needs up to 2f extra "
                            "cash for spot legs when both coins open"),
            "human_actions": ("4 roll decisions per year (when <= 7 days remain, check basis >= "
                              "4 %/yr); each entered pair is ~3 manual tickets (spot buy + "
                              "futures short at entry, spot sell at delivery; future "
                              "auto-settles); 25 in-window pairs over 5 years ~= 5 pairs/year"),
            "reuse_note": ("oc_carryd13/combine_carryd13.py is the equity-level hourly-mark "
                           "combination for BOT rows and is NOT re-run here (needs "
                           "hourly_ext.parquet, absent, + v424 hourly plumbing); its frozen-carry "
                           "definition (same 33 trades/fees/threshold/f) is reused verbatim"),
            "data_cap": "2026-09-24T00:00:00Z",
            "post_hoc": True, "reporting_only": True,
        },
        "combos": combos,
        "crosscheck_vs_equity_level": check,
        "checks": {
            "n_combos": len(combos),
            "any_reaches_manual_floor": any(c["manual_floor_all"] for c in combos),
        },
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    for c in combos:
        print(f"{c['row']} f={c['f']}: R5={c['R_5y']} W={c['W']} DDmax={c['DD_maxyearly']} "
              f"full={c['full_path_dd']} floor={c['manual_floor_all']}")
    print("crosscheck:", json.dumps(check))
    print("any reaches MANUAL floor:", out["checks"]["any_reaches_manual_floor"])


if __name__ == "__main__":
    main()
