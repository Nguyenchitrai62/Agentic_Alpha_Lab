# OpenCode research task: regime-conditional rip-sell ladder (read AGENTS.md, OPENCODE_VF_COMMON.md, research/tournament/RULES.md)

Write ONLY under `research/tournament/oc_rips/` and `tests/test_oc_rips.py`; one heavy process, RAM < 2.5 GB; no commits; no edits of leader
files. Market data up to 2026-09-24 00:00 UTC may be used (all five years are research data; any finding needs prospective validation).

Background: the dip ladder (limit BUYS k sigma_4h below each 4h bar open, standard grid) is the BOT's dip sleeve; its mirror (limit SELLS k
sigma_4h ABOVE the open, 'rip fade') lost on average in earlier studies (spikes do not revert). It was never tested CONDITIONAL on a slow
regime. The dip sleeve is weak exactly in bear / range years (2021-22, 2022-23, 2025-26), so a regime-conditional short-side ladder could
complement it.
PLAN.md first (fixed before any outcome statistic). Event study, 5 majors, k in {2.5, 3.0, 4.0}, standard 4h grid, bids live minutes
16..238 of the bar, strict trade-through fill (high > level) at the level (maker 0.0002), take-profit 1 sigma_4h below the level (maker,
low < TP), stop on a 5-minute-block CLOSE 4 sigma above the level (exit next minute open, taker 0.00055) plus a touch backstop at 8 sigma,
else exit at the next bar open (taker); shorts pay no funding (gate rule: shorts receive nothing, pay nothing); same-minute stop-first.
sigma_4h = std of 4h open-to-open returns over 360 bars (min 120), known at the bar open. Implement with numpy on the 1m files
(data/raw/btc_intraday_20260924, data/raw/majors_intraday_20260924) - you may adapt research/diagnostics/rolling_anchor_dips/rolling_anchor_dips.py
(anchored rule) mirrored for shorts.
Regimes at the bar open (daily, data before the day start; reuse research/tournament/oc_regime/regime.py definitions and its regimes_daily
parquet if it covers the dates): trend90 (BTC 90-day return sign), BTC below its 200-day mean, 30-day realized vol vs 1-year median, breadth50.
Pre-register at most 3 conditional rules, e.g. R1 = rips only when BTC < 200-day mean, R2 = rips only when trend90 < 0 AND vol below median,
R3 = rips only when breadth50 < 0.4.
Score per anchor year (2021-09-24 .. 2025-09-24, +365 d): fills, mean net bps, win rate, sum of returns at equal notional, daily-sum max DD,
for the unconditional ladder and each rule; leave-one-year-out sign check. DECISION RULE (fixed): a rule is PROMISING only if its mean net
return is > +5 bps in >= 4 of 5 years AND the 5-year sum is positive AND its daily-sum DD is below 2x the unconditional dip ladder's
(compute the dip ladder with the same code for reference). Also report the correlation of its daily P&L with the dip ladder's.
Causality / correctness tests (assert-based): regime values use only data before the day start (truncation test, 20 days); the fill / exit
logic on 3 hand-made synthetic minute paths (TP, stop, timeout). Deliverables: PLAN.md, scripts, results.json, REPORT.md, tests.
