"""Assemble oc_d_ddrank results.json + REPORT.md from frozen tmp outputs (no new compute)."""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
pre = json.loads((HERE / "tmp/ddrank_presample.json").read_text())
sec = json.loads((HERE / "tmp/ddrank_2021.json").read_text())
stop = json.loads((HERE / "tmp/stop_presample.json").read_text())

res = {
    "config": {
        "idea": "IDEAS12 #1 drawdown-rank rotation (buy the deepest coin harder)",
        "rule": "rank by trailing-30d DD-depth of own 4h closes (180 bars, min 60); V1 deepest 1.25/shallowest 0.75/mid 1.0; V2 top-2 1.25 else 1.0; frozen K2-family mults, no fit",
        "data": "4h closes only (spot pre-sample OK per assignment)",
        "harness": "replica PRIMARY (presample 9731 fills; 2021-2026 k2placebo 22312 fills); engine only if PRIMARY pass AND SECONDARY pass",
        "costs": {"maker": 0.0002, "taker": 0.00055, "fund_long_8h": 0.0001,
                  "note": "inside replica outcomes; limits strict trade-through, live 16..238, stop-first"},
        "gates": {"primary": "gain>0 in >=3/4 pre-sample AND Y2020p gain>0 AND pooled boosted stop delta<=+1pp",
                  "secondary": "dSum5y>=+0.273 AND gain>0 in >=4/5 years",
                  "engine": "only if PRIMARY pass AND SECONDARY pass"},
        "round_trip_bound": "4-8 bps bounds all replica effects (stated, not recomputed)",
    },
    "reproduction": {"presample": pre["reproduction"], "y2021_2026": sec["reproduction"]},
    "presample": {v: pre[v] for v in ("V1", "V2")},
    "stop_presample": stop,
    "secondary_2021_2026": {v: sec[v] for v in ("V1", "V2")},
    "engine": {"ran": False,
               "reason": "NO ENGINE: PRIMARY fails both variants (V1 1/4, V2 1/4, COVID Y2020p negative) AND SECONDARY fails both (V1 dSum +0.139<0.273 3/5; V2 dSum +0.196<0.273 4/5). Per PLAN, engine only for a variant with PRIMARY pass AND SECONDARY pass."},
    "credibility": {
        "fit_free_sign_stable": "PASS by construction (no fits, no return thresholds; rank is distribution-free; 180/60/1.25/0.75/top-2 frozen ex-ante)",
        "beats_exposure_control": "FAIL (norm already divides by realised mean; gains negative in 3/4 pre-sample years and dSum<0.273 on 2021-2026)",
        "bybit_leg": "NOT RUN (no engine; no S5 row)",
        "presample_leg": "FAIL (V1 1/4, V2 1/4; COVID Y2020p -0.103/-0.034)",
    },
    "verdict": "REJECT both variants as dip-sizing rules; no engine, no adoption, no prospective engine leg.",
}
(HERE / "results.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
print("wrote results.json", flush=True)

# ---- REPORT.md ----
def fmt(x, nd=6):
    return f"{x:+.{nd}f}" if isinstance(x, (int, float)) else str(x)

L = []
L.append("# oc_d_ddrank — REPORT (2026-10-08; PLAN frozen before any outcome)")
L.append("")
L.append("IDEAS12 #1 drawdown-rank rotation (buy the deepest coin harder): rank coins by")
L.append("trailing-30d DD-depth of own 4h closes (frozen 180 bars / min 60, closes with")
L.append("close_time <= T only); V1 deepest x1.25 / shallowest x0.75 / middle x1.0; V2 top-2")
L.append("deep x1.25 else x1.0 (frozen K2-family mults, no fit). 4h closes only (spot")
L.append("pre-sample OK). Replica PRIMARY + 2021-2026 SECONDARY; engine only if PRIMARY")
L.append("pass AND SECONDARY pass. B1/cap/stops kept in every leg by inheritance (replica")
L.append("has no budget/cap; engine not run).")
L.append("")
L.append("STATUS: DONE — no engine (valid negative). Pre-sample ledger reproduces exactly")
L.append("(n=9731, legs 909/2986/3115/2721, base 2.313362/2.678870/0.577643/0.297538);")
L.append("2021-2026 ledger reproduces exactly (n=22312, sum5y 7.718304). Rank-shuffle /")
L.append("timing / block placebos (1000/yr) + stop-kind recompute (15 unknown, as cboostpre)")
L.append("complete. Tests: 3 pass (`tests/test_oc_d_ddrank.py`).")
L.append("")
L.append("## PRIMARY: pre-sample replica 2017..2020-09-23 (SPOT fills/exits, perp gate costs)")
L.append("")
L.append("| year x variant | n | base | norm | gain | rank pct | timing pct | block pct | boosted% / deweighted% |")
L.append("|---|---|---|---|---|---|---|---|---|")
for v in ("V1", "V2"):
    for i, r in enumerate(pre[v]["per_year"]):
        rk = pre[v]["rank_placebo"][i]["percentile"]
        ti = pre[v]["timing_placebo"][i]["percentile"]
        bl = pre[v]["block_placebo"][i]["percentile"]
        L.append(f"| {r['year']} {v} | {r['n_fills']} | {r['base']:.6f} | {r['norm']:.6f} | "
                 f"{r['gain']:+.6f} | {rk:.2f} | {ti:.2f} | {bl:.2f} | "
                 f"{r['boosted_share']:.3f} / {r['deweighted_share']:.3f} |")
L.append("")
L.append("- Helps (gain>0): V1 1/4 (only Y2017 +0.023), V2 1/4 (only Y2017 +0.013).")
L.append("- COVID leg Y2020p (must survive): V1 -0.103, V2 -0.034 — BOTH NEGATIVE (fail).")
L.append("- Rank-shuffle (primary null): V1 93.7/13.4/42.5/11.9, V2 97.3/50.6/19.4/50.5")
L.append("  (only V2-Y2017 >= 95; Y2018 timing collapses to 0.1-0.3 for both).")
L.append("- Timing (diagnostic, cross-sectional idea): V1 73.9/0.1/1.4/0.8,")
L.append("  V2 76.9/0.1/9.4/10.4. Block: V1 24.2/0.1/8.3/0.8, V2 0.1/0.3/26.0/13.5.")
L.append("- PRIMARY pass = >=3/4 AND Y2020p>0 AND pooled stop<=+1pp: V1 FAIL, V2 FAIL.")
L.append("")
L.append("## Crash risk (stop-hit share; kinds recomputed verbatim mu=1.0; 15 unknown)")
L.append("")
L.append("| year | base stop% | V1 boosted% (delta) | V1 deweighted% (delta) | V2 boosted% (delta) | base TP% |")
L.append("|---|---|---|---|---|---|")
for r in stop["per_year"]:
    L.append(f"| {r['year']} | {r['base_stop_rate']:.2f} | {r['V1_boosted_stop_rate']:.2f} ({r['V1_boosted_stop_delta']:+.2f}) | "
             f"{r['V1_deweighted_stop_rate']:.2f} ({r['V1_deweighted_stop_delta']:+.2f}) | "
             f"{r['V2_boosted_stop_rate']:.2f} ({r['V2_boosted_stop_delta']:+.2f}) | {r['base_tp_rate']:.2f} |")
L.append("")
L.append(f"- Pooled: base 5.58%; V1 boosted {stop['V1_pooled']['boosted_stop_rate']:.2f}% "
         f"({stop['V1_pooled']['stop_delta']:+.2f}pp), V1 de-weighted "
         f"{stop['V1_pooled']['deweighted_stop_rate']:.2f}% ({stop['V1_pooled']['deweighted_delta']:+.2f}pp); "
         f"V2 boosted {stop['V2_pooled']['boosted_stop_rate']:.2f}% ({stop['V2_pooled']['stop_delta']:+.2f}pp).")
L.append("- Stop-rate check (fail if pooled boosted >+1pp): V1 PASS (-1.03pp), V2 PASS (-0.30pp) —")
L.append("  the rule does NOT lever stops; it just buys the wrong dips (Y2020p boosted stops")
L.append("  +0.86/+0.97pp on a 7.58% base, same crash-leg mechanism as every tilt).")
L.append("")
L.append("## SECONDARY: 2021-2026 replica gate (oc_k2placebo ledger; dSum5y>=+0.273, sum-half>=4/5)")
L.append("")
L.append("| year x variant | n | base | norm | gain | rank pct | timing pct | block pct |")
L.append("|---|---|---|---|---|---|---|---|")
for v in ("V1", "V2"):
    for i, r in enumerate(sec[v]["per_year"]):
        rk = sec[v]["rank_placebo"][i]["percentile"]
        ti = sec[v]["timing_placebo"][i]["percentile"]
        bl = sec[v]["block_placebo"][i]["percentile"]
        L.append(f"| {r['year']} {v} | {r['n_fills']} | {r['base']:.6f} | {r['norm']:.6f} | "
                 f"{r['gain']:+.6f} | {rk:.2f} | {ti:.2f} | {bl:.2f} |")
L.append("")
L.append(f"- V1: gains -0.005/-0.131/+0.156/+0.058/+0.062; dSum5y=+0.139 (<+0.273 FAIL), "
         f"sum-half=3/5 (FAIL). Rank 13.2/0.1/100/100/99.8; timing 46.6/0.3/100/98.5/98.7.")
L.append(f"- V2: gains +0.020/-0.033/+0.076/+0.089/+0.044; dSum5y=+0.196 (<+0.273 FAIL), "
         f"sum-half=4/5 (pass alone). Rank 11.0/0.3/99.8/100/99.7; timing 74.0/14.8/99.4/100/99.1.")
L.append("- SECONDARY pass = dSum5y>=+0.273 AND >=4/5: V1 FAIL, V2 FAIL (dSum).")
L.append("- 2022 kills both (V1 -0.131 rank 0.1, V2 -0.033 rank 0.3): deepest-coin sizing")
L.append("  levers the 2022 bear flushes (LUNA/FTX), exactly the epicenter risk pre-registered")
L.append("  in IDEAS12 (SOL-FTX, XRP-SEC). 2023-2025 gains are timing-significant but too small")
L.append("  to clear the +0.273 placebo-p95 bar (round-trip ~4-8 bps bounds all effects).")
L.append("")
L.append("## Engine vs G2: NOT RUN (per PLAN, valid negative)")
L.append("")
L.append("- Gate required PRIMARY pass AND SECONDARY pass for the same variant; no variant")
L.append("  passes either leg (PRIMARY 1/4 + COVID fail both; SECONDARY dSum fail both), so no")
L.append("  4-phase engine, no exposure-matched constant control, no Bybit S5 row, no G2")
L.append("  reproduction row in this study (G2 5.41/16.91/16.82 quoted from v421, not rerun).")
L.append("- Candidate-credibility checks: (1) fit-free/sign-stable PASS by construction (no fits,")
L.append("  distribution-free rank); (2) beats exposure control FAIL (norm gains negative/dust);")
L.append("  (3) Bybit leg NOT RUN; (4) pre-sample leg FAIL. 1/4 — adopt nothing.")
L.append("")
L.append("## Leakage checklist")
L.append("")
L.append("- Feature timing: DD-depth at T uses closes with close_time <= T only (window")
L.append("  C[j-180..j-1], current C[j-1]; tested bar never in its own window; ranking at (s,T)")
L.append("  uses only DD available at T; truncation-tested on real pre-sample bars.")
L.append("- Label windows: none fit anywhere (no harness join, no labels).")
L.append("- Fit windows: no fits; 180/60/1.25/0.75/top-2/seeds 20261007-09+BLOCK 42 all frozen")
L.append("  ex-ante, never scanned; no statistic from any test year feeds any choice; pre-sample")
L.append("  years never used for any fit (there is nothing to fit).")
L.append("- Fill timing: replica fills inherited (live 16..238 strict trade-through, stop-first);")
L.append("  perms reassign mults within year only (rank-shuffle within (y,s,T) bars; timing")
L.append("  uniform within year; block-42 within (y,sym,s)).")
L.append("- Gate costs inside reused replica outcomes (maker 0.0002/taker 0.00055, adverse long")
L.append("  funding 0.0001/8h). Coverage: all fills joined (0 missing mults via causal ffill);")
L.append("  15 unknown kinds (0.15%) excluded from rates only; early-bar NaN DD -> mult 1.0 (counted).")
L.append("- Spot-vs-perp caveat on every pre-sample number (SPOT fills/exits, perp gate costs).")
L.append("")
L.append("## What worked and what did not")
L.append("")
L.append("- Worked: stop-rate check passes (boosted stops do NOT rise pooled); Y2017 tiny gains")
L.append("  (+0.023/+0.013, V2 rank 97.3); 2023-2025 secondary gains positive with strong")
L.append("  rank/timing significance (V1 2023 rank 100/timing 100, V2 2024 rank 100/timing 100).")
L.append("- Did not: everywhere else — pre-sample 2018/2019/2020p all negative both variants;")
L.append("  2022 negative both; dSums (+0.139/+0.196) miss +0.273; COVID leg fails (must-survive")
L.append("  violated). Buying the deepest coin buys the epicenter (2022 bear, 2020 COVID crash).")
L.append("- Post-hoc log: none (one pre-report syntax typo in compute_ddrank_2021.py, fixed before")
L.append("  its first run, produced no outcome; two test-expectation typos fixed before passing;")
L.append("  no method/threshold/window touched after any outcome).")
L.append("")
L.append("## Vietnamese verdict")
L.append("")
L.append("Cả hai biến thể đều rớt cả hai cổng: pre-sample chỉ giúp 1/4 năm và chân COVID Y2020p âm")
L.append("(-0,10/-0,03, bắt buộc sống sót nhưng chết), 2021-2026 dSum +0,14/+0,20 dưới +0,273 dù 2023-2025")
L.append("dương; mua đồng sâu nhất là mua đúng tâm chấn (2022 bear, COVID crash).")
L.append("Stop gộp không tăng (V1 -1,03pp, V2 -0,30pp) nhưng edge không đủ bù round-trip 4-8 bps.")
L.append("Kết luận: REJECT cả V1 lẫn V2 — không engine, không adopt, không cần prospective engine.")
L.append("")
(HERE / "REPORT.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("wrote REPORT.md", flush=True)
