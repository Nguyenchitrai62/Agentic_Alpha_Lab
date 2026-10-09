# oc_fundclock — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_fundclock.md` (= IDEAS5 §5, rank 5) +
`docs/opencode/OPENCODE_W_COMMON_20261007.md` (+ AGENTS.md, OPENCODE_VF_COMMON.md,
`docs/opencode/IDEAS5_20261008.md` §5 read in full + CLOSED rows read in full).
Write ONLY `research/tournament/oc_fundclock/` + `tests/test_oc_fundclock.py`.
Engine / heavy 1m work via `scripts/heavy_slot.py` (one job at a time, one coin at
a time where 1m is touched, float32). Heartbeat print every 600 s in long jobs.
Progress print every ~10 min. Scratch only under `research/tournament/oc_fundclock/tmp/`.
GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/rm/commit/switch/rebase/merge.
No orders, no authenticated endpoints, no Kaggle uploads. No inspection outside the
workspace (no /proc, no system temp).

## Why (IDEAS5 §5, rank 5)

2024-26 funding-seasonality notes + program fact (gate funding adverse-flat; actual
predicted funding is public pre-settlement): crowded longs pay most exactly at
00/08/16 UTC; holding into a p90-predicted settlement is uncompensated bleed + gap
risk (Oct-2025: futures led, basis swung $1,367 in 8 min).
CLOSED rows read: `oc_bookfunding` (7d LEVEL p80 tilt x0.75, CLOSED as NOT PROMISING:
P&L>=97% 3/5, DD-not-worse 3/5, 5y total -8.8% — hot funding marks strong longs) and
`oc_idea4` (funding-SURPRISE settled-minus-premium dip filter, CLOSED as NOT PROMISING:
sign 5/5 but tail 3/5, retention 37-90%) — both are level/surprise tilts; this is
settlement-CLOCK timing (flatten into the settlement window + dip-bid cancel around
the clock, re-enter next signal), so kept per the IDEAS5 near-duplicate note.

## Variants (exactly two + reference, no others)

- REF = G2 unchanged (R2B1D17BFG2, v421 runs: rule inv, k 1.0, kd 1.7, bear True, G 2.0).
- W1 = funding-clock flatten + dip cancel: at a flagged settlement S for coin sym,
  (a) that coin's book LONG weight x0.5 on the standard-grid 4h bar T=S (after the
  exact v421 bear filter, before the shifted-clock forward fill; shorts/flats
  untouched), AND (b) dip rung multiplier 0 for that coin on the holding bar
  starting at S (post-settlement bar skip; covers [S,S+30m]; see dip approximation
  note below). Re-enter next signal (limit, maker — engine handles).
- W2 = book-only: same (a) book-long x0.5, NO dip cancel (dip tilt 1 everywhere).
- No exposure-matched control (IDEAS5 §5 does not ask; disclosed).
- Frozen numbers (never fit): predicted-as-of 1h before settlement, trailing-90d
  window, p90 threshold, 7-day embargo, scale x0.5, dip skip = 0, +-30min window.
  All round numbers from IDEAS5, frozen ex-ante.

## Predicted-funding proxy (exact causal definition, frozen; disclosed substitution)

Binance public bulk data (`data.binance.vision` fundingRate) archives SETTLED rates
only (8h rows `*_funding.parquet`: calc_time, last_funding_rate); no free public
endpoint serves a historical per-minute predicted-funding series (`oc_idea4` PLAN
disclosed the same gap BEFORE its run). IDEAS5 §5 names
`data/raw/binance_premium_20260928` (predicted + settled, local) — the folder holds
settled funding + premium-index 1m (the per-minute published crowding input from
which Binance predicted funding is computed). The operationalised predicted leg,
frozen here: P(S,sym) = mean premium-1m close over the 60 bars with open_time in
[S_floor-120m, S_floor-61m] (bar ENDs in (S_floor-120m, S_floor-60m], i.e. the 60m
TWAP ending exactly 1h before the settlement hour; all bars end <= S-60m, strictly
pre-settlement-1h, timestamped at S-1h). Require >= 30 valid bars else NaN (no
imputation). S runs over the coin's funding-file rows (settlements S wall time =
calc_time, kept with its ms offset); S_floor = S floored to the minute. This is the
same TWAP construction as `oc_idea4` V1 (there 60m ending at S; here 60m ending at
S-60m per "as of 1h before settlement"), causal and uses only the folder IDEAS5 names.

