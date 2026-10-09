# oc_bookattrib PLAN (pre-registered BEFORE any outcome, 2026-10-07)

## Question
Where does the deployed G2 BOOK's return come from — beta vs timing vs
structure? Attribution + placebo for the deployed book
(0.8 x O1 + 0.2 x CB members, trade mode, bear-book filter, 4 clocks).

## Deployed reference (frozen)
- G2 = `R2B1D17BFG2` in `research/parallel/rounds/parallel-20260906-r2/v421`
  (`v421_runs.pkl` per phase 0..3, `t`/`eq`/`eq_min`; `v421_result.json` rows).
  Expected 5y reset metric R/W/DD/full: 5.41 / 2.588 / 16.91 / 16.82, years
  (R,DD) = (2.588,10.86), (3.282,16.91), (6.045,15.81), (10.677,8.27),
  (4.648,12.90). Reproduce f=0 exactly before any attribution (same check as
  `oc_carrycompound/analyze_carrycompound.py`: `v388.hourly` + `reset_metric`
  per-year reset + continuous full-path DD); if reproduction fails, stop.
- No variant selection: ONE attribution method only (no tuning, no
  alternative parameters). Extra rows after seeing outcomes are disclosed.

## Inputs (read-only, no edits outside this folder + test file)
- v421 pickle stores ONLY `t`/`eq`/`eq_min` per phase (verified 2026-10-07) —
  per-coin book weights NOT stored. So regenerate w read-only exactly as
  `v421_gross_cap.py:worker()`:
  `phase_offset_full.prep_idx` + `pipe_setup("v321",...)` path, standard-grid
  `fw.research_books_d2(eu)` rows after the v421 bear filter, ffill to each
  shifted clock. Prices: Binance perp 4h opens from the same `prep_idx`
  (`opens`, per shifted clock); 1m only for the book-only engine check.
- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (engine order).
- Years: dev Y0..Y3 = anchors 2021/2022/2023/2024-09-24 +365d each
  ([A, A+365d)); most-recent Y4 = 2025-09-24..2026-09-23 reported separately
  and labelled, never used for the verdict.

## Fixed book-weight construction (exact v421 replica)
- `books154, _opens_std = eu.er.v154_books()`; standard books
  `std = fw.research_books_d2(eu).reindex(books154.index).fillna(0)[cols]`.
- Bear flag (v421 lines 69-72): `btc=_opens_std["BTCUSDT"]`,
  `bear=(btc < btc.rolling(1200,min_periods=600).mean())`; `sb=std.copy()`,
  `sb[bear] = sb[bear].where(sb[bear]<=0, sb[bear]*0.5)` (longs x0.5, shorts
  kept). Per-shift `books_bear = sb.reindex(idx,method="ffill").fillna(0)`.
- `M=pod.minutes()`; per shift s: `opens,prep=pof.prep_idx(M,books154.index+sh,
  s,cols)` (identical to engine incl. float32 ffill, settle flags).
- w(c,t) = `books_bear` row at decision bar t (causal: latest standard row
  r<=t_s; at s=0 identity). r(c,t) = next-bar open-to-open
  `opens(t+4h)/opens(t)-1` per coin on THAT shift's opens (executable proxy;
  limit/SL/TP differences are engine effects, reported as gap).

## Fixed attribution (per phase s=0..3, then 4-phase mean; per year)
1. B (gross, vectorised): per-bar `b(t)=sum_c w(c,t)*r(c,t)`; yearly gross
   factor `G=sum log? NO — compounded`: `E=cumprod(1+b)` over bars with
   t in [A,A+365d) (bars with any NaN open skipped, coverage reported);
   monthly geometric `R=100*(E_end**(1/12)-1)`; also total %.
   Tolerance check: v421 pickle has no separable book P&L (total = book+dip+
   costs), so the engine share is NOT separable — run the book-only engine
   instead (see below) and report vectorised-gross vs book-only-net gap with
   costs/execution as the stated explanation (no tolerance pass/fail on
   gross-vs-net; code asserts vectorised self-consistency B=BETA+TIMING).
2. BETA/TIMING: per coin-year `wbar(c,Y)=mean_t w(c,t)` over that year's bars;
   `beta(t)=sum_c wbar(c,Y)*r(c,t)`, `timing(t)=b(t)-beta(t)`; cumprod each to
   monthly R. Identity `B=BETA+TIMING` asserted to 1e-10.
3. Market-beta regression (daily): daily book return `rd(d)=prod(1+b)-1` over
   the 6 bars of each UTC day; market `rm(d)` = equal-weight mean of coin
   daily open-to-open returns; OLS `rd=alpha+beta*rm+e` per year (intercept in
   daily units, annualised alpha reported too); Newey-West HAC(5d) SE/t-stats
   (statsmodels if present else manual Bartlett-5 implementation — fixed).
4. Placebo: 500 block-shuffles of w WITHIN each coin-year, block=42
   consecutive 4h bars (7d, preserves distribution+persistence), seed=7;
   permutation = random permutation of whole blocks (last partial block kept
   as-is); `T_perm=sum timing_perm` with the REAL r; actual timing P&L
   percentile = mean(T_perm<=T_actual) (one-sided); report per year + 4-phase
   mean; p=(1+#(T_perm>=T_actual))/(1+500).
5. Splits: long-only `b_long=sum_{w>0} w r`, short-only `b_short=sum_{w<0} w r`
   (cumprod to monthly R per year); bear-filter contribution: same vectorised
   run with `sb=std` (no x0.5) vs with filter, per-year R difference
   (filter minus no-filter).
- 4-phase mean: mean of per-phase yearly equity paths? FIXED: per-phase
  monthly R averaged arithmetically for the headline, plus the pooled path
  (mean of per-phase per-bar b(t) aligned by bar order — phases have equal
  bar counts) as a cross-check; both reported, headline = mean of R.

## Gate costs / execution (for the engine leg only)
Maker 0.0002 (entries/TP/limit exits), taker 0.00055 (stops/market), longs
pay 0.0001/8h settlement in (T,T+4h] window, shorts 0, limit fill only on 1m
trade-through, no fill minutes 0-4 after 4h close, stop-first in same bar —
all inside `eu.simulate` unchanged.

## Book-only engine check (heavy_slot, read-only replica)
G2 with dip sleeve OFF (`sleeve=False`, all else = v421 worker incl.
`corr_size/kd=1.7/risk_mult/k=1.0/budget 0.26*1*1.7/G=2.0`, `trade` from
`pipe_setup("v321")`, `win_start=5`), 4 phases via
`scripts/heavy_slot.py run --tag oc_bookattrib ...`; per-year reset metric +
full-path DD with `reset_metric`/`v388` helpers. Reports net tradable book
vs vectorised gross (gap = fees/funding/limit-miss/SL/TP/governor).

## Outputs
`analyze_bookattrib.py` (vectorised, light-ish 1m opens only),
`run_bookonly.py` (heavy engine), `results.json`, `REPORT.md` with per-year
tables, bold key question, 3-line Vietnamese verdict with live-risk
implication, leakage/execution statement. Test
`tests/test_oc_bookattrib.py` (causality/truncation + hand-checked
synthetic). Write ONLY `research/tournament/oc_bookattrib/` + that test.
