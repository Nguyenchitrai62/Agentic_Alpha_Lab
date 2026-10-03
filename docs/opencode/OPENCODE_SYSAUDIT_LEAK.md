# OpenCode assignment: SYSTEM AUDIT 2 - data-leakage audit of the signal ("book") pipeline behind the deployed pipelines

Goal: independently check that the trading signals used by every deployed pipeline (M1-M5 MANUAL, R2/G2/CS BOT) use only information
available at the decision time, and that the walk-forward models never trained on data from their own test year. Priorities: part 1
(dynamic checks) > part 2 (truncation test) > part 3 (code review). Report what you could not finish.

## Write scope (nothing else)
- `research/diagnostics/system_audit/leak_opencode/` (scripts, CSV, `replication.json`, `SUMMARY.md`)
- `tests/test_system_audit_leak.py`
Do not edit any other file. Never look at returns after 2026-09-23. Run tests with
`.venv/Scripts/python.exe -m pytest tests/test_system_audit_leak.py -q`.

## Conventions (verify them, do not assume)
- Decisions are taken at 4h bar closes. A book row indexed t (UTC) is the decision for the HOLDING bar that starts at t + 4h, i.e. it
  may use data up to the close of the bar that starts at t (= t + 4h). Engine evidence: `research/parallel/rounds/parallel-20260906-r2/
  engine_user/engine_user.py` (prepare: "cube row i = holding bar T = idx[i] + 4h"; o1 = open at idx[i+1]).
- Research books of the deployed pipelines: `scripts/forward_v205.py::research_books_d2` = 0.8 x O1 books + 0.2 x the Coinbase-premium
  member D. O1 books = mean of members from `artifacts/research/engine_real/`: member_A_O1_orders, member_Aq_O1_orders, member_B_tv,
  member_Bq_tv; D = members_v154.parquet level "D" and members_quarterly_D.parquet (see research_books_o1 / research_books_d2 for weights).
- Member builders: `research/parallel/rounds/parallel-20260906-r2/v144/v144_deploy_v3.py` (annual walk-forward builder),
  `v202/v202_quarterly_retrain.py` (quarterly retrain wrapper), `v240/v240_order_level_flow.py` (O1 features), `v231/tv_indicators.py`
  (TradingView features), `v236/flow_features.py` (flow formulas), `v285/v285_coinbase_member_c4.py` (Coinbase member). Anchors are
  2021-09-24 .. 2025-09-24 (yearly); embargo must be >= the label horizon.
- Prices: 4h opens can be built from the raw 1m klines (`data/raw/btc_intraday_20260924/klines_1m_20*.parquet`,
  `data/raw/majors_intraday_20260924/<SYM>_1m_20*.parquet`; open at each 4h boundary).

## Part 1 - dynamic checks on the cached member predictions and the final books (save replication.json first)
For each member file above and for the combined research_books_d2 (call the function; it only reads parquet files), per symbol and per
anchor year Y (rows t in [anchor_Y, anchor_Y + 365 d)), compute Spearman correlations of the book value at row t with:
  r_dec  = return of the bar starting at t (open t -> open t+4h; already known at the decision),
  r_hold = return of the holding bar (open t+4h -> open t+8h),
  r_next = return of the bar after it (open t+8h -> open t+12h).
Leak flags: |corr(book, r_hold)| > 0.10 in any (member, symbol, year); or corr(book, r_hold) more than 3x corr(book, r_next) AND above 0.06.
Also compute the same for books shifted one row EARLIER (book row t+4h vs r_hold of row t): a large jump would mean an index off-by-one.
Report a table: member x year, mean over symbols of the three correlations.

## Part 2 - truncation test of the feature builders
For TradingView features (v231/tv_indicators.py) and the order-level flow features (v236/flow_features.py applied to
data/raw/aggflow_20260928_orders as v240 does), pick 20 random decision times T between 2022-01-01 and 2026-09-01. Build the features
(a) from the full history and (b) from the raw inputs truncated at the close of the bar T (drop every input row whose availability time
is after T + 4h). The feature rows at T must be identical (abs tol 1e-9). Report per builder: tested times, mismatching features.
If a builder cannot be run on truncated input in reasonable time, say so and do part 3 for it instead.

## Part 3 - code review of the walk-forward fit windows
In v144 / v202 / v285: quote (file:line) where the training rows for anchor Y are selected, the label definition (horizon), and the
embargo; confirm max(label end time of training rows) < anchor_Y (minus embargo). Also check that normalisation / calibration /
thresholds are fitted on training rows only.

## Output
`SUMMARY.md` (<= 30 lines): verdict per part (PASS / FLAG / NOT DONE), numbers, file:line evidence. Tests: synthetic leak example (a
book that equals r_hold must be flagged; a random book must not) + the truncation helper on a synthetic series. Stop when done.
