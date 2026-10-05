# OpenCode research task: two untried public information sources (read AGENTS.md, OPENCODE_VF_COMMON.md, research/tournament/RULES.md)

Write ONLY under `research/tournament/oc_newinfo/` (raw downloads into `data/raw/newinfo_20261005/` with a manifest.json of URLs + sha256)
and `tests/test_oc_newinfo.py`. One heavy process, RAM < 2.5 GB. No commits, no edits of leader files. Market data up to 2026-09-24 00:00 UTC
may be used (all five years are research data; the clean test of anything found here is prospective). Write PLAN.md BEFORE computing any
outcome statistic (sources, exact feature definitions, availability lags, labels, tests, decision rule below).

N1 Wikipedia attention: daily pageviews (Wikimedia REST per-article API, all-agents or user, desktop+mobile; send a User-Agent header) for the
articles Bitcoin, Ethereum, Solana_(blockchain_platform) (check the exact title), BNB / Binance_Coin (check), XRP / Ripple_Labs (check), 2016..
2026-09-23. Features (day D usable from D+1 00:00 UTC only): log views z-score vs its trailing 90-day mean/std, 7-day change, and the
cross-coin attention share. N2 CME gap: daily CME Bitcoin futures (front month continuous, e.g. Yahoo Finance BTC=F via the public chart API or
another free source; document it) Friday settlement vs Binance BTCUSDT price at the CME Sunday reopen (Sunday 23:00 UTC; mind DST), gap in
sigma_daily units; also the Monday-to-Friday 'gap fill' frequency.
Labels from Binance 4h opens of the 5 majors (research/tournament/ext/hourly_ext.parquet or data/raw 1m files): forward 1-day and 7-day
open-to-open returns normalised by trailing sigma; for N1 also the dip-sleeve monthly edge from research/tournament/oc_regime/monthly_main.csv.
Tests (5 anchor years 2021-09-24 .. 2025-09-24, +365 d each): Spearman IC per year per feature (pooled over coins for N1, BTC and ETH for N2),
and a leave-one-year-out sign test: the sign estimated on the other four years must hold on the held-out year. DECISION RULE (fixed): a
feature is PROMISING only if its IC has the same sign in >= 4 of 5 years AND |mean IC| >= 0.03 AND the leave-one-year-out sign holds in
>= 4 of 5 held-out years. Causality: assert-based truncation tests (features at D use nothing after D 00:00 UTC; 20 random days).
Deliverables: PLAN.md, fetch + feature + analysis scripts, results.json, REPORT.md (IC tables, LOYO, verdict per feature), tests.
