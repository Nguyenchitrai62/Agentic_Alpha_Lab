# oc_weeklybook REPORT — weekly-decision book sleeve (IDEAS10 #6) alongside 4h G2

Rule (frozen PLAN.md, no post-hoc change): same G2 members (`research_books_d2`,
post-bear) held weekly — slow leg = post-bear book at the last Wednesday 00 UTC
anchor at/before each 4h bar (0 before the first Wednesday; strictly causal);
V1 = fast + 0.10*slow, V2 = fast + 0.25*slow (after bear, before shifted ffill);
same G2 grid policy for all rows; dip untouched. Controls C_V1/C_V2 = REF books x
per-year gross-exposure constant (in-year, diagnostic, never eligible).
Engine: 4-phase v421 R2B1D17BFG2 replica (pipe v321, corr-inv kd=1.7, bear books,
budget 0.26*1.7, G=2.0, win_start=5; gate costs maker 0.0002/taker 0.00055/longs
0.0001 per 8h; no fill minutes 0-4; stop-first). No label fit anywhere (weekly
"pooled label" = pure time-aggregation of frozen member weights; fit window
vacuous, embargo satisfied by construction).
Repro: `research/tournament/oc_weeklybook/{PLAN.md,weeklybook_rule.py,
compute_books.py,run_engine.py,analyze.py,analyze_last.py,results.json}` +
test `tests/test_oc_weeklybook.py`. Caches: `tmp/{std_books.pkl,controls.json,
proxy_diag.json,runs_dev.pkl,runs_last.pkl,runs_s5.pkl}` + logs.
G2 reproduction: REF reproduces v421_result R2B1D17BFG2 TO THE DIGIT on all five
years (dev [2.588/10.86, 3.282/16.91, 6.045/15.81, 10.677/8.27], Y4 4.648/12.90,
5y 5.410, full-path DD 16.82 — asserted in-script at every stage).

## Dev4 engine (Binance 1m, 4-phase reset %/mo / yearly DD %, selection scale)

| year | REF (= G2) | V1 f=0.10 | V2 f=0.25 | C_V1 (expl ctrl) | C_V2 (expl ctrl) |
|---|---|---|---|---|---|
| 2021-09-24 | 2.588 / 10.86 | 2.644 / 11.63 | 2.426 / 13.44 | 2.776 / 11.22 | 2.747 / 11.81 |
| 2022-09-24 | 3.282 / 16.91 | 3.281 / 17.28 | 3.264 / 17.36 | 3.437 / 17.18 | 3.651 / 17.06 |
| 2023-09-24 | 6.045 / 15.81 | 5.444 / 15.65 | 3.895 / 15.44 | 5.887 / 15.71 | 5.242 / 15.52 |
| 2024-09-24 | 10.677 / 8.27 | 10.448 / 7.90 | 9.425 / 9.49 | 10.312 / 8.12 | 9.983 / 9.08 |
| dev4 mean / WORST / maxDD / losing | 5.601 / 2.588 / 16.91 / 0 | 5.410 / 2.644 / 17.28 / 0 | 4.717 / 2.426 / 17.36 / 0 | 5.562 / 2.776 / 17.18 / 0 | 5.369 / 2.747 / 17.06 / 0 |
| book win (dev4) / fills | 0.5114 / 3968 | 0.5118 / 3940 | 0.5058 / 3756 | 0.5121 / 4057 | 0.5089 / 4128 |

Dev4 robust pick (frozen rule: DD<=20, no losing year; prefer mean>=5, then highest
WORST, ties->mean; REF+V1+V2 only): **V1** (hot pool {REF 5.601/W 2.588, V1
5.410/W 2.644}; V2 4.717 excluded from hot pool; V1 wins on WORST 2.644 > 2.588
despite trailing REF on mean by -0.19pp). Exposure constants realised:
c_V1 = 1.082/1.089/1.086/1.085, c_V2 = 1.215/1.226/1.218/1.218 (per anchor year).
Beats-exposure (frozen: R(V)>R(C) AND DD(V)<=DD(C)): V1 vs C_V1 FAILS
(5.410 < 5.562, 17.28 > 17.18); V2 vs C_V2 FAILS (4.717 < 5.369, 17.36 > 17.06).
Both sleeves trail their own exposure-matched constants — an exposure story, not timing.

## Sleeve-corr gate (frozen: max dev4 yearly slow-vs-fast proxy corr < 0.7)

Per-year Pearson corr of standard-grid proxy net returns (0.0005/unit turnover,
diagnostic scale): 2021: 0.7942, 2022: 0.8781, 2023: 0.8094, 2024: 0.8141 —
max 0.8781, gate FAILS in all 4 years. The slow leg is the same book held weekly,
so it is ~0.8-correlated with the fast book, not a diversifier (same failure mode
as oc_tsmom's +0.17..+0.47, but worse). Clock-luck diagnostic (7 weekday phases,
proxy only, never picked): slow standalone 5y proxy totals range 0.87 (Mon) .. 1.51
(Fri; Wed frozen = 1.10) and yearly corrs are >0.7 almost everywhere (only 2022 Mon
0.39 / Sat 0.48 / Sun 0.31 / Fri 0.59 dip below) — no phase rescues the gate, and
Wednesday is not cherry-picked (middle of the pack).

