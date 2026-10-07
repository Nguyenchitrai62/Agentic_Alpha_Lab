# oc_ddanat_g2 PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

## Hypothesis / scope
DIAGNOSTIC only (no PROMISING rule, no verdict threshold). The deployment
configuration R2B1D17BFG2 (registry v421: R2B1D17BF + dip gross-notional cap
G = 2.0; see v421_gross_cap.py) has max yearly DD 16.91 in anchor year
2022-09-24..2023-09-23 and full-path DD 16.82 (research/tournament/oc_kpi_g2,
from research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl via
research/diagnostics/r2_decompose5/reset_metric.py + v388 hourly/mix). This
task finds which mixed-path episode(s) produce the 16.91, whether phases are
synchronous, and what each phase lost (book long / book short / dip, by coin,
by exit kind), following the method of research/tournament/oc_ddanat4p.

## Exact causal definitions (fixed before running)
- Input: ONLY research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl
  strat R2B1D17BFG2 (shifts 0..3, each t/eq/eq_min, 10944 bars) for task (1);
  phase replicas with the EXACT oc_kpi_g2 wiring (v421_gross_cap.py worker:
  dips x1.7 inv-rule, budget 0.26*1.7, bear-book filter, R2 agents r2_table_sN,
  v216 grid trade policy, win_start=5, sleeve_gross_cap 2.0) plus
  events/attrib/bars collection for task (2). Market data read only to
  2026-09-24 00:00 UTC. All five years are research data (assignment override
  of RULES.md hidden-year rule); findings need prospective validation. No
  refit, no selection, no tuning. ONE process at a time. LIGHT job: RAM < 1 GB,
  one process, no extra 1m reads (engine holds majors 1m closes internally as
  in oc_kpi_g2).
- Mixed path: replicate v388.hourly + mix EXACTLY (hourly grid
  2021-09-24 04:00 .. Y1+12h ffill, es=mean(e_s), ms=mean(mn_s), g1 =
  2026-09-23 12:00 UTC) and reset_metric.year_reset (per-year rebase at anchor)
  to confirm yearly DDs [10.86, 16.91, 15.81, 8.27, 12.90] and full-path DD
  16.82 (continuous mix, seg > 2021-09-24, max(1-ms/maxaccum(es))). Tolerance
  0.05pp vs v421_result.json row R2B1D17BFG2.
- Episodes: (a) on the yearly-reset path of anchor year 1
  (2022-09-24..2023-09-23, rebased to 1.0 at anchor, 1m-marked ms/pk) the
  episode behind the 16.91 = the peak-to-trough pair attaining the max (peak =
  argmax before trough; trough = argmin giving max DD; ties -> earliest peak,
  latest trough); (b) reset-chained path (yearly-reset segments chained
  multiplicatively) four deepest non-overlapping (peak,trough] windows sorted
  by peak time (same candidate rule as oc_ddanat4p run_mix.py: every new
  close-drawdown trough below all prior, ranked by depth); (c) full-path
  continuous mix: same four-deepest rule. Report 4h-close DD (es) and 1m-marked
  DD (ms) per episode. The "16.91 episode and next three largest" are the four
  reset-path episodes (b), with the full-path table (c) as cross-check; if the
  16.91 pair is a 1-hour mark artifact (as the 18.33 was), extend to the
  subsequent close trough and log it as a post-hoc change.
- Per-phase DD per episode: using each phase's OWN hourly series (e_s, mn_s on
  the same grid): DD_s = 1 - min(mn_s[p:q+1]) / e_s[p] (phase's worst mark vs
  its own level at mixed-path peak hour), plus phase trough hour (argmin of
  minimum(e_s,mn_s) in window). Synchronous = trough hours within 24h of each
  other AND all DD_s > 50% of mixed DD; else async/mixed (name which phase
  leads/lags).
- Phase replicas: copy of research/tournament/oc_kpi_g2/run_kpi_trades.py with
  ONLY attrib/bars collection added (same books_d2 + bear filter, same
  r2_table_sN, same corr_size inv kd=1.7, budget 0.26*1.7, sleeve_gross_cap
  2.0, v216 grid trade, win_start=5, live [2021-09-24, 2026-09-23+12h)+shift,
  ONE process at a time). Checks: rerun eq end vs v421_runs.pkl shift-N
  R2B1D17BFG2 end rel diff <= 1e-9 and overlap 10944/10944; event counts vs
  oc_kpi_g2 events_sN.parquet (same wiring: n_events, n_rungs equal);
  attrib linear sums vs eq move < 2pp per episode window.
- Episode attribution per phase: restrict to the episode window from task (1)
  mapped onto that phase's bar clock: attrib rows with bar-end in
  (peak_end-4h, trough_end-4h] (same convention as run_phase.py / oc_ddanat4p);
  book long/short split by sign of books_bear target at that bar; dip = sleeve
  fractions; dip per coin from rung_sl/rung_tp/rung_timeout exit events in
  (peak_end, trough_end]; exit-kind split likewise. Tables in % of
  episode-start equity, same units as oc_ddanat4p. For a one-bar crash window
  the close-trough extension window (peak, close_trough] is used and logged.
- Cross-checks: task-(1) mixed DDs reproduce v421 numbers; per-phase window
  DDs average-approximate the mixed DD (no exact equality expected).

## Decision / verdict rule
None (diagnostic). REPORT.md gives: (1) episode table + per-phase DDs +
synchronicity sentence; (2) per-phase attribution tables for each of the four
episodes (full detail for the 16.91 window; summary for the next three);
(3) plain statement of what a rule would need to cut to bring G2 below 15%
(arithmetical loss share that must go, in episode-equity points, and which
leg/coin/exit kind holds it), plus whether the 16.91 episode is a one-bar
event (like 2024-01-03 for D17BF) or a slow grind. One-line verdict names the
mechanism.

## Outputs
- scripts: run_mix.py (light, pkl-only), run_phase.py (shift-param replica +
  attrib, one heavy process at a time), make_results.py (light assembly),
  results.json, REPORT.md. Test: tests/test_oc_ddanat_g2.py (files exist, PLAN
  predates results, gate numbers reproduced, episode/attribution schema).
