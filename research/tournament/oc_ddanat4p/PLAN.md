# oc_ddanat4p PLAN (pre-registered BEFORE any outcome is computed, 2026-10-05)

## Hypothesis / scope
DIAGNOSTIC only (no PROMISING rule, no verdict threshold). oc_ddanat17 dissected
only phase s=0. The gate number is the 4-phase reset metric: R2B1D17BF max yearly
DD 18.33 in anchor year 2023-09-24..2024-09-23, full-path DD 16.9
(research/parallel/rounds/parallel-20260906-r2/v411/v411_runs.pkl via
research/diagnostics/r2_decompose5/reset_metric.py). This task finds which
mixed-path episode produces the 18.33, whether phases are synchronous, and what
each phase lost on (book long / book short / dip, by coin, by exit kind).

## Exact causal definitions (fixed before running)
- Input: ONLY research/parallel/rounds/parallel-20260906-r2/v411/v411_runs.pkl
  strat R2B1D17BF (shifts 0..3, each t/eq/eq_min, 10944 bars) for task (1); exact
  oc_ddanat17 replica reruns for shifts 1..3 for task (2). Market data read only
  to 2026-09-24 00:00 UTC. All five years are research data (assignment override
  of RULES.md hidden-year rule); findings need prospective validation. No refit,
  no selection, no tuning. ONE process at a time.
- Mixed path: replicate v388.hourly + mix EXACTLY (hourly grid
  2021-09-24 04:00 .. Y1+12h ffill, es=mean(e_s), ms=mean(mn_s)) and
  reset_metric.year_reset (per-year rebase at anchor) to confirm yearly DDs
  [12.42, 16.23, 18.33, 8.26, 12.81] and full-path DD 16.9 (continuous mix,
  seg > 2021-09-24, max(1-ms/maxaccum(es))). Tolerance 0.05pp vs v411_result.json.
- Episodes: on a given equity path (a) yearly-reset path of anchor year 2
  (2023-09-24..2024-09-23, rebased to 1.0 at anchor, 1m-marked ms/pk) the episode
  behind the 18.33 = the peak-to-trough pair attaining the max (peak = argmax
  before trough; trough = argmin of es/ms giving max DD; ties -> earliest peak,
  latest trough); (b) full-path continuous mix: running-peak candidates where a
  new max-DD trough appears below all prior (as in run_ddanat17.py), ranked by
  depth, take the FOUR deepest non-overlapping (peak,trough] windows sorted by
  peak time. Report 4h-close DD (es) and 1m-marked DD (ms) per episode.
- Per-phase DD per episode: using each phase's OWN hourly series (e_s, mn_s on
  the same grid): DD_s = 1 - min(mn_s[p:q+1]) / e_s[p] (phase's worst mark vs
  its own level at mixed-path peak hour), plus phase trough hour
  (argmin of minimum(e_s,mn_s) in window). Synchronous = trough hours within
  24h of each other AND all DD_s > 50% of mixed DD; else async/mixed (name which
  phase leads/lags).
- Phase 1-3 reruns: copy of research/tournament/oc_ddanat17/run_ddanat17.py with
  ONLY shift changed (shift=1,2,3), same books_d2 + bear filter (BTC open <
  rolling-1200 mean), same r2_table_sN, same corr_size inv kd=1.7, budget
  0.26*1.7, v216 grid trade, win_start=5, events/attrib/path_out/bars on, live
  [2021-09-24, 2026-09-23+12h)+shift. Checks: rerun eq end vs v411_runs.pkl
  shift-N R2B1D17BF end rel diff < 1%; attrib linear sums vs eq move < 2pp.
- Episode attribution per phase: restrict to the 18.33 episode window from task
  (1) mapped onto that phase's bar clock: attrib rows with bar-end in
  (peak_end-4h, trough_end-4h] (same convention as run_ddanat17.py); book
  long/short split by sign of books_bear target at that bar; dip = sleeve
  fractions; dip per coin from rung_sl/rung_tp/rung_timeout exit events in
  (peak_end, trough_end]; exit-kind split likewise. Tables in % of
  episode-start equity, same units as oc_ddanat17. Phase 0 numbers reused
  read-only from oc_ddanat17/results.json (no recompute).
- Cross-checks: task-(1) mixed DDs reproduce v411 numbers; per-phase window DDs
  average-approximate the mixed DD (no exact equality expected: mean of marks
  vs mark of means).

## Decision / verdict rule
None (diagnostic). REPORT.md gives: (1) episode table + per-phase DDs +
synchronicity sentence; (2) per-phase attribution tables for the 18.33 window;
(3) plain statement of what a rule would need to cut to bring that episode
below 15% (arithmetical loss share that must go, in episode-equity points, and
which leg/coin/exit kind holds it), plus which past rejected levers touched it
(governor v110/v141, stop distance v388/v417-X, cooldown v417-C, bear book
v410/BF) with their recorded DD deltas. One-line verdict names the mechanism.

## Outputs
- scripts: run_mix.py (light, pkl-only), run_phase.py (shift-param replica, one
  heavy process at a time), results.json, REPORT.md. Test:
  tests/test_oc_ddanat4p.py (files exist, PLAN predates results, gate numbers
  reproduced, episode/attribution schema).
