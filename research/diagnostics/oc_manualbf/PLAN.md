# oc_manualbf PLAN (fixed before running, 2026-10-05)

Goal: MANUAL (book + human-placeable dip ladder, no bot needed) with the
v410 bear-regime book filter, on the honest human schedule, over the FIVE
years 2021-09-24..2026-09-23.

Harness (as manual_human.py + r2_decompose5.py, no new choices after this):
- 4h grids shifted s = 0..3h; phase_offset_full.prep_idx on the FULL
  books154.index + shift (r2_decompose5 full index, not the dev-truncated one);
  standard research books (forward_v205.research_books_d2) forward-filled as
  latest standard row r <= t_s (identity at s = 0); agents ON with the
  per-phase tables v376/tables_hidden/r2_table_s{s}.parquet; adverse long
  funding on the settlement bar; engine_user trade mode.
- Live window per phase: [2021-09-24 + sh, 2026-09-23 + sh) (Y1 = 2026-09-23
  as v388/v410; strictly inside market data up to 2026-09-24 00:00 UTC).
  Anchors ANCH5 = 2021-09-24 .. 2025-09-24 (+ sh per phase); year y covers
  [a0, min(a0 + 365d, live1)) as pof.metrics.
- ONE heavy process (multiprocessing Pool(1)), phases run sequentially,
  rows sequential inside a phase; minutes cube deleted after prep_idx.

Rows (FIXED, 6 = 2 pipelines x 3 variants; BF includes the human schedule):
- M4 = v362, M5 = v367 (via pof.pipe_setup, incl. book_mult 0.75, M5 tighten).
- <P>_base: deployed rules, minute-5 reaction, every bar (reproduces
  manual_human dev4 portion on years 0-3, extended to 5y).
- <P>_human: 15-minute reaction (book orders from minute 15, dip limits from
  minute 16 via sleeve_start) + night bar skipped: on the holding bar starting
  at (20 + s) UTC no new book order (flat -> wait, in position -> hold) and no
  new dip limit (sleeve_filter 0); resting orders, SL, TP stay (manual_human).
- <P>_humanBF: <P>_human PLUS the v410 bear filter on the STANDARD book rows
  BEFORE the shifted-clock forward fill: bear[t] = BTC 4h open[t] < mean of
  the prior 1200 opens up to t (opens_v154 BTCUSDT reindexed to the book
  index, rolling 1200, min_periods 600); on bear rows book LONG targets x0.5,
  shorts (<= 0) and zeros unchanged; dips/agents unchanged. Transform is
  strictly causal (row t uses opens <= t only).

Metrics per row (single clock, mean over the four phases as manual_human):
- per-year %/month: per phase m_y = 100*((1+net_y)^(1/12)-1), then mean over
  phases (plus per-phase values for transparency).
- R5 = mean over phases of the 5y geometric %/month
  (100*(prod(1+net_y)^(1/60)-1)); Rdev4 = same over years 0-3 (check vs
  manual_human.json); Rlast = year-4 monthly.
- DD = mean over phases of max yearly 1m DD + worst phase (DD_max);
  full-path DD is NOT the gate metric (gate = max yearly 1m DD here).
- book win rate (pooled over phases, v377 style: trade_stats per phase/year
  window summed dev+_hidden counts) and all-trade win rate (book + dip rungs
  rung_tp/sl/timeout by exit time, engine net ret incl. fees, as
  phase_offset_full.book_win).
- No selection on the last year: verdict compares human vs humanBF on the
  full 5y table only; dev4/last-year splits reported labelled.

Verdict vs the base gate: R5 >= 5 %/month AND DD < 20 AND book win > 55 %
(all three, on the pooled/mean numbers above).

Outputs: results.json + REPORT.md (this folder). Cache: oc_manualbf_runs.pkl
(local, gitignored). No commits, no leader-file edits.