## Thresholds and flags (exact, walk-forward, per-coin)

- ANCH5 = 2021-09-24 .. 2025-09-24 (UTC). For anchor A and coin sym: pool = {P(S,sym)
  : S in [A-97d, A-7d)} (90 days of settlements ending 7d before the anchor; 7d
  embargo; strictly previous data only). q90[A,sym] = 90th percentile (linear
  interpolation, numpy default). Require >= 50 settlements in the pool else q90 = NaN
  and that coin is NEVER flagged that year (disclosed skip, never imputed).
- Year y=[A, A+365d) uses q90 of its anchor A on all four phase shifts. No test-year
  statistic feeds any threshold.
- Flag: settlement S of coin sym in year y flagged iff finite P(S) and finite
  q90[A(y),sym] and P(S) > q90 (strictly greater); NaN -> False.
- Book gate at standard-grid 4h bar T (T in {00,04,08,12,16,20 UTC}): gate(T,sym)
  true iff T is a funding settlement hour (T.hour in {0,8,16} and T.minute==0) AND
  the settlement S=T of that coin is flagged. Rows with T < 2021-09-24 never gated.
  Only book LONGS x0.5 (`sb.where(~(gate & (sb>0)), sb*0.5)`); shorts/flats identical.
- Dip cancel (W1 only) approximation (frozen, disclosed): the IDEAS5 "+-30min around
  settlement" intrabar cancel cannot be expressed in the per-bar 4-phase engine
  without lookahead (the pre-settlement half [S-30m,S) lies inside a holding bar that
  started before the flag is known at S-1h; `sleeve_fill_size(i,a,r,f)` is per
  decision bar, not per fill minute). The causal implementable half is the holding
  bar STARTING at flagged S ([S,S+4h), decided at/after S when the flag at S-1h is
  known): W1 dip tilt(i,a)=0 on those bars for that coin (covers [S,S+30m] plus the
  rest of the bar — conservative, wider than 30m but causal); exits of already-open
  rungs unchanged (engine handles). W2 dip tilt = 1.0 everywhere.
- Expected gate rate (IDEAS5 prior: ~30-60 events/yr market-wide): reported per
  coin-year and market-wide, not selected on.

## Data (read-only, never edited)

- Funding: `data/raw/binance_premium_20260928/{BTC,ETH,SOL,BNB,XRP}USDT_funding.parquet`
  (calc_time settlement, last_funding_rate; 2020-01..2026-08-31 16:00 UTC; SOL from
  2020-09-13, BNB from 2020-02-10). Premium 1m: same folder
  `{SYM}_premium_1m.parquet` (open_time, close = premium index decimal; to
  2026-09-26 23:59). Premium bars starting at/after 2026-09-24 00:00 UTC dropped.
  No other 1m data loaded (no majors/btc/alts intraday klines). One coin at a time,
  close column only, float32.
- Coverage rule: if the named data does not cover an anchor norm window (<50 pool
  settlements for a coin-year), disclose and never flag that coin that year (never
  impute). All five norm windows [A-97d,A-7d) are expected covered (SOL/BNB series
  start 2020; funding ends 2026-08-31 so Y4 settlements after 2026-08-31 have no S
  and are never flagged — disclosed, gate naturally off).
- Books/opens: engine's own `eu.er.v154_books()` + `forward_v205.research_books_d2`
  (same as v426/spillgate/vpinveto); no 1m except the engine's own minute cube.

## Engine (fixed; per-(T,sym) book-multiplier copy of vpinveto/spillgate mechanism)

- v414 pipe v321, corr-aware inv sizes kd=1.7, bear books built EXACTLY as v421
  (`btc = _opens_std["BTCUSDT"].reindex(books154.index)`,
  `bear = (btc < btc.rolling(1200, min_periods=600).mean())`,
  `sb.loc[bear] = sb.loc[bear].where(sb<=0, sb*0.5)`), risk budget 0.26*1*1.7,
  sleeve_gross_cap G=2.0, win_start=5, gate costs inside the engine (maker 0.0002,
  taker 0.00055, longs pay 0.0001/8h, shorts 0; limit fill only on 1m trade-through;
  nothing in first 5 min after a 4h close; stop-first in shared 1m bar — engine handles).
