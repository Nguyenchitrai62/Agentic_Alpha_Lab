# oc_idea2wf REPORT: walk-forward per-coin dip close-stop (4.0 vs 5.5sg)

## Setup

Rung-level replica of oc_idea2/oc_dipexit D0 (LONG dip rungs, majors,
rungs 2.5/3/3.5/4/5sg below the 4h bar open; fills offsets 16..238 on strict
low<level trade-through; 5m-block CLOSE stop on absolute clock, 8sg backstop,
TP 1.0sg limit, timeout at next-bar open; maker 0.0002/taker 0.00055; longs pay
0.0001 on settling timeouts). Bars with open in [2020-08-01, 2026-09-24)
computed; scored anchor years [A_k, A_k+365d) with
A = 2021-09-24, 2022-09-24, 2023-09-24, 2024-09-23, 2025-09-23
(literal 2021-09-24+k*365d; A3/A4 1 day early vs calendar, leap day disclosed;
2026-09-23..24 unscored 1-day gap). 1m read to 2026-09-24 00:00 (timeout opens
only); one coin at a time, one process. U = uniform close-stop 4.0sg.
Per-coin wide leg Vc = 5.5sg computed for EVERY major. Walk-forward choice
m_c(A_k) = 5.5 iff sum(Vc-U) over coin-c paired rungs with
max(t_exit_U, t_exit_Vc) < A_k-7d is strictly > 0, else 4.0 (no other
distances). Paired rungs kept only if U and Vc both finite -> 6876 rungs
(5489 scored; BTC 1368, ETH 1417, SOL 1101, BNB 1481, XRP 1509 total).
Years 0-2 U sums reproduce oc_idea2 EXACTLY (same windows). Year = bar-open
anchor year; daily sums by EXIT date UTC of the respective leg (WF path uses WF
exits, U path uses U exits). Win = net > 0 strictly. All 5 years are research
data per assignment (disclosed vs RULES.md hidden-year rule); a PROMISING
screen still needs prospective validation.

## Choice table (choice.json: {anchor_iso: {SYMBOL: m}})

| anchor | BTC | ETH | SOL | BNB | XRP |
|---|---|---|---|---|---|
| 2021-09-24 | 5.5 | 5.5 | 5.5 | 4.0 | 5.5 |
| 2022-09-24 | 5.5 | 5.5 | 5.5 | 4.0 | 5.5 |
| 2023-09-24 | 5.5 | 5.5 | 5.5 | 5.5 | 5.5 |
| 2024-09-23 | 5.5 | 5.5 | 5.5 | 4.0 | 5.5 |
| 2025-09-23 | 5.5 | 5.5 | 5.5 | 4.0 | 5.5 |

Training sum(V-U) (n_train): 2021: BTC +0.290(290), ETH +0.455(281),
SOL +0.200(148), BNB -0.165(295), XRP +0.509(331); 2022: +0.198(502),
+0.597(512), +0.320(316), -0.032(483), +0.514(522); 2023: +0.218(709),
+0.606(710), +0.819(520), +0.036(715), +0.681(747); 2024: +0.281(980),
+0.585(982), +0.819(719), -0.138(995), +0.887(1067); 2025: +0.281(1141),
+0.402(1178), +0.819(891), -0.154(1212), +1.086(1282).

## Per-year WF vs U (n scored; mean/win/sum; worst-day / max-DD of exit-day sums)

| year | U uniform-4sg | WF walk-forward | D = WF-U sum |
|---|---|---|---|
| 2021-09-24 | .00381/.688/3.7766/-0.430/-0.454 (n990) | .00399/.692/3.9522/-0.578/-0.578 | +0.1756 |
| 2022-09-24 | .00038/.695/0.3933/-1.924/-2.282 (n1045) | .00104/.700/1.0888/-1.457/-1.825 | +0.6955 |
| 2023-09-24 | .00397/.773/5.2761/-0.495/-0.495 (n1330) | .00402/.776/5.3508/-0.511/-0.511 | +0.0747 |
| 2024-09-23 | .00410/.698/4.0484/-0.507/-0.507 (n987) | .00412/.698/4.0646/-0.539/-0.539 | +0.0161 |
| 2025-09-23 | .00132/.655/1.5006/-1.018/-1.269 (n1137) | .00143/.656/1.6279/-1.074/-1.325 | +0.1274 |
| FULL | .00273/.705/14.9950/-1.924/-2.282 (n5489) | .00293/.708/16.0843/-1.457/-1.825 | +1.0892 |

LOO mean D excl. year: +0.2284/+0.0984/+0.2536/+0.2683/+0.2405 (5/5 > 0).
Worst-day-not-worse (WF >= U): 1/5 years (only 2022 better; 2021/2023/2024/2025
worse by 0.02-0.15). Full-path worst day (-1.457 vs -1.924) and maxDD (-1.825
vs -2.282) improve under WF (driven by 2022), but the per-year bar fails 4/5.

## Decision (PROMISING = D>0 in >=4/5y AND LOO D>0 in >=4/5 AND worst-day-not-worse in >=4/5)

D>0 in 5/5 years; LOO>0 in 5/5; worst-day-not-worse in 1/5. Third bar fails.

## Verdict

NOT PROMISING: walk-forward per-coin stop beats uniform 4sg in 5/5 years with LOO>0 in 5/5 but worst-day-not-worse in only 1/5 (sums transfer, tails do not).

## Caveats / repro

- No post-hoc change: anchors (literal +k*365d), the (4.0, 5.5) pair, the
  max(exit)<A-7d training rule with strict >0, the replica/priority/fees, and
  the 3-part rule were all pre-registered in PLAN.md before any outcome.
- The WF rule picks WIDE almost everywhere (all coins except BNB, which stays
  4.0 in 4/5 years on negative training sums); it is effectively "wider stops
  everywhere except BNB". Return edge is real each year (+0.02 to +0.70) but 4
  of 5 yearly worst days worsen: wider stops convert stop-outs into larger
  down-day tails outside 2022.
- Repro: `research/tournament/oc_idea2wf/{PLAN.md,analyze_idea2wf.py,
  results.json,choice.json,REPORT.md}` (majors 1m only, one coin at a time,
  RAM < 1 GB) + `tests/test_oc_idea2wf.py`.
