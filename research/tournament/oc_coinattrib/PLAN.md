# oc_coinattrib PLAN (pre-registered BEFORE any outcome, 2026-10-07)

## Question
Per-coin and per-side attribution of deployed G2 (book timing + dip sleeve):
is the return concentrated in one or two coins (concentration risk if that
coin's microstructure changes, e.g. listing / ETF regime), and which coins
carry the dip sleeve? Descriptive only — NO variant selection, NO tuning.

## Deployed reference (frozen)
- G2 = `R2B1D17BFG2` in `research/parallel/rounds/parallel-20260906-r2/v421`
  (`v421_runs.pkl`, `v421_result.json`). Expected 5y reset R/W/DD/full:
  5.41 / 2.588 / 16.91 / 16.82, years (R,DD) = (2.588,10.86),
  (3.282,16.91), (6.045,15.81), (10.677,8.27), (4.648,12.90).
- Reproduce f=0 exactly (same check as
  `oc_carrycompound/analyze_carrycompound.py` + `oc_bookattrib`:
  `reset_metric.year_reset` x5 + `v388` continuous full-path DD, assert to the
  digit) BEFORE any attribution. If reproduction fails, stop and report.
- Years: dev Y0..Y3 = anchors 2021/2022/2023/2024-09-24 +365d each
  ([A,A+365d) wall-clock); most-recent Y4 = 2025-09-24..2026-09-23 reported
  separately and labelled, never used for the verdict count. Verdict counts
  dev years only; 5y counts shown as labelled extras.
- No variants: ONE method below. Extra rows after seeing outcomes are
  disclosed extras, never replace pre-registered rows.

## BOOK leg (vectorised gross, reuse oc_bookattrib exactly)
- Import `research/tournament/oc_bookattrib/analyze_bookattrib.py` read-only
  (no copy-paste drift): `validate_g2()`, `load_books_standard()`
  (books154, opens_std, std=`research_books_d2`, sb=bear-filtered with v421
  x0.5 on longs when BTC < 1200-bar mean, bear mask), `load_shifted_opens()`
  (per-shift 4h opens from 1m first-minute-open logic), `monthly_geometric`,
  `BLOCK=42`, `NPERM=500`, `SEED=7`.
- Coins (engine order): BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT.
- Per shift s=0..3, per year Y: w = books_bear ffill to shifted clock (rows
  [:-1]), r = next-bar open-to-open on that shift's opens, valid mask skips
  any-NaN-open bars. Wall-clock window [A,A+365d).
- Per-coin split (additive, asserted to 1e-10):
  b_c(t) = w_c(t)*r_c(t); B_c factor = cumprod(1+b_c) -> monthly R.
  wbar_c(Y) = mean_t w_c(t) that year; beta_c(t) = wbar_c*r_c(t);
  timing_c(t) = b_c(t)-beta_c(t). Sum_c b_c = b, sum_c beta_c = beta,
  sum_c timing_c = timing (assert each).
- Per-coin-side cells: long_c(t) = max(w_c,0)*r_c, short_c(t) = min(w_c,0)*r_c
  (cumprod to R per coin-year). Pooled sides: long = sum_c long_c,
  short = sum_c short_c (must match oc_bookattrib long_R/short_R).
- Shares + Herfindahl (headline): per-phase timing sums
  T_c(s,Y) = sum timing_c; 4-phase mean Tm_c(Y) = mean_s T_c; total
  Tm(Y) = sum_c Tm_c; share_c(Y) = Tm_c/Tm if Tm != 0 else 0 (reported as-is,
  may exceed 100% / go negative if coins disagree — stated limit).
  H(Y) = sum_c share_c^2. Same for B sums as context. Per-phase shares kept
  in tmp for audit; headline shares from mean sums.
- Placebo PER COIN: 500 block-42 shuffles of w_c WITHIN each coin-year
  (whole-block permutation, last partial block kept as-is, exactly as
  oc_bookattrib but restricted to column c), seed = 7 + coin_idx (0..4,
  deterministic, disclosed), r real. T_perm_c = sum(b_perm_c - beta_perm_c)
  with beta from shuffled mean. Percentile = mean(T_perm <= T_actual),
  p = (1+#(T_perm >= T_actual))/501. 4-phase mean percentile reported.
- Leave-one-coin-out (vectorised, labelled NOT tradable): per shift/year,
  B_{-c} = sum_{k!=c} w_k r_k, BETA_{-c} with wbar recomputed without c,
  TIMING_{-c} = B_{-c}-BETA_{-c} -> monthly R (4-phase mean). Drop vs full
  timing reported.

## DIP leg (read-only ledger, NO 1m reload)
- Source: `research/tournament/oc_stoptf/fills.parquet` D0 leg ONLY
  (deployed TP-1sg/close5-stop/8sg-backstop/timeout-next-open, B1 sizes
  w=1/(1+n), maker 0.0002/taker 0.00055 + settle funding — identical replica
  to `oc_placebo_dip/compute_placebo_dip.py` D0; pairing requires all legs
  finite in both, count 22312 in both).
- Validation BEFORE use: n == 22312; 5y 4-phase-mean w*d0 sum == 7.718304
  (+-1e-4) and per-year means == oc_placebo_dip base_mean4 S
  (0.911273, 0.832599, 2.099814, 3.197390, 0.677229 +-1e-6) and per-phase
  sums match phase0_fidelity. If mismatch, stop and report (fall back to
  heavy rebuild is NOT allowed silently).
- Per coin per year: S_c(Y) = 4-phase mean of per-phase w*d0 sums;
  n_c(Y) = 4-phase mean trades; win_c(Y) = pooled fills (all 4 phases) with
  d0 > 0 strictly; stop_c(Y) = pooled (stop+backstop)/n (h0 in
  {"stop","backstop"}), plus stop-only rate; mean w_c. Share_c(Y) = S_c(Y) /
  S(Y) (all base yearly S > 0, so shares well-defined). H(Y) same formula.
- DD contribution: pooled-across-phases daily exit-day sums (key xd0 date,
  value w*d0, all 5y), cumulative path from 0, top-5 peak-to-trough DD
  episodes by magnitude (distinct non-overlapping (peak_day,trough_day]
  windows, sorted deepest first; dates = exit dates, labelled diagnostic —
  no open marks). Per episode per coin: sum w*d0 with xd0 in window.
  Report per-coin total across the 5 episodes + share of the 5-episode loss.
- LOCO dip: total mean4 sum without each coin = S(Y) - S_c(Y) per year +
  5y sum; reported per year.

## Key question (bold in REPORT)
Is any single coin > 40% of G2's timing or dip P&L in most years? Count =
#dev years (Y0..Y3) where max coin share > 40%, separately for book timing
shares and dip S shares; 5y count shown labelled. "Most years" = >= 3/4 dev
years. Also report LOCO worst-case drop.

## Gate costs / execution (labelled)
- Book vectorised: next-open fills, NO fees/funding/limit-miss/SL/TP —
  diagnostic gross only (gap to tradable book-only net in oc_bookattrib:
  gross 5y 3.489 vs net 2.531). Dip w*y: net of rung fees/funding per the
  replica (maker/taker + settle funding on timeouts), raw sums, no
  compounding normalisation. Gate maker 0.0002 / taker 0.00055 / long funding
  0.0001/8h, limit trade-through, no fill minutes 0-4, stop-first stated for
  the engine legs; not re-simulated here.

## Leakage statement (to verify in REPORT)
w at decision bar t uses latest standard-grid book row r<=t (ffill; s=0
identity); books are research fits frozen before each anchor
(research_books_d2 members); r uses next-bar opens (scoring only, never a
feature). Dip ledger is a frozen replica with fills on strict 1m
trade-through. No test-year / most-recent-year statistic entered any weight,
threshold or choice (single method, seeds fixed above). Fits/thresholds:
none in this study (read-only).

## Outputs (ONLY these paths)
- `research/tournament/oc_coinattrib/analyze_coinattrib.py` (imports
  oc_bookattrib + reads fills.parquet; light except 1m-open load for shifted
  opens — run via heavy_slot),
- `research/tournament/oc_coinattrib/tmp/coinattrib_raw.json`,
- `research/tournament/oc_coinattrib/results.json`,
- `research/tournament/oc_coinattrib/REPORT.md` (per-year tables, bold key
  question, honest limits, 3-line Vietnamese verdict adopt/reject/prospective
  + live-risk note),
- `tests/test_oc_coinattrib.py` (causality/truncation + hand-checked
  synthetic share/H/LOCO tests; run with `.venv/Scripts/python.exe -m pytest
  tests/test_oc_coinattrib.py -q`).