- Gate applied AFTER the bear filter, BEFORE the shifted-clock forward fill, on the
  standard grid with causal asof (latest gate T <= book T; same ffill as v426).
- Rows run through the engine (ONLY these three): REF, W1, W2.
- Stages: stage dev runs [DEV0=2021-09-24, DEV1=2025-09-24) for the three rows
  (REF first; must reproduce v421 G2 years 0..3 R/DD to the digit, else STOP).
  Stage last runs [DEV0, Y1=2026-09-23) ONCE for REF + the dev4 robust pick ONLY
  (every Y4 number labelled scored-once; REF Y4 must reproduce v421 G2 Y4 to digit).
  No re-runs after seeing outcomes; any change becomes a disclosed extra row.
- Long jobs: `nohup ... > tmp/<log> 2>&1 &` + poll the log; heartbeat every 600 s.

## Metrics / selection (fixed)

- Gate costs as above (inside engine).
- Per-year 4-phase reset %/mo + DD via `reset_metric.year_reset`; dev4 geo mean,
  W (worst-year R), max yearly DD, losing count; 5y geo mean (years 0..4 on stage-last
  runs); full-path DD via `v388.mix` equal-1/4 mix from 2021-09-24 (max of reset DDs
  and full-path for the gate); pooled book/rung/all win rates + fills/year + gated
  share of (T,sym) rows + sized mean book multiplier (same collection as
  oc_vpinveto/run_engine.py; W2 dip mult reports 1.0).
- Robust pick on dev4 ONLY among W1/W2 (REF is baseline): eligible iff DDmax <= 20
  and no losing dev year; prefer dev4 mean >= 5 %/mo, then highest dev4 WORST-year
  monthly return, ties -> higher mean. (If none eligible, pick = "none-eligible" and
  the last stage runs REF only.)
- G2 baseline to reproduce (v421_result R2B1D17BFG2): dev
  [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27)], Y4 (4.648/12.90),
  5y 5.410, full-path DD 16.82. Reproduce REF to the digit first, else STOP.

## Leakage / checks (stated in REPORT)

- Feature timing (premium bars ending <= S-60m only; P(S) timestamped S-1h; gate at
  T=S uses only data <= S-1h < T; truncation-tested in tests/test_oc_fundclock.py);
  label windows (no labels fit; thresholds are unsupervised quantiles); fit windows
  (q90 from [A-97d,A-7d) per anchor-coin, 7d embargo, frozen per year, no statistic
  from any test year feeds any choice); fill timing (win_start=5 + 1m trade-through +
  stop-first, engine). Gate costs inside the engine.
- No statistic from any test year feeds any choice. All five years were available
  when scored; findings need prospective validation.

## Compute plan (heavy_slot, resume-safe)

- `fund_rule.py`: pure helpers (`premium_twap_before`, `gate_flag`, `anchor_of`) —
  no data access; unit-tested.
- `compute_fund.py`: one coin at a time (premium 1m close float32) -> P(S) per
  settlement -> per-anchor q90 (JSON) -> gate table `gates_std.parquet` {(T,sym):
  gate} + `thresholds.json`. CPU-only; via heavy_slot (1m RAM > 0.4 GB).
  Resume-safe per-coin caches in tmp/.
- `check_g2.py`: f=0-style reproduction assert (v421_runs.pkl + reset_metric) to digit.
- `run_engine.py`: sequential shifts per stage, heartbeat every 600 s, caches
  `tmp/runs_dev.pkl` / `tmp/runs_last.pkl` (resume-safe). Via heavy_slot, one job,
  nohup + log.
- `analyze.py`: CPU-only scoring of stage-dev (reset metric + v388.mix + wins) ->
  `tmp/dev_table.json`; `analyze_last.py`: stage-last ONCE (pick + REF) ->
  `tmp/last_table.json` (+ 5y means + full-path DD).
- Deliverables: PLAN.md (this file), fund_rule.py, compute_fund.py, check_g2.py,
  run_engine.py, analyze.py, analyze_last.py, results.json, REPORT.md,
  tests/test_oc_fundclock.py (>=1 causality/truncation test + >=1 hand-checked
  synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_fundclock.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the
  original row stays and the change is a disclosed extra row.)
