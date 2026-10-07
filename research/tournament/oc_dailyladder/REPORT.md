# oc_dailyladder REPORT (2026-10-05; PLAN pre-registered before any outcome)

Idea #21: daily-timeframe dip ladder as a second, slower sleeve beside the
4h BOT dip ladder. Fixed rule, no grid, one run.

## Setup

Majors (BTC/ETH/SOL/BNB/XRP), daily rungs k in {1.5, 2.0, 2.5} below the
UTC day open O_D; sigma_d = std(ddof=1) of 90 daily open-to-open returns
ending D-1 (min 60). Resting bids valid day D, fill on strict
low < lv*(1-5bps) trade-through (maker 0.0002); TP +1.0sg limit (maker);
-2.0sg stop on hourly closes, exit next-hour open (taker 0.00055,
stop-first); time exit at D+3 00:00 open (taker); longs pay 1bp per 8h
settlement; fill hour never TPs; unit size per filled rung. Hourly data
only (`ext/hourly_ext.parquet`), one process, peak RAM ~0.4 GB. 2132
fills (entry D 2021-09-24 .. 2026-09-15; exits to 2026-09-18). 4h stream
= `ext/fills_U_ext.parquet` via `harness5.load` exactly as oc_idea7
(yearly test-row n = 990/1045/1330/989/1144, matching prior workers),
unweighted sum(y_dep) by exit date. Market data to 2026-09-24 00:00 UTC
read per assignment (all five years research data; needs prospective
validation; disclosed vs RULES.md hidden-year rule).

## Per-year results (entry-year cohorts; daily sums by exit date)

| year | n | win | mean net | sum | worst day | maxDD | corr w/ 4h | 4h n/sum |
|---|---|---|---|---|---|---|---|---|
| 21-22 | 477 | 65.2% | +55.4 bps | +2.641 | -0.770 | 1.201 | 0.02 | 990 / +3.935 |
| 22-23 | 318 | 69.5% | +47.3 bps | +1.503 | -1.205 | 1.316 | 0.33 | 1045 / +0.704 |
| 23-24 | 498 | 71.1% | +36.2 bps | +1.805 | -1.531 | 2.773 | 0.38 | 1330 / +6.018 |
| 24-25 | 421 | 70.5% | +31.3 bps | +1.317 | -1.003 | 1.972 | 0.39 | 989 / +4.257 |
| 25-26 | 418 | 63.9% | -26.1 bps | -1.090 | -1.102 | 2.282 | 0.26 | 1144 / +1.493 |
| FULL | 2132 | 68.0% | +28.9 bps | +6.176 | -1.531 | — | 0.263 | 5498 / +16.407 |

(a) sum > 0 in 4/5 years (only 25-26 negative; all 5 coins negative
that year, ETH worst at -0.49). (b) full-period exit-day correlation
0.263 < 0.5 PASS (yearly 0.02..0.39, never >= 0.5).

## Drawdown test per year (4h + 0.5*daily vs 4h alone scaled to same sum)

| year | S_4h | S_comb | maxDD_comb | maxDD_4h_scaled | pass? |
|---|---|---|---|---|---|
| 21-22 | 3.935 | 5.255 | 0.735 | 0.678 | NO |
| 22-23 | 0.704 | 1.456 | 2.210 | 4.480 | YES |
| 23-24 | 6.018 | 6.920 | 1.549 | 0.567 | NO |
| 24-25 | 4.257 | 4.916 | 1.321 | 0.598 | NO |
| 25-26 | 1.493 | 0.948 | 1.617 | 0.746 | NO |

(c) not-worse in only 1/5 years: the daily sleeve's own exit-day path
carries multi-day loss streaks (worst days -0.8..-1.5, path DD up to
2.8) that add to, rather than smooth, the 4h path at half weight.

## Descriptive (NOT part of the rule)

- Exit mix: TP 1353 (63%), stop 415 (19%), time 364 (17%).
- Per-coin sum (5y): XRP +3.48, SOL +1.71, BTC +1.15, BNB +0.97,
  ETH -1.13. Per-rung mean: k=1.5 +15 bps (n1174), k=2.0 +31 bps
  (n603), k=2.5 +72 bps (n355) — depth pays but was NOT selected;
  fixed rule stands as pre-registered.
- Funding paid: mean 2.8 bps/trade, max 9 settlements; well inside the
  +29 bps full-period mean net (vs ~4-8 bps round-trip cost).
- LOYO pooled sums (other 4 entry-years): +3.54/+4.67/+4.37/+4.86/+7.27,
  all > 0 — the 2021-24 sums are stable; only the 25-26 year itself is
  negative, so LOYO cannot rescue the DD clause.

## Caveats / post-hoc log

1. No post-hoc change: one fixed rule, one run, no tuning; per-k and
   per-coin cuts are descriptive only.
2. Hour granularity approximations (disclosed in PLAN): the 00:00 bar is
   included as proxy for the 00:05 start; TP exit stamped at its trigger
   hour start; funding counted on hour-start boundaries.
3. Late-window skip: entry days past 2026-09-20 have no D+3 bar in data
   and are skipped (3 days); last fill 2026-09-15.
4. Rung-level screen only: compounding/margin of a live sleeve are not
   modelled; a PROMISING verdict would still need prospective validation.

## Decision (pre-registered rule: sum>0 in >=4/5 AND corr<0.5 AND DD not-worse in >=3/5)

sum 4/5 PASS, corr 0.263 PASS, DD 1/5 FAIL.

## One-line verdict

NOT PROMISING: the daily ladder earns in 4/5 years and diversifies
(corr 0.26) but deepens the combined drawdown in 4/5 years and loses
money in 2025-26, so it fails as a second sleeve.
