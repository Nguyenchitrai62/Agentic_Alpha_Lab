# oc_d_poststop — REPORT (IDEAS12 #2: Post-stop dip aggression)

Rule (frozen, no fits): after a dip stop on coin c (VERBATIM ledger exit branch at mu=1.0,
kind in {stop, backstop}, exit minute x -> tc = T + x min, strictly causal), size c's new
rungs x1.25 for N days on the same (coin, shift). V1 N=7, V2 N=3. Reproduction gates PASS
exactly on both ledgers (presample n=9731/base 2.313362/2.678870/0.577643/0.297538;
2021-2026 n=22312/sum5y=7.718304). Spot-vs-perp caveat on every pre-sample number.

## PRIMARY: pre-sample replica 2017..2020-09 (normalised gain vs no change)

| year | V1 gain | V1 timing% | V1 boost% | V2 gain | V2 timing% | V2 boost% |
|---|---|---|---|---|---|---|
| Y2017 | -0.0069 | 46.9 | 22.9 | -0.0136 | 90.7 | 16.6 |
| Y2018 | +0.0277 | 100.0 | 26.6 | +0.0570 | 100.0 | 15.5 |
| Y2019 | +0.1037 | 100.0 | 12.0 | +0.0679 | 100.0 | 8.6 |
| Y2020p COVID | -0.0298 | 23.7 | 24.1 | -0.0336 | 9.3 | 16.1 |

Timing is real in 2018/2019 (100.0% both variants, block confirms) but the COVID leg is
negative for BOTH variants -> explicit FAIL per IDEAS12 ("explicit FAIL if the 2020p COVID
leg is negative"). Helps only 2/4 (< 3/4 required). PRIMARY: FAIL both variants.

## Crash risk: boosted-fill stop rates (same VERBATIM kind recompute)

| year | base stop% | V1 boost stop-delta | V2 boost stop-delta |
|---|---|---|---|
| Y2017 | 3.30 | -1.86pp | -1.31pp |
| Y2018 | 3.29 | +0.48pp | +0.17pp |
| Y2019 | 6.69 | -5.35pp | -4.83pp |
| Y2020p COVID | 7.58 | +5.40pp | +8.14pp |
| pooled | 5.58 | V1 +0.48pp (PASS <=+1pp) | V2 +1.46pp (FAIL >+1pp) |

Post-stop windows buy straight into cascading stops in the COVID crash (+5.4/+8.1pp) —
the exact failure mode the PLAN pre-registered. Stops are rare (~3.4% of fills; 14-33
triggers per coin-shift over 3 pre-sample years), so CIs are wide, but the COVID sign is
negative, not just noisy.

## SECONDARY: 2021-2026 replica gate (dSum5y >= +0.273 AND >= 4/5)

| year | V1 gain | V2 gain |
|---|---|---|
| 2021 | -0.0151 | -0.0536 |
| 2022 | -0.0659 | -0.0524 |
| 2023 | +0.1490 | +0.0685 |
| 2024 | -0.0064 | -0.0148 |
| 2025 | +0.0062 | +0.0360 |
| dSum5y / half | +0.068 / 2-5 FAIL | -0.016 / 2-5 FAIL |

Only 2023 helps robustly (timing 100.0% both variants); 2022 loses on both. SECONDARY:
FAIL both variants. No engine, no exposure control, no Bybit S5 (gated out per PLAN —
a variant must help on the pre-sample AND pass the secondary gate; neither did).

## Leakage / checks

Feature timing: stop tc = exit minute from 1m data, boosted decisions strictly after tc
(truncation-tested). No labels fit anywhere; no fits at all (1.25/N/seeds/BLOCK frozen).
Fill timing: live 16..238 strict trade-through + stop-first inherited; perms within
(year, shift, coin) only. Gate costs inside reused replica outcomes. Coverage: presample
unknown-kind fills 15/9731 (same 15 as oc_cboostpre); 2021-2026 unknown 0/22312; joins
100% exact both legs. No statistic from any test year fed any choice.

## Verdict (3 dong tieng Viet)
1. REJECT ca hai bien the V1/V2: COVID pre-sample am va chi giup 2/4 nam, secondary cung truot.
2. Bai hoc: stop la dau hieu capitulation that, nhung cua so sau stop mua trung cascade tiep dien.
3. Dong huong nay: can bang chung prospective moi, khong dua vao engine hay adoption.
