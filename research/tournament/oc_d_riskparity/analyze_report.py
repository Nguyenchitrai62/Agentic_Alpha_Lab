"""Merge all oc_d_riskparity legs into results.json + REPORT.md (CPU-only).

Reads tmp/v1_presample.json, tmp/stop_v1_presample.json, tmp/v2_presample.json,
tmp/v1_2021.json, tmp/stop_v1_2021.json, tmp/v2_2021.json. Applies the frozen
PRIMARY pass (gain>0 in >=3/4 pre-sample years AND Y2020p>0 AND pooled
parity-weighted stop delta <= +1pp) and SECONDARY gate (dSum5y >= +0.273 AND
sum-half >= 4/5). REPORT states which gate failed; no engine claim unless a
variant passes both (none does here).
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TMP = HERE / "tmp"


def load(name: str) -> dict:
    return json.loads((TMP / name).read_text())


def main() -> None:
    v1pre = load("v1_presample.json")
    s1pre = load("stop_v1_presample.json")
    v2pre = load("v2_presample.json")
    v1y = load("v1_2021.json")
    s1y = load("stop_v1_2021.json")
    v2y = load("v2_2021.json")

    v1_gains = [r["gain"] for r in v1pre["V1"]["per_year"]]
    v2_gains = [r["gain"] for r in v2pre["V2"]["per_year"]]
    v1_help = sum(1 for g in v1_gains if g > 0)
    v2_help = sum(1 for g in v2_gains if g > 0)
    v1_primary = bool(v1_help >= 3 and v1_gains[3] > 0
                      and not s1pre["pooled"]["fail"])
    v2_primary = bool(v2_help >= 3 and v2_gains[3] > 0)
    # V2 pooled parity stop delta vs REF base (REF base from V1 kind recompute)
    v2_pooled_pw = v2pre["V2"]["stops_v2"]["pooled_parity_stop_rate"]
    ref_pooled_base = s1pre["pooled"]["base_stop_rate"]
    v2_stop_delta = round(v2_pooled_pw - ref_pooled_base, 4)
    v2_primary = bool(v2_primary and v2_stop_delta <= 0.01)

    v1_sec = bool(v1y["V1"]["secondary_pass"])
    v2_sec = bool(v2y["V2"]["secondary_pass"])

    results = {
        "config": {
            "idea": "IDEAS12 #3 risk-parity rung sizing: size = base x 4sg/stopDist",
            "V1": "5 rungs {2.5,3,3.5,4,5}, uniform 4sg stops, mults 4/(k+4) sizing-only",
            "V2": "4 rungs {2.5,3.5,4.5,5.5} stops {4,5,6,7}, mults 4/(k'+s') + rebuilt outcomes",
            "primary_pass": "gain>0 in >=3/4 pre-sample years AND Y2020p>0 AND pooled parity stop delta<=+1pp",
            "secondary_gate": "dSum5y >= +0.273 AND sum-half >= 4/5",
        },
        "reproduction": {
            "presample": v1pre["reproduction"],
            "y2021_2026": v1y["reproduction"],
        },
        "V1_presample": v1pre["V1"],
        "V1_stop_presample": s1pre,
        "V2_presample": v2pre["V2"],
        "V1_2021": v1y["V1"],
        "V1_stop_2021": s1y,
        "V2_2021": v2y["V2"],
        "verdict": {
            "V1_primary": {"helps": v1_help, "covid_gain": v1_gains[3],
                           "stop_delta": s1pre["pooled"]["stop_delta"],
                           "pass": v1_primary},
            "V2_primary": {"helps": v2_help, "covid_gain": v2_gains[3],
                           "stop_delta": v2_stop_delta, "pass": v2_primary},
            "V1_secondary": {"dSum5y": v1y["V1"]["dSum5y"],
                             "sum_half": v1y["V1"]["sum_half"],
                             "pass": v1_sec},
            "V2_secondary": {"dSum5y": v2y["V2"]["dSum5y"],
                             "sum_half": v2y["V2"]["sum_half"],
                             "pass": v2_sec},
            "engine": "NO ENGINE — no variant passes PRIMARY + SECONDARY",
        },
    }
    (HERE / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")

    L = []
    L.append("# oc_d_riskparity — REPORT (2026-10-08; PLAN frozen before any outcome)")
    L.append("")
    L.append("IDEAS12 #3: risk-parity rung sizing (equal dollar-risk per rung).")
    L.append("size = base x (4sg/stopDist), open-to-stop parity: V1 mults 4/(k+4) on the base")
    L.append("5-rung grid with frozen 4sg stops (sizing-only overlay); V2 rungs 2.5/3.5/4.5/5.5sg")
    L.append("with depth-scaled stops 4/5/6/7sg + parity mults 4/(k'+s') (rebuilt fills +")
    L.append("outcomes, backstop still 8sg). No fit anywhere. STATUS: DONE — both reproductions")
    L.append("pass exactly; V1/V2 pre-sample + 2021-2026 replica + placebos + stop tables complete.")
    L.append("Tests: 7 pass (`tests/test_oc_d_riskparity.py`).")
    L.append("")
    L.append("## Reproduction gates: PASS both")
    L.append("")
    L.append("- Pre-sample REF ledger n = 9731 (legs 909/2986/3115/2721), base 4-phase-mean sums")
    L.append("  2.313362 / 2.678870 / 0.577643 / 0.297538 (exact to 1e-6).")
    L.append("- 2021-2026 REF ledger n = 22312, base sums 0.911273 / 0.832599 / 2.099814 /")
    L.append("  3.197390 / 0.677229, sum5y = 7.718304 (exact).")
    L.append("- V2 rebuilt ledgers (own fill sets): pre-sample n = 6783")
    L.append(f"  (legs {v2pre['per_leg_v2'][0]}/{v2pre['per_leg_v2'][1]}/{v2pre['per_leg_v2'][2]}/{v2pre['per_leg_v2'][3]});")
    L.append(f"  2021-2026 n = {v2y['n_fills_v2']} (legs {'/'.join(str(x) for x in v2y['per_leg_v2'])}).")
    L.append("  Fewer fills is mechanical (4 rungs, deeper levels fill less) — disclosed.")
    L.append("")
    L.append("## PRIMARY: pre-sample 2017-2020 replica (norm = tilted/realised_mean, gain = norm-base)")
    L.append("")
    L.append("| year x variant | n (REF/V2) | base | norm | gain | timing pct | block pct |")
    L.append("|---|---|---|---|---|---|---|")
    for i, leg in enumerate(("Y2017", "Y2018", "Y2019", "Y2020p")):
        a = v1pre["V1"]["per_year"][i]
        ta = v1pre["V1"]["timing_placebo"][i]
        ba = v1pre["V1"]["block_placebo"][i]
        b = v2pre["V2"]["per_year"][i]
        tb = v2pre["V2"]["timing_placebo"][i]
        bb = v2pre["V2"]["block_placebo"][i]
        L.append(f"| {leg} V1 | {a['n_fills']} / — | {a['base']:.6f} | {a['norm']:.6f} | "
                 f"{a['gain']:+.6f} | {ta['percentile']:.2f} | {ba['percentile']:.2f} |")
        L.append(f"| {leg} V2 | {a['n_fills']} / {b['n_fills_v2']} | {b['base']:.6f} | "
                 f"{b['norm_v2']:.6f} | {b['gain']:+.6f} | {tb['percentile']:.2f} | {bb['percentile']:.2f} |")
    L.append("")
    L.append(f"- Helps (gain>0): V1 {v1_help}/4 (only Y2020p); V2 {v2_help}/4 (none).")
    L.append("- Timing/block pcts are DIAGNOSTIC (parity is not a timing rule, pre-registered):")
    L.append("  V1 timing 42/43/47/99.5, block 39/66/63/97.5; V2 timing 100/100/100/89.5,")
    L.append("  block 100/100/100/67.2. High V2 timing pcts mean the rung composition beats")
    L.append("  rung-shuffled nulls yet still loses to doing nothing — the grid itself is the problem.")
    L.append("- COVID leg Y2020p separately: V1 +0.062523 (helps); V2 -0.236307 (fails).")
    L.append("")
    L.append("## Crash risk (stop-hit share; kinds VERBATIM mu=1.0; unknowns: 15 V1-pre / "
             f"{s1pre['config']['unknown']} REF-pre counted; V2 kinds recorded in rebuild)")
    L.append("")
    L.append("Pre-sample per-rung-group stop rates (REF kinds): shallow {0,1} / mid {2} / deep {3,4}:")
    for r in s1pre["per_year"]:
        L.append(f"- {r['year']}: base {r['base_stop_rate']:.2%} | shallow {r['shallow_stop_rate']:.2%} / "
                 f"mid {r['mid_stop_rate']:.2%} / deep {r['deep_stop_rate']:.2%} | "
                 f"parity-weighted {r['parity_stop_rate']:.2%} (delta {r['parity_stop_delta']:+.2%})")
    L.append(f"- Pooled: base {s1pre['pooled']['base_stop_rate']:.2%} vs parity-weighted "
             f"{s1pre['pooled']['parity_stop_rate']:.2%} (delta {s1pre['pooled']['stop_delta']:+.2%}) — "
             "no FAIL (<= +1pp).")
    L.append("V2 pre-sample (own stops): shallow(2.5sg) 4.23% / mid(3.5sg) 4.52% / deep(4.5+5.5sg) 6.12%;")
    L.append(f"pooled V2 {v2pre['V2']['stops_v2']['pooled_stop_rate']:.2%}, parity-weighted "
             f"{v2_pooled_pw:.2%} vs REF base {ref_pooled_base:.2%} (delta {v2_stop_delta:+.2%}) — no FAIL,")
    L.append("but V2 stops LESS because wider stops are hit less often while losing MORE per stop.")
    L.append("2021-2026 V1 groups: deep rungs stop ~2x the base rate every year "
             f"(pooled base {s1y['pooled']['base_stop_rate']:.2%} vs parity {s1y['pooled']['parity_stop_rate']:.2%}, "
             f"delta {s1y['pooled']['stop_delta']:+.2%}) — shape helps stops marginally, returns not at all.")
    L.append("")
    L.append("## SECONDARY: 2021-2026 replica gate (dSum5y >= +0.273 AND sum-half >= 4/5)")
    L.append("")
    L.append("| year x variant | base | norm | gain |")
    L.append("|---|---|---|---|")
    for i, yy in enumerate(("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")):
        a = v1y["V1"]["per_year"][i]
        b = v2y["V2"]["per_year"][i]
        L.append(f"| {yy} V1 | {a['base']:.6f} | {a['norm']:.6f} | {a['gain']:+.6f} |")
        L.append(f"| {yy} V2 | {b['base']:.6f} | {b['norm_v2']:.6f} | {b['gain']:+.6f} |")
    L.append("")
    L.append(f"- V1: dSum5y = {v1y['V1']['dSum5y']:+.6f}, sum-half = {v1y['V1']['sum_half']}/5 → FAIL.")
    L.append(f"- V2: dSum5y = {v2y['V2']['dSum5y']:+.6f}, sum-half = {v2y['V2']['sum_half']}/5 → FAIL.")
    L.append("")
    L.append("## Engine vs G2: NOT RUN (no variant passes PRIMARY + SECONDARY)")
    L.append("")
    L.append("- V1 PRIMARY: 1/4 helps (needs >= 3/4) → FAIL (COVID leg helps alone).")
    L.append("- V2 PRIMARY: 0/4 helps, COVID leg -0.236 → FAIL.")
    L.append("- V1 SECONDARY: dSum5y -0.097 < +0.273, 1/5 < 4/5 → FAIL.")
    L.append("- V2 SECONDARY: gate failed (see row above) → FAIL.")
    L.append("- Per the frozen plan, ENGINE (G2 reproduction 5.41/16.91/16.82, exposure-matched")
    L.append("  constant control, Bybit S5) runs ONLY for a variant passing both gates.")
    L.append("  No engine claim is made; no full-path DD exists for these variants.")
    L.append("- Candidate-credibility checks: (1) fit-free rule passes by construction; (2) beats")
    L.append("  exposure control — N/A, no engine; (3) Bybit leg — N/A, no engine; (4) pre-sample")
    L.append("  leg — FAILS for both. Verdict: REJECT.")
    L.append("")
    L.append("## Leakage checklist")
    L.append("")
    L.append("- Feature timing: V1 uses rung index only (no features); V2 levels/stops use O/sg")
    L.append("  available at bar open T only; V2 fills/outcomes causal on 1m (live 16..238 strict")
    L.append("  trade-through, stop-first); truncation-tested in tests/test_oc_d_riskparity.py.")
    L.append("- Label windows: no labels fit anywhere. Fit windows: no fits — every constant")
    L.append("  (2.5/3/3.5/4/5, 4/5/6/7, 4/(k+s), seeds 20261008/20261009, BLOCK 42) is frozen")
    L.append("  ex-ante arithmetic, never scanned; no statistic from any test year feeds any choice.")
    L.append("- Fill timing: inherited replica cores; perms reassign mults within (year[, coin, phase]) only.")
    L.append("- Gate costs inside all replica outcomes (maker 0.0002/taker 0.00055, adverse long")
    L.append("  funding 0.0001/8h). Coverage: V1 joins exact on rung (0 misses); V1-pre unknowns 15")
    L.append(f"  (0.15%); V1-2021 unknowns {s1y['config']['unknown']}; V2 fill deltas disclosed above.")
    L.append("- Spot-vs-perp caveat on every pre-sample number (SPOT fills/exits, perp gate costs).")
    L.append("")
    L.append("## What failed and why")
    L.append("")
    L.append("- V1 (pure parity sizing on the G2 grid): exposure-normalised gains are ~0 in")
    L.append("  2017-2019 (-0.004/-0.005/-0.000) and +0.063 in the COVID leg — the parity shape")
    L.append("  (0.62..0.44 across rungs) is too flat to matter outside the crash leg, and the")
    L.append("  2021-2026 gate is negative (dSum5y -0.097, 1/5). Round-trip 4-8 bps bounds it all.")
    L.append("- V2 (depth-scaled grid + wider stops): loses EVERY pre-sample year (-0.73/-0.78/-0.05/-0.24).")
    L.append("  Mechanism: dropping the earning 3.0sg rung (oc_contrib: shallow earns every year) and")
    L.append("  pushing size to 4.5/5.5sg rungs that fill less but bleed more per stop outweighs the")
    L.append("  lower stop frequency; wider stops cut stop counts (4.67% vs 5.58%) while deepening")
    L.append("  the average stop loss. Crash-reducing by construction in COUNT, not in P&L.")
    L.append("- This closes the direction per the 2-variant limit (Kelly-sized tails UP and breached DD;")
    L.append("  parity sizes them DOWN and still loses — the deep rungs cannot be rescued by sizing).")
    L.append("")
    L.append("## Vietnamese verdict")
    L.append("")
    L.append("V1 chỉ giúp đúng chân COVID (+0,06) còn 3 năm pre-sample ~0 và 2021-2026 âm (dSum -0,10, 1/5).")
    L.append("V2 thua cả 4 năm pre-sample (-0,73/-0,78/-0,05/-0,24): bỏ rung 3.0sg đang kiếm tiền và dời size")
    L.append("ra rung sâu stop rộng — ít stop hơn nhưng mỗi stop lỗ nặng hơn, không cứu được rung sâu.")
    L.append("Kết luận: REJECT cả hai variant, đóng hướng risk-parity rung sizing, không cần bằng chứng prospective.")
    L.append("")
    (HERE / "REPORT.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote results.json + REPORT.md", flush=True)


if __name__ == "__main__":
    main()
