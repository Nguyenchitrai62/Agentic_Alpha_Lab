# oc_ripcont REPORT: buy-the-first-pullback-after-a-rip (long sleeve)

Setup, variants, placebo, choice and the PROMISING gate are pre-registered in
PLAN.md (fixed before any outcome statistic). 5 majors x 4 clocks (each 1/4
capital), pooled per variant x anchor year. Costs: maker 0.0002 / taker
0.00055, longs pay 0.0001 per 8h settlement crossed. C3 dropped (no causal
per-bar book weight for all four clocks; see PLAN.md). G2 baseline reproduced
to the digit (R=5.41, W=2.588, DD=16.91, full-path 16.82) before any overlay.

## Verdict: NOT PROMISING (both variants fail gate i; C1 also fails ii)

Mean net per fill (bps) / n / win — dev years 21-22 .. 24-25 | dev sum | DD:
- C1 (k=2.0): -5.91/509/53% | -1.38/635/53% | -7.64/774/52% | +7.56/543/60%
  | sum -0.5692 | DD 0.031 (1/4 yrs >+5bps; sum < 0)
- C2 (k=3.0): -0.26/208/53% | -1.02/325/53% | +0.90/388/58% | +6.80/264/60%
  | sum +0.1762 | DD 0.011 (1/4 yrs >+5bps; sum > 0)
- Placebo (200 draws, seed 7, dev4 pooled mean): C1 actual -2.31 vs pbo mean
  -7.79 (p95 -5.11) -> pct 100.0; C2 actual +1.49 vs pbo mean -7.86 (p95
  -3.32) -> pct 100.0. Both pass (iii); DDs pass (iv) vs cap 2x1.2796=2.56.
- Exit shares dev4 (TP/SL/time): C1 1089/767/605; C2 587/386/212. Win rates
  53-60%: same pathology as rip-fades (TP wins smaller than SL/timeout
  losses), centred near zero instead of negative.
- Daily-PnL correlation vs G2 4-phase equity (dev4): C1 0.084, C2 0.081 —
  near-zero (fills at different times than book/dip, but no edge).
- Chosen on dev4 only (higher worst-year mean: C2 -1.02 > C1 -7.64): C2.
  Most-recent year scored ONCE for C2 only: n=248, mean +2.41 bps, win 57.7%,
  sum +0.0597 (TP/SL/time 123/78/47) — also below +5bps. No overlay was run
  (gate failed); book/dip engine untouched.

## Why it fails

Rips continue (oc_rips), but buying one sigma below the trigger with a
+0.75s TP / -1.0s SL does not capture the drift: three of four dev years are
~0 or negative for both k; only 2024 (strong-trend year) is positive. Beating
the random-minute placebo (which averages ~-8bps) only proves entries are
less bad than arbitrary longs, not that they earn. Scale: dev4 scaled sums
(+0.0044 total-equity for C2, -0.0142 for C1) are two orders below the dip
reference (+11.68 raw 5y sum on one grid).

## Causality / leakage checks

- Features at decision time only: sigma(b) uses bar opens <= T; trigger m>=5
  with H known at minute m; fill f>=m+1 on trade-through low<L; exits use
  minutes >f; timeout open at T+4h. No fill in offsets 0..4.
- No fits/thresholds on outcomes: k/TP/SL multiples fixed in PLAN.md; placebo
  seed fixed; no parameter was changed after seeing a mean.
- Data < 2026-09-24 only; most-recent year computed once for C2 (PASS2 loop
  covers only [2025-09-24-4h, 2026-09-24) bars for k=3.0).
- Tests: tests/test_oc_ripcont.py, 5 passed (sigma truncation/log hand-check,
  TP exact, same-minute stop-first, timeout+funding, first-5min/no-pullback).

## Post-hoc log

No rule/threshold change after outcomes. Three pre-outcome engineering fixes
(tz-aware bar_open conversion; date_range tz args; per-phase G2 reset — the
first version averaged phases before resetting and missed v421 rows) were
made after seeing fill COUNTS only, before any mean/placebo/decision
statistic existed. Original PLAN.md choice rule kept; no extra rows.

## Verdict (tiếng Việt)
- Kết luận: LOẠI — pullback sau rip không có edge (chỉ 1/4 năm dev trên +5bps).
- Không triển khai overlay, không sửa engine book/dip.
- Hướng tiếp theo (nếu có): đóng nhánh này, chỉ xem xét lại khi có bằng chứng prospective mới.
