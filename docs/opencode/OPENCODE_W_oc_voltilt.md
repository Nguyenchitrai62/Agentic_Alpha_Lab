# OpenCode task oc_voltilt - is the foundation-model dip tilt just VOLATILITY timing? (simple-vol control with the identical rule)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_voltilt/` and `tests/test_oc_voltilt.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome. Engine via heavy_slot (RAM is tight: one engine job at a time).
No GPU, no new packages beyond .venv (if you need GARCH and `arch` is missing, implement the 1-step GARCH(1,1) filter with fixed per-anchor
MLE in numpy/scipy yourself).

## Why
Three foundation models with different pretraining (Kronos K2, Chronos C2, Toto T3; research/tournament/oc_kronoshidden, oc_chronos, oc_toto)
all give the same tilt direction (+1: bigger rungs when the forecast lower quantile is far below the price) and significant timing on 2023-2026
but none in 2021-2022. research/tournament/oc_kronosfeat: Kronos forecasts |move| (vol1 IC 0.18) but not sign. Hypothesis: the shared
content is plain short-term volatility timing - if a trivial causal vol forecast with the IDENTICAL rule gives the same gain, the models are
unnecessary (simpler, no pretraining contamination, nothing to host).

## Variants (pre-registered, exactly two)
risk_RV6 = std of the last 6 four-hour log returns of that shift's bars ending at the bar closing at T, divided by sigma (the same sigma360 as
Kronos / Chronos). risk_GARCH = one-step GARCH(1,1) forecast sigma for the bar opening at T (parameters fitted per anchor on that shift-0 4h
series before A - 7 d, frozen inside the year; filter runs causally) divided by sigma. Bars: research/tournament/oc_kronoshidden/
bars_4h_4shift.parquet, same T range. Causality truncation test.
Tilt V_RV6 / V_GARCH: rung size x1.25 / x0.75 on the outer quintiles, per-anchor fit exactly like oc_chronos / oc_toto (harness rows
t_exit < A - 7 d, shift-0 feature joined on (sym, T), direction = sign of Spearman(risk, y_dep), q20 / q80). Engine on G2 with the oc_chronos
mechanism (copy run_engine.py / tilt_rule.py; reproduce REF 5.41 / 16.91 / 16.82 first).

## Report
Rows REF, V_RV6, V_GARCH (+ C2, T3, K2 copied from their reports as reference, not re-run). Dev4 (fully clean here - no pretraining), robust
pick among REF / V_RV6 / V_GARCH on dev4 ONLY, then the post-release year scored ONCE for all three rows (labelled), 5y geometric, full-path DD,
timing placebo pct per year like research/tournament/oc_k2placebo. Also: Spearman of risk_RV6 / risk_GARCH with each FM risk (C2 ch_q10,
T3 f_q10, K2 low1) per year, and the share of (coin, bar) rows where V_RV6's multiplier equals C2's. Vietnamese 3-line verdict: is the FM tilt
explained by simple vol timing?