## Last year scored ONCE (Binance 1m, REF + dev4 pick V1 only, labelled)

| year | REF | V1 f=0.10 |
|---|---|---|
| 2025-09-24 (scored-once) | 4.648 / 12.90 | 4.719 / 12.50 |
| 5y mean / WORST / maxDD / losing | 5.410 / 2.588 / 16.91 / 0 | 5.272 / 2.644 / 17.28 / 0 |
| full-path DD (v388.mix, 2021-09-24..) | 16.82 | 17.28 |
| book win 5y / fills | 0.5169 / 5085 | 0.5170 / 5014 |

V1's scored-once year (+0.07pp over REF) does not repair the dev4 gates above; Y4
never picks per protocol.

## Bybit-price friction row S5 (oc_c2bybit harness, dev window, REF + V1 only, labelled)

Bybit 1m (`bybit_minutes`, live0=2021-11-15+shift, std filtered >=2021-11-15 before
shift; year 2021 = SHORT window from 2021-11-15, friction row only, never gated):

| year | REF on Bybit | V1 f=0.10 on Bybit |
|---|---|---|
| 2021-09-24 (short: from 2021-11-15) | 2.129 / 12.36 | 1.985 / 13.67 |
| 2022-09-24 | 2.735 / 18.11 | 2.491 / 18.59 |
| 2023-09-24 | 4.932 / 16.89 | 4.060 / 17.13 |
| 2024-09-24 | 10.377 / 9.22 | 10.152 / 7.89 |
| dev4 mean / WORST / maxDD | 4.994 / 2.129 / 18.11 | 4.622 / 1.985 / 18.59 |
| full-path DD (dev window) | 18.09 | 18.70 |

Venue gap (Binance→Bybit dev4): REF -0.61pp (5.601→4.994), V1 -0.79pp
(5.410→4.622); V1 trails REF on both venues by ~0.37pp with worse DD. No venue
rescue.

## Leakage checklist (how checked)

- Feature timing: w_fast uses closes <= T (cached member weights close-known;
  shifted clocks ffill latest standard row <= t_s); w_slow uses only the Wednesday
  anchor W* <= T (Wednesday-midnight rows; truncation-tested in
  tests/test_oc_weeklybook.py: post-Wednesday perturbations cannot move earlier slow
  rows; slow is 0 before the first anchor, no lookback beyond the grid).
- Label windows: no labels fit anywhere (slow = aggregation of frozen member
  weights; "weekly pooled label" implemented with zero estimated parameters).
- Fit windows: none (f 0.10/0.25 + Wednesday phase frozen ex-ante in PLAN.md before
  any outcome; R2 size/TP agents pre-date anchors; C_* in-year realised means labelled
  diagnostic/non-eligible and never picked; phase diagnostic proxy-only, never picked).
- Fill timing: engine trade-mode for every row (limit trade-through, no fill minutes
  0-4 after a 4h close, stop-first in the shared 1m bar); gate costs inside the engine
  (maker 0.0002, taker 0.00055, longs 0.0001/8h, shorts 0).
- No test-year statistic feeds any choice (dev pick uses 2021-2024 only; Y4 and S5
  scored once each for REF + the frozen V1 pick).

## Caveats / post-hoc log

1. No post-hoc change to PLAN.md definitions, variants, phases, fractions, gates, or
   the decision rule. PLAN.md was written before compute_books.py ran.
2. Book-only P&L is NOT separable from engine equity (engine stores t/eq/eq_min only,
   same as v421) — win rates/fills/fees/funding reported instead; proxy P&L is
   diagnostic scale only (0.0005/unit turnover, no SL/TP/funding/1m fills).
3. Slow-leg DD/standalone-Sharpe not gated (idea judges the overlay on return AND
   corr <0.7); standalone slow proxy totals reported in results.json/proxy_diag.
4. S5 year-2021 is a short window (Bybit 1m starts 2021-11-15); its yearly R/DD are
   not comparable to full Binance years — friction row only.
5. All five Binance years were available when scored (assignment override); any
   finding needs prospective validation; in-sample walk-forward style with no fitted
   parameter (phase/fractions frozen).

## Verdict

NOT PROMISING: the f=0.10 weekly sleeve trails G2 on dev4 mean (5.410 vs 5.601),
trails its own exposure-matched constant (5.410 vs 5.562 with worse DD 17.28 vs
17.18), and fails the diversifier gate (slow-vs-fast corr 0.79..0.88, max 0.8781 >
0.7) on both venues — a correlated exposure add-on, not a slow diversifier. Close
the direction in this form (same-members weekly-hold sleeve at f=0.10/0.25).

## Vietnamese verdict (3 lines)

- KHÔNG TRIỂN KHAI: sleeve weekly f=0.10 thua G2 trên dev4 (5.410 so với 5.601) và thua cả mức khống chế exposure-matched, DD tệ hơn (17.28 so với 17.18).
- Tương quan sleeve-G2 quá cao (0.79–0.88, ngưỡng <0.7 trượt cả 4 năm dev) nên không phải diversifier; hàng Bybit S5 cũng thua tương tự.
- Đóng hướng này ở dạng hiện tại (giữ book 4h + slow-hold cùng members với f=0.10/0.25).
