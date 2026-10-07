# OpenCode task oc_paperpower - how much paper evidence do the go-live gates need? (power / false-pass analysis)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_paperpower/` and `tests/test_oc_paperpower.py`.

## Question
Go-live gates (scripts/prospective_scorecard.py GO_LIVE; docs/DEPLOYMENT_PLAN_VI.md): after >= 8 weeks of paper, live return percentile >= 20
of the research bootstrap for the same horizon, paper DD <= 15 %, paper-vs-plan divergence <= 1.5 pp/month, no cycle_error > 1 h. How
informative is that after 8 / 12 / 26 weeks?

## Method (fixed)
- Research return process: G2 + carry hourly equity (4-phase), built exactly as research/tournament/oc_carrycompound/analyze_carrycompound.py
  (f = 0.25) -> daily returns over the five years 2021-09-24 .. 2026-09-23 (all research data; this is descriptive, no selection).
- Scenarios for the "true" live process (stationary block bootstrap, 10-day blocks, 5000 paths each, seed 0):
  S_good = research daily returns as they are; S_half = research returns minus a constant so the mean is halved; S_zero = research returns
  minus their mean (same volatility and tails, zero edge); S_neg = mean -1 %/month.
- For horizons 8, 12, 26, 52 weeks: probability that the percentile gate (>= 20 of the S_good bootstrap at the same horizon) AND the DD gate
  (max DD <= 15 %) pass, under each scenario; also the probability that the STOP rule (DD > 20 %, or percentile < 5 after >= 8 weeks) fires.
- Report a table and the false-pass rate (S_zero / S_neg passing) and the true-pass rate (S_good). Recommend (descriptively) the horizon at
  which S_zero passes <= 20 % of the time, and say plainly how weak 8 weeks is if it is.
- Caveat: the bootstrap ignores regime persistence beyond 10 days; also run 30-day blocks as a sensitivity row.
Vietnamese 3-line summary for the owner.
