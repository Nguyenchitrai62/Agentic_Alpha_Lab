# oc_kpi_g2 PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

REPORTING task only (no PROMISING rule, no verdict). Repeat research/tournament/oc_kpi
exactly for the deployment configuration R2B1D17BFG2 (registry v421: R2B1D17BF +
dip gross-notional cap G = 2.0; see research/parallel/rounds/parallel-20260906-r2/v421/v421_gross_cap.py).

## Data (fixed here)
- Source of truth for equity: research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl
  (shifts s=0..3, row R2B1D17BFG2, each {t, eq, eq_min} on the 4h-close grid,
  live 2021-09-24..2026-09-23). The pkl holds ONLY t/eq/eq_min, so the assignment
  requires re-running the s=0..3 replicas with events.
- Replicas: exact v421 worker (v421_gross_cap.py::worker minus the REF skip, same
  pod.minutes, prep_idx, books_bear, pipe_setup("v321"), corr_size inv kd=1.7,
  risk_mult 1.0, budget 0.26*1.7, sleeve_gross_cap 2.0, trade=v216 grid policy,
  win_start=5) via a copy of research/tournament/oc_kpi/run_kpi_trades.py plus
  kw["sleeve_gross_cap"]=2.0, ONE process at a time, collecting events/attrib/bars/
  path_out/state. Equity check: rerun 4h-close eq == v421_runs.pkl eq to 1e-9
  relative (max abs rel diff) on every bar of every shift; abort on mismatch.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides the
  old RULES.md hidden-year cut; all five years are research data; findings need
  prospective validation). No refit, no selection, no tuning. LIGHT job: RAM < 1 GB,
  one process, no 1m data unless stated (engine holds majors 1m closes internally
  as in oc_kpi; no extra 1m reads).
- Mix helpers: research/diagnostics/r2_decompose5/reset_metric.py
  (year_reset: per-year 1/4-capital reset mix) and v388 (hourly, mix,
  ANCH=("2021-09-24",...), Y1=2026-09-23). g1 = Y1+12h everywhere.

## (1) Monthly returns (fixed, same as oc_kpi)
- Continuous 4-phase mix: e,mn = v388.mix(runs,"R2B1D17BFG2",g1) with hourly()
  grid 2021-09-24 04:00..g1. Calendar-month return for M in 2021-09..2026-09:
  R_M = e[last grid point in M]/e[last grid point strictly before M]-1
  (2021-09 partial from 2021-09-24; 2026-09 partial to g1). Table lists all 61
  months in %; summary: share >= +5%, share >= 0% (over all 61 AND over the 59
  full months as secondary), longest consecutive run of months < 0%.
- Per-year reset rows (reset_metric.year_reset y=0..4): R = monthly geo mean,
  DD = 1m-marked DD inside the reset year. These are the year numbers.

## (2) Trade win rates after fees (fixed, same as oc_kpi)
- Book trades: v213.trade_stats position episodes (book_fill -> book_stop /
  book_tp / book_close, adds/reduces folded in; net = side*(proceeds-cost)-fees
  over cost; maker 0.0002 entries/TP/close, taker 0.00055 stops; funding
  excluded). Dip rungs: rung_fill -> rung_sl|rung_tp|rung_timeout paired FIFO
  per symbol; engine ret is already net of rung maker/taker fees (and timeout
  funding); win = ret > 0. All trades = book episodes + dip rungs.
- Year bucket = ENTRY time (book_fill t / rung_fill t) in anchor year
  [A_k, A_k+365d), A=(2021-09-24,...,2025-09-24), A_5=2026-09-24. Report per
  year: n_book, win_book, n_rung (sl/tp/timeout split), win_rung, n_all,
  win_all; plus pooled 5y. Events pooled over s=0..3 sub-accounts (each phase
  is 1/4 capital; counts are summed, win rates are pooled trade counts).

## (3) Drawdowns (fixed, same as oc_kpi)
- Per reset year y: DD_4h = max 1-es/pk(es) and DD_1m = max 1-ms/pk(es) from
  the reset-mix segments (es,ms as in year_reset; pk = running max of es).
  Full path: continuous mix e,mn over (2021-09-24,g1]: DD_4h full, DD_1m full,
  DD_gate = max(both). Cross-check vs v421_result.json row R2B1D17BFG2.

## (4) Positions + exposure (fixed, same as oc_kpi)
- From rerun bars[] (per holding bar, per coin): qty, open=o1, equity.
  Book-open coin-bar = |qty|>0 at bar end. n_book_open per bar in 0..5.
  Dip-open: from paired rungs, rung open during [fill_t, exit_t); sampled at
  4h-bar ends AND counted as max concurrent within each bar from event times.
  Report: avg/max n_book_open, avg/max n_total_open (book+dip at bar ends),
  max concurrent dip rungs within any bar; gross exposure/equity per bar =
  sum_a|qty_a*open_a|/equity + dip open notional/equity (dip leg = sum of
  weight of open rungs, weights are fractions of bar-start equity rescaled to
  mix equity); report mean and max. If bars weights need rescaling across the
  4-phase mix, state the factor (1/4 each, mix equity base).

## Outputs (fixed)
- scripts: run_kpi.py (equity/monthly/DD from v421 pkl), run_kpi_trades.py
  (shift replicas 0..3 + G=2.0 cap, one process; writes events/bars per shift +
  checks), compute_kpi.py (win rates, positions/exposure, results.json +
  BF reference side-by-side). results.json (monthly table, yearly reset rows,
  win rates, DDs, exposure, checks, plus R2B1D17BF oc_kpi numbers next to it).
  REPORT.md (tables, plain language, one-line descriptive summary; no
  PROMISING verdict; BF column next to G2 everywhere). Test
  tests/test_tournament_oc_kpi_g2.py.
- Checks recorded in results.json: pkl keys, equity match 1e-9 per shift,
  monthly compounding vs 5y net, year partition cover (10944 bars/shift
  pattern), event pairing loss (unpaired fills count).
