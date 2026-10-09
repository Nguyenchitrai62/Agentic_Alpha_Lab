# oc_paperpower — PLAN (pre-registered before computing any outcome)

Descriptive power study, information only. No new trading rule, no selection,
no fitting. Assignment: docs/opencode/OPENCODE_W_oc_paperpower.md + common
header docs/opencode/OPENCODE_W_COMMON_20261007.md.

## Question
Go-live gates (scripts/prospective_scorecard.py GO_LIVE;
docs/DEPLOYMENT_PLAN_VI.md s2.3/s4): after >= 8 weeks of paper, live return
percentile >= 20 of the research bootstrap for the same horizon, paper DD <=
15 %, paper-vs-plan divergence <= 1.5 pp/month, no cycle_error > 1 h. How
informative is that after 8 / 12 / 26 weeks (+ 52 weeks reference)?

## Inputs (read-only, never edited)
- G2 4-phase runs: research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl,
  strat R2B1D17BFG2; expected baseline v421_result.json rows R2B1D17BFG2
  (R 5.41 / W 2.588 / DD 16.91 / full_path_dd 16.82).
- Carry overlay definition: research/tournament/oc_carrycompound/analyze_carrycompound.py
  (f = 0.25), carry trades research/tournament/oc_cashcarry/results.json
  (33 entered, threshold_ann_basis 0.04), hourly spot research/tournament/ext/hourly_ext.parquet,
  quarterly 1h data/raw/qbasis_20261003, spot 4h data/raw/spot_majors_20260925,
  phase helper research/parallel/rounds/parallel-20260906-r2/v388/v388_bot_stop_distance.py.
- Gate text: scripts/prospective_scorecard.py (GO_LIVE / STOP_RULE / bootstrap),
  docs/DEPLOYMENT_PLAN_VI.md s2.3 + s4.

## Exact causal definitions (frozen)
1. Hourly G2+carry equity built EXACTLY as analyze_carrycompound.py continuous
   full-path pass at f = 0.25 (same GRID0 2021-09-24 04:00 UTC, same g1 =
   v388.Y1 + 12 h, same last-close-before strictly-before-t marking, same
   entry-paid fee 0.001 + 0.00055, same frozen ret_alloc, same notional
   N = f x live A at each entry, same r_bot-on-whole-equity recursion
   A(t) = A(t-1)*(1+r_bot(t)) + dU(t), same marked path
   M(t) = A(t-1)*(ms_base(t)/es_base(t-1)) + dU(t)). f = 0 short-circuits to
   base bit-exact. VALIDATION GATE: f = 0 must reproduce v421_result G2
   per-year R and DD lists, R/W/DD and full_path_dd TO THE DIGIT; if it does
   not, STOP and report, no bootstrap.
2. Daily research series: restrict continuous close path A_c to
   (2021-09-24 00:00 UTC, 2026-09-23 00:00 UTC]; daily equity E[d] = last A_c
   value with timestamp <= D[d] for D = date_range(2021-09-24, 2026-09-23,
   freq=1D, tz=UTC) (ffill; causal, right-continuous), except E[2021-09-24]
   which is seeded with the first hourly value A_c[0] (grid starts 2021-09-24
   04:00, so the 00:00 mark has no prior point). Daily simple returns
   r[d] = E[d]/E[d-1] - 1 for d >= 1 (N = 1825 values, 2021-09-25..2026-09-23).
   (Pre-outcome fix: PLAN first said 1826; correct is 1825 returns over 1826
   daily marks. No outcome had been computed when fixed.)
   All five years are research data; use is DESCRIPTIVE only (no selection,
   no fitting, no threshold tuning).
3. Horizons (pre-registered): 8 / 12 / 26 / 52 weeks = 56 / 84 / 182 / 364 days.
4. Scenarios (pre-registered shifts of the same daily vector, mu = mean(r)):
   S_good = r as is; S_half = r - mu/2 (mean halved); S_zero = r - mu (zero
   mean, same volatility/tails); S_neg = r - mu + mu_neg with
   mu_neg = (1 - 0.01)**(1/30.4167) - 1 (daily arithmetic mean whose geometric
   pace is -1 %/month on a 30.4167-day month; computed in code, ~-0.00033).
5. Bootstrap (pre-registered): fixed 10-day blocks exactly as
   prospective_scorecard.bootstrap (random start uniform in [0, N-block],
   non-circular, concatenate blocks, truncate to horizon, seed 0 via
   numpy.default_rng(0)), 5000 paths per (scenario, horizon). Path equity
   P_k = cumprod(1 + block returns); cumulative return C = P_H - 1; daily-close
   maxDD = max(1 - P_k / running peak of P). Reference thresholds from the
   S_good bootstrap at the same horizon: p20 = 20th percentile of C,
   p5 = 5th percentile of C.
6. Gates simulated per path: PASS = (C >= p20) AND (maxDD <= 15 %).
   STOP = (maxDD > 20 %) OR (C < p5). Divergence (<= 1.5 pp/month) and
   cycle_error (> 1 h) are live-execution checks and are NOT simulated;
   reported as not-covered.
7. Sensitivity (pre-registered): repeat the full table with 30-day fixed blocks
   (same seeds/paths structure, block = 30), one extra row-set.
8. Summaries: per (horizon, scenario) PASS % and STOP % (of 5000); reference
   p20/p5 cumulative-return thresholds and research daily mu/vol; false-pass =
   S_zero/S_neg PASS %; true-pass = S_good PASS %. Recommendation rule
   (pre-registered, descriptive): shortest horizon at which S_zero PASS <= 20 %;
   state plainly how weak 8 weeks is if S_zero passes well above 20 %.

## Decision / selection rule
None. No variant comparison, no deployment change. The tournament dev4
selection rule and the most-recent-year-once rule do not pick anything here;
per-year table (including 2025-09-24 labelled most-recent) is reported for
context only. No statistic from this study feeds any model or threshold.

## Leakage / validity notes
- Hourly carry marks use only the last CLOSED hourly bar strictly before t;
  daily E[d] uses only A_c <= D[d]; bootstrap resamples past daily returns only.
- Full five-year window is descriptive per assignment (no selection); the
  reference distribution and the simulated scenarios share the same five years,
  so PASS rates are in-sample descriptions of gate sharpness, not OOS claims.
- Daily-close DD understates true 1m-marked DD; the gate DD numbers here are
  therefore optimistic (lower-bound) vs the official max(4h-close, 1m-marked) DD.
- Bootstrap preserves <= 10-day (sensitivity 30-day) dependence only; it
  ignores annual regime persistence — stated as the assignment's caveat.

## Gate costs
Already inside the equity (maker 0.0002 entries/TP, taker 0.00055 stops, gate
funding, limit trade-through fills per engine_real / oc_carrycompound). No extra
cost layer is added in the bootstrap (returns are resampled as printed).

## Resources
LIGHT-MEDIUM single process: ~44k hourly rows + 1826 daily values + 4 x 4 x
5000 x <= 364-day simulations in numpy (vectorised per-batch, chunked if
needed). No 1m data, no engine rerun, no GPU. Run through the shared semaphore
only if RAM is expected > 0.4 GB; otherwise direct. Seed fixed (0).
Script: research/tournament/oc_paperpower/analyze_paperpower.py ->
results.json + REPORT.md. Test: tests/test_oc_paperpower.py.
