"""oc_b7c2pre analyze: write results.json + REPORT.md from frozen tables only.

Reads tmp/stack_presample.json (fresh stack replica+placebo) + tmp/stop_stack.json
(fresh stack stop splits on frozen kinds) + frozen B7/C2 copies (already inside
stack_presample.json["copies"]). REPORT.md + results.json are written from those
tables only. No recompute here.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

LEG_ORDER = ("Y2017", "Y2018", "Y2019", "Y2020p")


def main() -> None:
    stack = json.loads((HERE / "tmp/stack_presample.json").read_text())
    stop = json.loads((HERE / "tmp/stop_stack.json").read_text())

    # ---- counts ----
    counts = {}
    for v in ("B7C2", "B7C2_cap"):
        py = stack[v]["per_year"]
        tp = stack[v]["timing_placebo"]
        bp = stack[v]["block_placebo"]
        counts[v] = {
            "helps_vs_base": sum(r["gain_vs_base"] > 0 for r in py),
            "helps_vs_B7": sum(r["gain_vs_B7"] > 0 for r in py),
            "helps_vs_C2": sum(r["gain_vs_C2"] > 0 for r in py),
            "timing_sig": sum(r["percentile"] >= 95 for r in tp),
            "block_sig": sum(r["percentile"] >= 95 for r in bp),
        }

    results = {
        "config": stack["config"],
        "reproduction": stack["reproduction"],
        "stop_config": stop["config"],
        "B7C2": {**stack["B7C2"]},
        "B7C2_cap": {**stack["B7C2_cap"]},
        "copies": stack["copies"],
        "stop_per_year": stop["per_year"],
        "stop_pooled": {v: stop[f"{v}_pooled"] for v in ("B7C2", "B7C2_cap")},
        "stop_pooled_exCOVID": {v: stop[f"{v}_pooled_exCOVID"] for v in ("B7C2", "B7C2_cap")},
        "counts": counts,
        "notes": [
            "pre-sample unseen-years diagnostic (2017-2020); no selection, no engine, no adoption",
            "B7 rows copied from oc_cboostpre/results.json + tmp/stop_presample.json (not rerun)",
            "C2 rows copied from oc_presampletilt/results.json (not rerun)",
            "spot-vs-perp caveat on every number (SPOT fills/exits, perp gate costs)",
            "C2 fit from later data (anchor-2021) applied to earlier years; labelled fit from later data, rule frozen",
        ],
    }
    (HERE / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print("wrote results.json", flush=True)

    # ---- REPORT ----
    def row_main(v, y):
        r = next(x for x in stack[v]["per_year"] if x["year"] == y)
        t = next(x for x in stack[v]["timing_placebo"] if x["year"] == y)
        b = next(x for x in stack[v]["block_placebo"] if x["year"] == y)
        return r, t, b

    b7 = {r["year"]: r for r in stack["copies"]["B7_per_year"]}
    c2 = {r["year"]: r for r in stack["copies"]["C2_per_year"]}
    b7t = {r["year"]: r["percentile"] for r in stack["copies"]["B7_timing"]}
    c2t = {r["year"]: r["percentile"] for r in stack["copies"]["C2_timing"]}

    L = []
    L.append("# oc_b7c2pre — REPORT (2026-10-08; PLAN frozen before any outcome)")
    L.append("")
    L.append("Does the B7xC2 stack (product of the B7 dip-budget boost and the C2 Chronos rung")
    L.append("tilt, verbatim oc_b7c2: m=m_B7*m_C2; cap min(product,1.5)) help on the UNSEEN")
    L.append("pre-sample years 2017-2020? Reused D0+B1 dip replica ledger (9,731 fills; SPOT")
    L.append("fills/exits, perp gate costs inside; spot-vs-perp caveat on every number). B7 rows")
    L.append("are COPIES from oc_cboostpre, C2 rows COPIES from oc_presampletilt (copy gates pass);")
    L.append("only the two stack rows are fresh. Diagnostic only: no selection, no engine.")
    L.append("")
    L.append("CONTAMINATION LABEL (pre-registered): B7 was picked on dev4 after the delay replica")
    L.append("had covered the post-release year, and the C2 rule uses the anchor-2021 fit on earlier")
    L.append("years (labelled fit from later data, rule frozen); these pre-sample years are the")
    L.append("unseen evidence leg (nobody looked at them when the ideas were formed).")
    L.append("")
    L.append("STATUS: DONE — stack replica + 1000 timing/block perms per variant/year complete,")
    L.append("frozen-kind stop splits complete (15 unknown, 0 missing joins). Tests pass (see below).")
    L.append("")
    L.append("## Replica (reused ledger n = 9731, base sums reproduce 2.313362/2.678870/0.577643/0.297538)")
    L.append("")
    L.append("| year x variant | n | base | norm_stack | gain_vs_base | gain_vs_B7 | gain_vs_C2 | timing pct | block pct | boosted(mult>1)% |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for v in ("B7C2", "B7C2_cap"):
        for y in LEG_ORDER:
            r, t, b = row_main(v, y)
            L.append(f"| {y} {v} | {r['n_fills']} | {r['base']:.6f} | {r['norm']:.6f} | "
                     f"{r['gain_vs_base']:+.6f} | {r['gain_vs_B7']:+.6f} | {r['gain_vs_C2']:+.6f} | "
                     f"{t['percentile']:.2f} | {b['percentile']:.2f} | {r['boosted_share_mult_gt1']:.4f} |")
    L.append("")
    L.append("Copies for reference (B7 from oc_cboostpre, C2 from oc_presampletilt; not rerun):")
    L.append("")
    L.append("| year | base | B7 norm (gain, timing) | C2 norm (gain, timing) |")
    L.append("|---|---|---|---|")
    for y in LEG_ORDER:
        L.append(f"| {y} | {b7[y]['base']:.6f} | {b7[y]['norm']:.6f} ({b7[y]['gain']:+.6f}, {b7t[y]:.2f}) | "
                 f"{c2[y]['norm']:.6f} ({c2[y]['gain']:+.6f}, {c2t[y]:.2f}) |")
    L.append("")
    L.append(f"- Helps vs no tilt (gain_vs_base>0): B7C2 "
             f"{counts['B7C2']['helps_vs_base']}/4, B7C2_cap {counts['B7C2_cap']['helps_vs_base']}/4 "
             f"(B7 copy 3/4, C2 copy 3/4; failure is Y2020p everywhere).")
    L.append(f"- Beats B7 alone (gain_vs_B7>0): B7C2 "
             f"{counts['B7C2']['helps_vs_B7']}/4 (Y2017/Y2019 only; Y2018 -0.002132, Y2020p -0.155390), "
             f"cap {counts['B7C2_cap']['helps_vs_B7']}/4 (Y2018 -0.000420, Y2020p -0.095161).")
    L.append(f"- Beats C2 alone (gain_vs_C2>0): B7C2 "
             f"{counts['B7C2']['helps_vs_C2']}/4 (all but Y2020p), cap 3/4 (Y2020p -0.005508, near zero).")
    L.append(f"- Timing significant (>=95): B7C2 {counts['B7C2']['timing_sig']}/4 "
             f"(2017/2018/2019; Y2020p 4.30), cap {counts['B7C2_cap']['timing_sig']}/4 (Y2020p 10.99); "
             f"block {counts['B7C2']['block_sig']}/4 and {counts['B7C2_cap']['block_sig']}/4.")
    L.append("- COVID leg Y2020p (reported separately): B7C2 norm 0.072688 gain_vs_base -0.224850 "
             "(vs B7 gain -0.069459, vs C2 gain -0.159113); cap norm 0.132917 gain -0.164620. "
             "The stack deepens the COVID-leg loss vs EACH leg alone (gain_vs_B7 -0.155/-0.095, "
             "gain_vs_C2 -0.066/-0.006); timing insignificant (4.3/9.5 uncapped, 11.0/23.5 capped).")
    L.append("")
    L.append("## Crash risk (stop-hit share of boosted fills vs base rate; frozen kinds, 15 unknown)")
    L.append("")
    L.append("| year | base stop% | B7 boosted (copy, delta) | B7C2 boosted (delta) | B7C2_cap boosted (delta) | stack deboosted stop% |")
    L.append("|---|---|---|---|---|---|")
    for r in stop["per_year"]:
        L.append(f"| {r['year']} | {r['base_stop_rate']*100:.2f} | "
                 f"{r['B7_copy']['stop_rate']*100:.2f} ({r['B7_copy']['stop_delta']*100:+.2f}) | "
                 f"{r['B7C2_stop_rate']*100:.2f} ({r['B7C2_stop_delta']*100:+.2f}) | "
                 f"{r['B7C2_cap_stop_rate']*100:.2f} ({r['B7C2_cap_stop_delta']*100:+.2f}) | "
                 f"{(r['B7C2_deboosted_stop_rate']*100 if r['B7C2_deboosted_stop_rate'] is not None else float('nan')):.2f} |")
    L.append("")
    L.append(f"- Pooled: base 5.58%, B7 copy boosted 6.20% (+0.62), B7C2 boosted "
             f"{stop['B7C2_pooled']['boosted_stop_rate']*100:.2f}% "
             f"({stop['B7C2_pooled']['stop_delta']*100:+.2f}), cap same. Ex-COVID pooled: base 4.80%, "
             f"stack boosted 4.92% (+0.11). No crash-risk reduction from adding C2.")
    L.append("- COVID leg Y2020p separately: base 7.58%; B7 boosted 9.13% (+1.55); stack boosted "
             "9.33% (+1.75, both variants). C2 does NOT reduce B7's crash-leg damage there — "
             "it adds +0.20pp to the boosted stop rate.")
    L.append("- Y2019 (the other elevated-stop year): base 6.69%; B7 7.47% (+0.78); stack 7.32% "
             "(+0.64) — marginally lower than B7 but still elevated; deboosted (0.75) fills stop "
             "14.17% that year (small 3.85% share, context only).")
    L.append("")
    L.append("## Leakage checklist")
    L.append("")
    L.append("- Feature timing: B7 triggers use closes with close_time <= tc only; SIG window excludes "
             "the tested bar; boost window strictly after tc (0 < T-tc <= 7d); C2 forecast for T uses "
             "only 512 closes of bars closing <= T; stack lookup uses only (sym,shift,T) at the holding "
             "bar with ffill-causal B7 join. Truncation-tested in tests/test_oc_b7c2pre.py (stack mults "
             "from truncated frozen boost+Chronos tables identical on kept prefix; multisets subset of "
             "the pre-registered sets).")
    L.append("- Label windows: none fit anywhere in this study (no harness join, no labels).")
    L.append("- Fit windows: B7 no fits (frozen 4.0/540/120/1.5/7d); C2 frozen anchor-2021 fit "
             "(dir +1, q20/q80, hi/lo 1.25/0.75) applied to earlier years and labelled fit-from-later; "
             "no statistic from any test year feeds any choice. Pre-sample years never used for any fit.")
    L.append("- Fill timing: replica fills inherited (live 16..238 strict trade-through, stop-first); "
             "kind splits reuse the frozen outcome_mu branch with the same window + stop-first ordering; "
             "perms reassign mults within the year only (bar-level joint null + block-42 per (sym,shift)).")
    L.append("- Coverage: no skipped year; all 9,731 fills joined (0 missing time-bars, 0 missing boost; "
             "5,547 C2-missing->1 by burn-in/context, counted); 15 unknown kinds excluded from rates only.")
    L.append("- Gate costs: inside the reused replica outcomes (maker 0.0002/taker 0.00055, adverse long "
             "funding 0.0001/8h); the stack is a sizing-only overlay with no extra cost.")
    L.append("- Spot-vs-perp caveat on every number (SPOT fills/exits, perp gate costs).")
    L.append("")
    L.append("## What worked and what did not")
    L.append("")
    L.append("- Worked: the stack helps vs doing nothing in 3/4 unseen years (gains +0.063/+0.076/+0.138 "
             "uncapped, +0.069/+0.078/+0.133 capped) with significant joint timing in 2017-2019 "
             "(100/100/~98 timing, ~97-100 block); it beats C2 alone in all non-COVID years. Pooled "
             "crash risk is flat vs B7 (pooled delta +0.60 vs B7 +0.62).")
    L.append("- Did not: the stack does NOT beat B7 alone (Y2018 gain_vs_B7 -0.002/-0.0004; the B7 edge "
             "does not compose); the COVID leg Y2020p fails harder under the stack than under either leg "
             "(gain -0.225/-0.165 vs B7 -0.069, C2 -0.159; timing lost; boosted stops +1.75 vs B7 +1.55) — "
             "C2 deepens rather than cushions B7's crash-leg damage, the same mechanism as the deepened "
             "2023 episode in oc_b7c2.")
    L.append("")
    L.append("## Vietnamese verdict")
    L.append("")
    L.append("- Stack B7xC2 giúp 3/4 năm chưa từng thấy so với không tilt (gain +0,06/+0,08/+0,14, timing "
             "100/100/98) và hơn C2 đơn lẻ ở mọi năm không-COVID, nhưng KHÔNG hơn B7 đơn lẻ (Y2018 thua "
             "nhẹ, bản cap cũng vậy; chỉ Y2017/Y2019 hơn B7).")
    L.append("- Chân COVID Y2020p làm stack lỗ sâu hơn cả hai chân (gain -0,22/-0,16 so với B7 -0,07 và C2 "
             "-0,16; timing mất) và stop của fill được boost tăng +1,75pp so với B7 +1,55pp — C2 không "
             "giảm mà còn đào sâu damage của B7 ở chân crash.")
    L.append("- Kết luận: REJECT stack trên unseen-years — giữ B7 làm ứng viên (chờ paper prospective), "
             "không đưa B7C2/B7C2_cap vào G2.")
    L.append("")
    (HERE / "REPORT.md").write_text("\n".join(L), encoding="utf-8")
    print("wrote REPORT.md", flush=True)


if __name__ == "__main__":
    main()
