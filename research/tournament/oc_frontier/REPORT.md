# oc_frontier REPORT: v399..v423 5-year 4-phase reset-metric rows + Pareto frontiers

Sources: `research/parallel/rounds/parallel-20260906-r2/vNNN/vNNN_result.json`
(rows R/W/DD/years), `vNNN/run.log` (`<row> full-path DD x`), `vNNN/result_manifest.json`
(`audit.passed`). All five walk-forward years are research data (anchors 2021-09-24 ..
2025-09-24, +365 d); findings need prospective validation. No 1m data loaded; one
process; RAM << 1 GB. Scatter plot: `frontier.png` (R vs max yearly DD). Machine table:
`results.json`. REPORTING task (no selection): no PROMISING flag is assigned.

Definitions: R = 5y geometric %/month; W = worst single-year %/month;
DD_yearly = max yearly DD (= rows[row].DD); full_path_dd = run.log value (null when
absent in both log and JSON: all 7 rows of v399/v400); recent_R = years[4][0]
(anchor 2025-09-24 year); audited = manifest audit.passed. Pareto: maximise R,
minimise DD (ties on identical points kept).

## Full table (80 rows)

| version | row | R | W | max yearly DD | full-path DD | recent R | audited |
|---|---|---|---|---|---|---|---|
| v399 | R2 | 4.820 | 1.956 | 25.05 | null | 3.949 | yes |
| v399 | R2B1 | 4.550 | 1.286 | 13.88 | null | 4.405 | yes |
| v399 | R2B2 | 4.615 | 1.678 | 17.71 | null | 4.319 | yes |
| v400 | R2 | 4.820 | 1.956 | 25.05 | null | 3.949 | yes |
| v400 | R2B1_130 | 5.171 | 1.404 | 17.06 | null | 5.426 | yes |
| v400 | R2B1_150 | 5.460 | 1.335 | 18.92 | null | 5.114 | yes |
| v400 | R2B2_130 | 5.518 | 1.774 | 23.13 | null | 5.012 | yes |
| v401 | R2B1R_110 | 4.764 | 1.546 | 18.38 | 20.23 | 4.301 | yes |
| v401 | R2B1R_130 | 5.198 | 1.980 | 23.51 | 25.93 | 4.689 | yes |
| v401 | R2B1_130 | 5.171 | 1.404 | 17.06 | 20.50 | 5.426 | yes |
| v402 | R2B1_125 | 5.111 | 1.366 | 17.52 | 20.58 | 5.085 | yes |
| v402 | R2B1_130 | 5.171 | 1.404 | 17.06 | 20.50 | 5.426 | yes |
| v402 | R2B1e_130 | 4.961 | 1.184 | 17.03 | 21.33 | 5.116 | yes |
| v402 | R2B1e_150 | 5.134 | 1.049 | 18.26 | 23.12 | 4.934 | yes |
| v403 | R2B1S_130 | 4.852 | 1.058 | 18.37 | 21.28 | 5.211 | yes |
| v403 | R2B1T_130 | 5.015 | 1.228 | 17.53 | 21.48 | 5.392 | yes |
| v403 | R2B1_130 | 5.171 | 1.404 | 17.06 | 20.50 | 5.426 | yes |
| v404 | R2B1G16_130 | 4.472 | 1.161 | 16.70 | 19.23 | 4.293 | yes |
| v404 | R2B1G18_130 | 4.781 | 1.406 | 16.47 | 18.69 | 4.709 | yes |
| v404 | R2B1_130 | 5.171 | 1.404 | 17.06 | 20.50 | 5.426 | yes |
| v405 | R2B1G18_140 | 4.945 | 1.463 | 17.36 | 20.96 | 4.390 | yes |
| v405 | R2B1G18_150 | 4.842 | 1.244 | 20.30 | 22.13 | 3.838 | yes |
| v405 | R2B1_130 | 5.171 | 1.404 | 17.06 | 20.50 | 5.426 | yes |
| v406 | R2B1D16 | 5.137 | 2.012 | 17.33 | 16.37 | 4.853 | yes |
| v406 | R2B1D18B08 | 5.042 | 2.491 | 18.70 | 17.22 | 4.263 | yes |
| v406 | R2B1_130 | 5.171 | 1.404 | 17.06 | 20.50 | 5.426 | yes |
| v407 | R2B1D16 | 5.137 | 2.012 | 17.33 | 16.37 | 4.853 | yes |
| v407 | R2B1D20 | 5.779 | 2.515 | 20.95 | 18.89 | 5.203 | yes |
| v407 | R2B1D20B11 | 5.894 | 2.401 | 21.21 | 19.10 | 5.528 | yes |
| v408 | R2B1D16 | 5.137 | 2.012 | 17.33 | 16.37 | 4.853 | yes |
| v408 | R2B1D18 | 5.452 | 2.370 | 19.14 | 17.57 | 5.018 | yes |
| v409 | R2B1D13 | 4.957 | 1.728 | 15.00 | 16.36 | 4.704 | yes |
| v409 | R2B1D15B08 | 4.626 | 2.161 | 15.99 | 14.94 | 4.054 | yes |
| v409 | R2B1D16 | 5.137 | 2.012 | 17.33 | 16.37 | 4.853 | yes |
| v409 | R2B1D16B06 | 4.325 | 2.196 | 16.38 | 15.21 | 3.369 | yes |
| v410 | R2B1D16 | 5.137 | 2.012 | 17.33 | 16.37 | 4.853 | yes |
| v410 | R2B1D16BF | 5.236 | 2.731 | 17.40 | 16.20 | 4.969 | yes |
| v410 | R2B1D18BF | 5.564 | 3.008 | 19.22 | 17.57 | 5.148 | yes |
| v411 | R2B1D16 | 5.137 | 2.012 | 17.33 | 16.37 | 4.853 | yes |
| v411 | R2B1D17BF | 5.425 | 2.831 | 18.33 | 16.90 | 5.060 | yes |
| v412 | R2B1D18BF | 5.564 | 3.008 | 19.22 | 17.57 | 5.148 | yes |
| v412 | R2B1D18BFS | 5.706 | 2.957 | 19.22 | 17.67 | 4.850 | yes |
| v413 | R2B1D12BFH | 4.277 | 1.349 | 30.19 | 31.57 | 3.786 | yes |
| v413 | R2B1D18BF | 5.564 | 3.008 | 19.22 | 17.57 | 5.148 | yes |
| v413 | R2B1D18BFH | 5.040 | 1.384 | 32.27 | 37.57 | 2.474 | yes |
| v414 | R2B1D17BF | 5.425 | 2.831 | 18.33 | 16.90 | 5.060 | yes |
| v414 | R2B1D17BFV1 | 5.731 | 2.409 | 22.93 | 21.38 | 5.050 | yes |
| v414 | R2B1D17BFV2 | 5.711 | 2.301 | 24.08 | 22.35 | 4.930 | yes |
| v415 | R2B1D17BF | 5.425 | 2.831 | 18.33 | 16.90 | 5.060 | yes |
| v415 | R2B1D17BFS5 | 5.416 | 2.678 | 18.37 | 16.62 | 5.143 | yes |
| v415 | R2B1D17BFS6 | 5.565 | 2.760 | 18.37 | 16.71 | 5.167 | yes |
| v416 | R2B1D17BF | 5.425 | 2.831 | 18.33 | 16.90 | 5.060 | yes |
| v416 | R2B1D17BFD | 5.194 | 2.831 | 20.45 | 18.37 | 4.811 | yes |
| v417 | R2B1D17BF | 5.425 | 2.831 | 18.33 | 16.90 | 5.060 | yes |
| v417 | R2B1D17BFC | 5.416 | 3.438 | 18.45 | 17.42 | 4.782 | yes |
| v417 | R2B1D17BFCX | 5.504 | 3.439 | 18.55 | 17.47 | 4.811 | yes |
| v417 | R2B1D17BFX | 5.574 | 2.831 | 18.37 | 16.89 | 5.104 | yes |
| v418 | R2B1D17BF | 5.425 | 2.831 | 18.33 | 16.90 | 5.060 | yes |
| v418 | R2B1D17BFDS | 5.547 | 2.752 | 18.35 | 16.84 | 4.498 | yes |
| v419 | R2B1D17BF | 5.425 | 2.831 | 18.33 | 16.90 | 5.060 | yes |
| v419 | R2B1D17BFBRK05 | 5.360 | 2.816 | 18.32 | 16.88 | 5.058 | yes |
| v419 | R2B1D17BFBRK08 | 5.401 | 2.831 | 18.33 | 16.87 | 5.058 | yes |
| v419 | R2B1D17BFBUD13 | 5.392 | 2.757 | 18.33 | 16.88 | 5.023 | yes |
| v420 | R2B1D17BF | 5.425 | 2.831 | 18.33 | 16.90 | 5.060 | yes |
| v420 | R2B1F15K20 | 4.993 | 2.129 | 16.17 | 15.87 | 4.326 | yes |
| v420 | R2B1F15K23 | 5.281 | 2.227 | 16.97 | 16.69 | 4.474 | yes |
| v420 | R2B1F20K17 | 5.042 | 2.521 | 16.00 | 15.47 | 4.651 | yes |
| v420 | R2B1F20K20 | 5.300 | 2.704 | 18.41 | 17.69 | 4.833 | yes |
| v421 | R2B1D17BF | 5.425 | 2.831 | 18.33 | 16.90 | 5.060 | NO |
| v421 | R2B1D17BFG2 | 5.410 | 2.588 | 16.91 | 16.82 | 4.648 | NO |
| v421 | R2B1D17BFG3 | 5.291 | 2.680 | 18.33 | 16.91 | 4.833 | NO |
| v422 | G15K20 | 5.731 | 2.472 | 16.96 | 16.76 | 4.340 | yes |
| v422 | G2F20K20 | 5.346 | 2.648 | 16.20 | 16.02 | 4.613 | yes |
| v422 | G2K20 | 5.874 | 2.832 | 17.79 | 17.69 | 4.716 | yes |
| v422 | R2B1D17BF | 5.425 | 2.831 | 18.33 | 16.90 | 5.060 | yes |
| v422 | R2B1D17BFG2 | 5.410 | 2.588 | 16.91 | 16.82 | 4.648 | yes |
| v423 | R2B1D17BF | 5.425 | 2.831 | 18.33 | 16.90 | 5.060 | yes |
| v423 | R2B1D17BFX45 | 5.118 | 2.402 | 15.92 | 15.81 | 4.643 | yes |
| v423 | R2B1D17BFX45G2 | 5.015 | 2.350 | 16.11 | 16.03 | 4.493 | yes |
| v423 | R2B1D17BFX5 | 5.311 | 2.822 | 16.87 | 16.25 | 4.934 | yes |

