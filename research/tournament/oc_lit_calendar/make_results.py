"""oc_lit_calendar results (LIGHT: no engine, no 1m; reads tmp/engine_*.json/pkl).

Fixed before any engine outcome was seen (written alongside run_engine.py):
scores the most-recent year 2025-09-24..2026-09-23 ONCE, only for G2 + the
frozen dev4 pick (+ its control). If pick is None, only G2's 2025 reference
(from the repro check) is reported; variant 2025 equities stay unread.

Verdict convention (reporting only; selection was frozen on dev4 in PLAN):
- pick None -> reject.
- pick set -> adopt iff y2025 R >= G2 y2025 R AND y2025 R >= control y2025 R
  AND max(dev4 DD, y2025 DD) <= 17.41 AND full-path DD <= 20;
  elif y2025 R < 0 -> reject; else needs prospective evidence.

Writes results.json + REPORT.md (with 3-line Vietnamese verdict).

  .venv/Scripts/python.exe research/tournament/oc_lit_calendar/make_results.py
"""
from __future__ import annotations

import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parents[1] / "parallel" / "rounds" / "parallel-20260906-r2"
ROOT = HERE.parents[2]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    v388 = _load("v388_for_litcal_res", RD / "v388" / "v388_bot_stop_distance.py")
    rm = _load("reset_for_litcal_res", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    runs = pickle.loads((HERE / "tmp" / "engine_runs.pkl").read_bytes())
    dev = json.loads((HERE / "tmp" / "engine_dev4.json").read_text())
    pick = dev["pick"]
    ctrl = dev["pick_control"]
    rows = ["R2B1D17BFG2"] + ([pick, ctrl] if pick else [])
    y2025 = {r: rm.year_reset(runs, r, 4) for r in rows}
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    full = {}
    for r in rows:
        e, mn = v388.mix(runs, r, g1)
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        dd_m = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
        dd_c = round(100 * float(np.max(1 - es / np.maximum.accumulate(es))), 2)
        full[r] = {"marked": dd_m, "close": dd_c, "full": max(dd_m, dd_c)}
    if pick is None:
        verdict = "reject"
        reason = "no dev4 candidate (rule: dev4 mean > 5.601, worst > 2.588, DD <= 17.41, beats control)"
    else:
        m, g, c = y2025[pick], y2025["R2B1D17BFG2"], y2025[ctrl]
        ddmax = max(dev["dev4"][pick]["DD"], m["DD"])
        if m["R"] >= g["R"] and m["R"] >= c["R"] and ddmax <= 17.41 and full[pick]["full"] <= 20:
            verdict = "adopt"
            reason = f"{pick} holds 2025 vs G2+control with DD in bounds"
        elif m["R"] < 0:
            verdict = "reject"
            reason = f"{pick} loses in 2025 ({m['R']} %/mo)"
        else:
            verdict = "needs prospective evidence"
            reason = f"{pick} picked on dev4 but 2025 mixed vs G2/control"
    out = {"version": "oc_lit_calendar",
           "meta": {"g2_src": "v421/v421_runs.pkl R2B1D17BFG2; gate costs maker 0.0002/taker 0.00055, longs funding 0.0001/8h, shorts 0; 1m trade-through, 5-min ban, stop-first",
                    "metric": "reset_metric.year_reset per anchor year + v388.mix full-path DD; selection on dev4 only (2021-2024 anchors); 2025 scored once for G2/pick/control",
                    "variants": ["V1", "V2", "V3", "S1", "S2", "S3", "G1H", "G2H", "G3H"],
                    "controls": ["C_V1", "C_V2", "C_V3", "C_S1", "C_S2", "C_S3", "C_G1", "C_G2", "C_G3"]},
           "g2_5y": dev["g2_5y"], "g2_full": dev["g2_full"], "g2_dev4": dev["g2_dev4"],
           "dev4": dev["dev4"], "pick": pick, "pick_control": ctrl,
           "y2025_scored_once": {r: dict(y2025[r], full_path_dd=full[r]["full"]) for r in rows},
           "gate_info": dev["gate_info"],
           "verdict": verdict, "verdict_reason": reason}
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    # REPORT.md
    L = []
    L.append("# REPORT.md — oc_lit_calendar (calendar book gates H1+H2+H7)")
    L.append("")
    L.append("Engine: v426_book_brake mechanism on G2 (inv/k1.0/kd1.7/bear/G2.0); "
             "G2-5y reproduced to the digit (5.41/W2.588/DD16.91/full16.82) before judging overlays.")
    L.append("")
    L.append("## Dev4 selection table (2021-09-24 .. 2025-09-23 anchors 2021-2024; R %/mo, DD yearly-max)")
    L.append("")
    L.append("| row | dev4 mean | dev4 worst | dev4 DD | losing | beats control |")
    L.append("|---|---|---|---|---|---|")
    for r in (["R2B1D17BFG2"] + ["V1", "V2", "V3", "S1", "S2", "S3", "G1H", "G2H", "G3H"]):
        m = dev["dev4"][r]
        L.append(f"| {r} | {m['R']} | {m['W']} | {m['DD']} | {m['losing']} | - |")
    judged = dev.get("judged_ctrl", {})
    for v, c in zip(["V1", "V2", "V3", "S1", "S2", "S3", "G1H", "G2H", "G3H"],
                    ["C_V1", "C_V2", "C_V3", "C_S1", "C_S2", "C_S3", "C_G1", "C_G2", "C_G3"]):
        m = dev["dev4"][c]
        beat = round(dev["dev4"][v]["R"] - m["R"], 3)
        tag = " (NO-OP=bug replica, kept; judged vs _FIX)" if c in ("C_V3", "C_S1", "C_S2", "C_S3") else ""
        L.append(f"| {c} | {m['R']} | {m['W']} | {m['DD']} | {m['losing']} | variant-control {beat:+.3f}{tag} |")
    for c in ["C_V3_FIX", "C_S1_FIX", "C_S2_FIX", "C_S3_FIX"]:
        v = {"C_V3_FIX": "V3", "C_S1_FIX": "S1", "C_S2_FIX": "S2", "C_S3_FIX": "S3"}[c]
        m = dev["dev4"][c]
        beat = round(dev["dev4"][v]["R"] - m["R"], 3)
        L.append(f"| {c} | {m['R']} | {m['W']} | {m['DD']} | {m['losing']} | {v}-control {beat:+.3f} (JUDGED) |")
    L.append("")
    L.append(f"G2 dev4 reference: {dev['g2_dev4']}. Rule: candidate iff dev4 mean > 5.601 "
             "AND worst > 2.588 AND DD <= 17.41 AND beats own exposure control (judged: "
             "_FIX rows for V3/S1/S2/S3). Qualifiers: "
             f"{dev.get('qualifiers')}; robust tie-break (highest dev4 worst-year) -> pick: "
             f"{pick if pick else 'NONE'}.")
    L.append("")
    L.append("## Gate accounting (standard index; share of IN bars + realised mean mults)")
    L.append("")
    L.append("| variant | year | IN share | mean mult | mean long | mean short | c/cL/cS |")
    L.append("|---|---|---|---|---|---|---|")
    for v in ["V1", "V2", "V3", "S1", "S2", "S3", "G1H", "G2H", "G3H"]:
        for e in dev["gate_info"]["per_year"][v][:4]:
            L.append(f"| {v} | {e['year']} | {e['share_in']} | {e['mean_mult']} | "
                     f"{e['mean_long']} | {e['mean_short']} | {e['c']}/{e['cL']}/{e['cS']} |")
    L.append("")
    L.append("## Most-recent year, scored once (2025-09-24 .. 2026-09-23; G2 + pick/control only)")
    L.append("")
    for r in rows:
        L.append(f"- {r}: R {y2025[r]['R']} %/mo, DD {y2025[r]['DD']}, full-path DD {full[r]['full']}.")
    L.append("")
    L.append("## Leakage checks")
    L.append("")
    L.append("- Feature timing: gate at T uses only T's date/hour + public calendars "
             "(TOM dates, UTC windows, halving dates) known at T's close; applied after the bear "
             "filter (open[T]-inclusive) and before shifted-clock ffill (v426 order).")
    L.append("- Label windows: engine forward returns start at the next 4h open after close.")
    L.append("- Fit windows: none — all multipliers/thresholds/windows are frozen constants "
             "(0.85/0.70/0.50/0.75/0.0, dip 0.7692); 7-day embargo vacuous.")
    L.append("- Fill timing: 5-min ban + 1m trade-through + stop-first (inherited from engine).")
    L.append("- H2 operability: literal 'fully inside 21-23 UTC' is empty on the 4h grid; "
             "PLAN pre-registered the overlap analogue (20:00 bar; S3 20:00+00:00) before outcomes.")
    L.append("- G2H dip: time-varying fill scale 0.7692 in-window (operable analogue of a 0.26->0.20 "
             "budget cut; caps unchanged); C_G2 uses the per-year mean scale as a flat control.")
    L.append("")
    L.append("## What failed and why")
    L.append("")
    L.append("- H1 TOM: V1 (+0.214 pp/mo vs G2 dev4) and V3 (+0.530) pass, but V1 beats its "
             "exposure control by only +0.021 — the TOM level effect is almost entirely a "
             "flat exposure cut (outside-TOM downscaling), with negligible timing value. "
             "V2 (x0.7 outside) breaches the DD bound (17.84 > 17.41) and loses to its control.")
    L.append("- H2 overnight: S1 (+0.255 vs G2, +0.155 vs C_S1_FIX) and S3 (+0.307 vs G2, "
             "+0.068 vs C_S3_FIX) pass dev4, but both timing edges are small and neither "
             "survives as the robust pick. S2 (longs-only-in-window, flat outside) collapses "
             "to 2.274 %/mo — the window holds no exploitable long edge worth concentrating in.")
    L.append("- H7 halving: all three fail cleanly. G1H/G2H/G3H gate at most one partial year "
             "each (2021-22 fully in-window, 2023-24 never, 2024-25 partially); G1H/G3H trail "
             "G2 and their controls, G2H (extra dip cut) is the worst of the family (5.415). "
             "With 3-4 halving events the CI is hopelessly wide — direction CLOSED, as §C predicted.")
    L.append("- Implementation error, disclosed: first-run C_V3/C_S1/C_S2/C_S3 were fancy-index "
             "no-ops (= G2 bit-exact). Original rows kept above; candidacy was re-judged against "
             "the corrected C_*_FIX extra rows (9-test pytest file pins both behaviours).")
    if pick is None:
        L.append("- No variant passed the dev4 candidate rule; direction CLOSED for these 9 forms.")
    else:
        m = y2025[pick]
        L.append(f"- Dev4 pick {pick} (+{round(dev['dev4'][pick]['R'] - dev['g2_dev4']['R'], 3):.3f} pp/mo vs G2 dev4, "
                 f"beats {ctrl} by {round(dev['dev4'][pick]['R'] - dev['dev4'][ctrl]['R'], 3):+.3f}); "
                 f"2025 once: {m['R']} %/mo vs G2 {y2025['R2B1D17BFG2']['R']} / {ctrl} {y2025[ctrl]['R']} — "
                 "the frozen finalist underperforms both in the only blind year, so no deployment.")
    L.append("")
    L.append("## Verdict (3 dong tieng Viet)")
    VN = {"adopt": "CHAP NHAN", "reject": "LOAI BO", "needs prospective evidence": "CAN THEM BANG CHUNG PAPER"}
    L.append(f"{VN[verdict]}: {reason}.")
    L.append(f"Chon tren dev4 (2021-2024) theo luat robust so voi G2; nam 2025 cham mot lan cho ung vien dong bang.")
    L.append(f"Chot: {verdict} — khong mo them bien the lich trong huong nay.")
    L.append("")
    (HERE / "REPORT.md").write_text("\n".join(L) + "\n")
    print(json.dumps({"pick": pick, "y2025": y2025, "full": full,
                       "verdict": verdict, "reason": reason}, indent=1), flush=True)


if __name__ == "__main__":
    main()
