# oc_governor PLAN (pre-registered BEFORE any outcome, 2026-10-07)

Assignment: docs/opencode/OPENCODE_W_oc_governor.md + common header
docs/opencode/OPENCODE_W_COMMON_20261007.md. This file freezes every choice
before any number is computed. Any change after seeing an outcome is kept as
a disclosed extra row, never a silent edit.

## Deployed reference (frozen)

G2 = `R2B1D17BFG2` in research/parallel/rounds/parallel-20260906-r2/v421
(v421_runs.pkl strat R2B1D17BFG2; v421_result.json):
5y R 5.410 / W 2.588 / max-yearly-DD 16.91 / full-path DD 16.82, no losing year.
Years (R %/mo, DD %): 2021 (2.588, 10.86), 2022 (3.282, 16.91),
2023 (6.045, 15.81), 2024 (10.677, 8.27), 2025-09-24 labelled (4.648, 12.90).
G2 config (v421_gross_cap.py worker, non-REF branch): v321 pipe (history_tm +
v221 + v216 GRID trader, agents ON via hist.R2_TABLE), books = research_books_d2
with x0.5 bear filter on longs ffill to shifted clocks, corr-size inv/kd=1.7,
risk_mult=1.0, sleeve budget 0.26*1.7, gross cap 2.0, sleeve ON, trade mode,
win_start=5, default gov (0.20, 0.10). Gate costs: maker 0.0002, taker 0.00055
(stops/market exits), longs 0.0001/8h, shorts nothing, limit fill only on 1m
trade-through, no fill minutes 0-4, stop-first on ties.
Metric: reset_metric.year_reset per anchor year (fresh 1.0 at each anchor) +
v388.mix hourly full-path DD (max of close/marked, same as v421). Reproduce the
G2 numbers above EXACTLY from v421_runs.pkl before any overlay; else stop.

## Pre-registered engine rows (ONE knob each, DD gate = 4-phase-mix max close/1m)

- GV1: gov = (0.25, 0.10) (zero at 25% DD, full size below 15%). All else = G2.
- GV2: gov = (0.30, 0.15) (zero at 30% DD, full size below 15%). All else = G2.
- GV3: pooled-account governor approximation (TWO-PASS, labelled): pass 1 =
  G2 stored phase paths -> hourly combined equity E(t) = mean of 4 phase eq
  (v388.hourly ffill) -> combined dd(t) = 1 - E(t)/trailing-90d-peak E(t);
  per-phase g_s[i] = clip((0.20 - dd_comb(t_lag))/0.10, 0, 1), t_lag = end of
  that phase's own bar j = i-2 (its stored t[j]); first 2 bars g = 1.
  Pass 2 = G2 harness with per-bar governor overridden to g_s via
  gov=(1.0, 1e-9) (default g ~= 1) x risk_mult(i) = g_s[i] (applied on live
  bars, same lag convention as the engine). Report max/mean abs difference
  between pass-1 and pass-2 combined dd(t) time series. All else = G2.
No other variants. No tuning on outcomes.

## Selection (dev years ONLY: anchors 2021/2022/2023/2024-09-24, each [A, A+365d))

- Stage 1 (dev): run G2-harness reproduction + GV1/GV2/GV3 dev window
  (live = DEV0+sh .. 2025-09-24+sh). Compare ONLY dev4.
- Robust criterion: eligible = max yearly DD <= 20 and no losing dev year;
  prefer dev4 mean >= 5 %/mo if any; among those pick highest dev4 WORST-year
  monthly R; ties -> higher mean.
- Qualifier for recent-year scoring: dev4 mean > G2 dev4 mean AND dev4 worst
  year >= G2 dev4 worst AND max yearly DD <= 20 (hard cap; also note vs 16.91).
- Stage 2 (recent year 2025-09-24 .. 2026-09-23) scored ONCE, only for
  qualifiers (+ G2 reference, already stored/labelled). No iteration after.
- If nothing qualifies, no stage-2 engine run; REPORT states rejection.

## Descriptive (Task 1, stored G2 runs only + labelled proxy)

Per phase (s = 0..3) and per wall year (5 anchor years): recompute g from the
stored phase eq path with the audited formula (PD=6, 90d = 540 bars, lag 2:
g[i] = clip((0.20 - (1 - eq[j]/max(eq[j-539..j])))/0.10), j = i-2; g = 1 for
i < 2; NaN-safe). Report: share of live bars with g < 1 and g == 0, longest
consecutive g == 0 spell (bars and dates), mean g, and phase eq window return
inside vs outside g == 0 spells. Missed-P&L: NO same-fill counterfactual exists;
estimate with the LABELLED vectorised book proxy of oc_bookattrib (w x r,
w = bear-filtered research books ffill, r = next-bar open-to-open on that
shift's 4h opens; engine vol-scale/governor/costs/fills excluded) as
sum((1 - g_b) x b_b) per phase-year, plus dip rung sizes scale with g so the
dip miss is proportionally larger (stated, not quantified bar-for-bar). All
proxy numbers labelled APPROXIMATION, never mixed with engine rows.

## Live governor check (Task 1, read-only)

Inspect scripts/forward_trade_phase.py build() + backend/multiphase.py merge():
each phase s replays eu.simulate from start-WARMUP with eu.v110.START/END set
around its own window, so g inside is from THAT phase sub-book's own eq path;
merge() averages sub-book growths (capital 0.25 x growth/mix, never rebalanced)
and never feeds the pooled mix back into g. State YES/NO whether live also uses
per-phase sub-account equity (expected YES), with file:line pointers.

## Leakage / causality

- Descriptive g uses only stored eq up to j = i-2 (same lag as engine); proxy
  books are research_books_d2 ffill (latest standard row <= t_s) and r uses
  opens t -> t+1; no fits on test years; no forward returns for >= 2025-09-24
  are used to choose anything (recent year scored once for qualifiers only).
- Engine rows: books/sigma/vol-scale/governor/agents all causal per v421
  harness; agents keyed by holding bar (size/TP decided at bar open); fills
  win_start=5 + trade-through + stop-first; test file has a truncation/lag test
  + hand-checked synthetic governor test.

## Outputs (ONLY these paths)

- research/tournament/oc_governor/PLAN.md (this file), compute_descriptive.py,
  compute_engine.py, analyze_engine.py, REPORT.md, results.json, tmp/ snippets.
- tests/test_oc_governor.py (>= 1 causality/truncation test + >= 1 synthetic
  hand-checked case; run with .venv/Scripts/python.exe -m pytest -q).
- Heavy engine via: .venv/Scripts/python.exe scripts/heavy_slot.py run
  --tag oc_governor --min-free-gb 2.0 -- <cmd>. Progress print every ~10 min.