## Pareto frontiers

Yearly-DD frontier (R up, max yearly DD down), 9 rows: v399/R2B1 (4.550, 13.88),
v409/R2B1D13 (4.957, 15.00), v423/R2B1D17BFX45 (5.118, 15.92), v422/G2F20K20
(5.346, 16.20), v421/R2B1D17BFG2 = v422/R2B1D17BFG2 tie (5.410, 16.91),
v422/G15K20 (5.731, 16.96), v422/G2K20 (5.874, 17.79), v407/R2B1D20B11
(5.894, 21.21).

Full-path-DD frontier (R up, full-path DD down), 9 rows: v409/R2B1D15B08 (4.626,
14.94), v420/R2B1F20K17 (5.042, 15.47), v423/R2B1D17BFX45 (5.118, 15.81),
v422/G2F20K20 (5.346, 16.02), v415/R2B1D17BFS5 (5.416, 16.62),
v415/R2B1D17BFS6 (5.565, 16.71), v422/G15K20 (5.731, 16.76), v422/G2K20
(5.874, 17.69), v407/R2B1D20B11 (5.894, 19.10). (v399/v400 rows excluded: no
full-path DD logged.)

Deployment pick v411/R2B1D17BF (5.425, yearly 18.33, full-path 16.90, audited yes)
is on NEITHER frontier (dominated yearly by v422/G2K20; dominated full-path by
v415/R2B1D17BFS6).

