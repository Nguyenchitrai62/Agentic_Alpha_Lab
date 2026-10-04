# New-data scouting rounds (2026-10-04): common rules for every worker (read with AGENTS.md and OPENCODE_VF_COMMON.md)
Goal: find NEW, free, historical information that predicts the outcome of the deployed strategies' dip-limit trades (their main return source) or
4h returns of the five majors (BTC ETH SOL BNB XRP), without any data leakage. You fetch, build causal features, and run a dev-only study.
Dip-trade outcomes to study: research/diagnostics/phase_agents/fills_U.parquet (61,779 simulated dip-limit fills of 35 coins on the standard 4h
grid, 2020-08..2025-09; columns: sym, t_fill (fill minute, UTC), t_exit, r = rung index, x0..x6 = existing state features, y0.5 / y1.0 / y1.5 =
the trade's net return with take-profit 0.5 / 1.0 / 1.5 sigma). PRIMARY TARGET: y1.0. Use ONLY rows with t_exit < 2025-09-14 (dev); never
look at anything later. Features must be joined AS OF strictly before the fill minute (availability time + a safety lag you state, e.g. an hourly
snapshot stamped h is used only from h + 1h unless you prove it is published at h) - assert it.
Report per feature: Spearman IC with y1.0 per calendar year (2021-2025) for the majors and for all coins, and the IC after controlling for x0..x6
(residual of an OLS of y1.0 on x0..x6 fitted on the same rows); a feature is interesting only if the IC has the same sign in every year and the
partial IC is non-zero (|t| > 3 pooled). Also IC with the next 4h return (bar open -> next bar open) of the five majors at 4h closes (dev only).
Write: fetcher with a manifest (rows, first/last time, sha256) under data/raw/<your dataset>_20261004/, a feature module, the study script, CSV +
SUMMARY.md (<= 20 lines) under research/diagnostics/newdata_<tag>/, tests in tests/test_newdata_<tag>.py (causality test: features computed on
data truncated at T equal the full-data features at T; synthetic cases). Public endpoints only, polite rate limits, resumable. Do not edit any
other file. Stop when done.
