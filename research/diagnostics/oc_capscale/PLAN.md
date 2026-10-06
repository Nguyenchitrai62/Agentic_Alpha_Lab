# oc_capscale PLAN (fixed BEFORE any outcome is computed)

## Goal
Capital scaling for the deployment configuration R2B1D17BFG2
(registry v421: R2B1D17BF + dip gross-notional cap G = 2.0): at which total
account size can a user deploy it as simulated?

## Harness (fixed; v421 wiring, no new choices after this)
- 4-phase 5-year harness copied from
  research/parallel/rounds/parallel-20260906-r2/v421/v421_gross_cap.py
  `worker(shift)`: phase grids s = 0..3h via
  research/diagnostics/phase_offset_full/phase_offset_full.py
  (`pod.minutes`, `prep_idx` on books154.index + shift, standard
  `forward_v205.research_books_d2` books forward-filled, BTC-bear halving,
  per-phase tables v376/tables_hidden/r2_table_s{s}.parquet through
  `pof.pipe_setup("v321", ..., True)` = v216 G2 grid trade policy,
  `sleeve_fill_size` = inv-correlated x kd=1.7, `risk_mult` k=1.0,
  `sleeve_risk_budget` = 0.26 x 1.0 x 1.7, `sleeve_gross_cap` = 2.0,
  `trade` unchanged, `win_start=5`).
- Live window per phase: [2021-09-24 + sh, 2026-09-23 + sh) (5 anchor years
  2021-2025, the v421 window). One engine at a time, strictly sequential
  (no Pool); before each phase wait until free RAM > 2 GB (PowerShell
  Win32_OperatingSystem, sleep 120 s); `del M` + `gc.collect()` after prep.
- Rows (FIXED, 4 account sizes): total account A in
  {2000, 5000, 10000, 25000} USDT. Each phase runs one sub-book at 1/4 of
  the capital: `eu.ACCOUNT = A / 4` for that simulate; Bybit-like minimum
  `eu.MIN_NOTIONAL = 5.0` for every symbol (the engine/oc_lots value).
  Everything else identical to v421 (causal; no refit; no selection).
- Unconstrained reference: NO rerun. v421 cached
  `v421_runs.pkl` R2B1D17BFG2 scored with the same metric code below.
  (v421 used ACCOUNT=10000 with Binance-style mins; at that size minimums
  almost never bind, so it is the unconstrained baseline.)

## Minimum enforcement and skip counting (fixed causal definitions)
- Book ENTRY orders (trade mode): enforced natively and exactly inside the
  engine - an entry whose `size * prev_eq * ACCOUNT` is below 5 USDT is not
  issued (position stays as it was until the next decision). Counting only:
  a `book_size` wrapper records every entry candidate (called only when a
  new order would be placed) and returns 1.0, so the run is bit-for-bit the
  native constrained run. Book entry skip share =
  1 - issued(A) / issued(Amax) pooled over phases (Amax = 25000: nothing
  binds there, so this is the exact in-path gap vs the intended flow).
  (In-position adds/reduces have their own native mins checks; they are not
  separately counted - covered by the weight-share bound below.)
- Dip rungs: the engine has no notional-minimum hook that sees both the
  equity and the fill price, so dip minimums are NOT enforced in-path.
  Every `rung_fill` event is checked post-hoc with causal info only:
  notional N = |weight| x phase-USDT-equity at the fill bar start
  ((A/4) x eq[i-1], eq = the run's own compounding multiplier) and the
  oc_lots Bybit rule (qtyStep floor: BTC 0.001 / ETH 0.01 / SOL 0.1 /
  BNB 0.01 / XRP 0.1, floored qty >= minQty AND floored notional >= 5 USDT;
  live fetch with the oc_lots fallback snapshot, source recorded).
  Reported: count share + gross-P&L share of placeable rungs. Path-impact
  bound: a skipped rung is < max(5, step-value) USDT on >= A/4 equity, so
  the reported 5y/DD numbers include book-minimum effects exactly and
  exclude dip-minimum effects bounded by the reported gross share.
- The same post-hoc Bybit check is applied to all placed book sizing orders
  (`order_issue` with |weight|>0: entries plus scale-adds; reduces place
  nothing): count share + weight share. The notional-5 part is in-path; the
  qty-step-only gap (mostly BTC notionals between 5 and one step value) is
  counted, and the small-A performance rows are therefore UPPER bounds whose
  gap is bounded by the weight/gross-P&L shares.

## Metrics per account size (fixed)
- Per anchor year (reset metric
  research/diagnostics/r2_decompose5/reset_metric.py `year_reset` on the
  4-phase 1/4 mix): R (%/month) and DD (1m-marked, conservative).
- R5 = geometric 5y mean 100*(prod(1+R/100)^(1/5)-1); W = worst yearly R;
  maxDD = max yearly DD; fullDD = conservative full-path DD of the 1/4 mix
  over the whole 5y (v388.mix conventions, 1m-marked minima vs peak).
- Skipped shares pooled over the 4 phases: book entries (in-path count),
  dip rungs (post-hoc count + gross-P&L share), per coin.
- Difference vs the unconstrained v421 row: dR5, dW, dMaxDD, dfullDD.

## Verdict rule (fixed)
One deployment-note paragraph in plain Vietnamese: the minimum account
size with R5 within 0.5 pp/month of unconstrained AND fullDD <= 20 AND
>= 99% of book entries and >= 99% of dip-rung gross P&L placeable, plus the
comfortable size (all four: R5 within 0.2 pp, no year below 2 %/month,
>= 99.5% placeable on both). No PROMISING claim (deployment note only).

## Outputs
- run_oc_capscale.py (sequential heavy runner + metric/skip helpers);
  oc_capscale_runs/ (local per-key cache, gitignored); results.json (metrics,
  deltas, skip shares, lot rules/source); REPORT.md (tables + verdict).
  Test: tests/test_oc_capscale.py (light: helpers + results integrity,
  no engine).

## Post-hoc change log (definitions fixed before outcomes except where noted)
- 2026-10-06, before aggregation: book in-path skip changed from
  1 - issued/candidates to 1 - issued(A)/issued(Amax). Reason: the run
  showed candidates AND issued bit-identical across sizes within each
  phase, i.e. the 5-USDT notional minimum binds nothing at any tested
  size (entry floor = 5% signal x E >= 25 USDT even at A=2000); the
  ~22% candidates gap is nonfinite-sigma bars, size-independent baseline
  engine behaviour. The Amax-relative form is the exact in-path gap.
- 2026-10-06, before aggregation: per-key cache files instead of one
  pickle (a 16-run single pickle died with MemoryError on this host).