Stretch DD < 15: yearly only v399/R2B1 (13.88, no full-path logged); full-path only
v409/R2B1D15B08 (14.94; yearly 15.99). So no row meets DD < 15 on BOTH metrics.

## Caveats / post-hoc log
1. No post-hoc change to definitions: run.log values matched result-JSON
   full_path_dd for all 73 rows where both exist (0 mismatches). v399/v400 (7 rows)
   have null full-path DD in both sources (predate full-path logging).
2. Audit state: 77/80 rows audited yes; only the 3 v421 rows are audit.passed
   false ("awaiting OpenCode blind audit") — includes the yearly-frontier member
   v421/R2B1D17BFG2 (its tie twin v422/R2B1D17BFG2 is audited). v423 passed its
   blind audit (v423_audit/COMPARISON.md: PASS) during this task; results.json was
   rebuilt to reflect it (no metric values changed).
3. The identical yearly point v421/v422 R2B1D17BFG2 (5.410, 16.91) is a tie kept on
   the yearly frontier per the pre-registered rule.

## Verdict
REPORTING ONLY: highest R is v407/R2B1D20B11 (5.894, DD 21.21/19.10); lowest-DD rows
are v399/R2B1 (yearly 13.88) and v409/R2B1D15B08 (full-path 14.94); the deploy pick
v411/R2B1D17BF sits inside both frontiers, not on them.
