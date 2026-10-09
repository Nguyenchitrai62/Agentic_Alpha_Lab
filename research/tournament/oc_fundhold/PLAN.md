# oc_fundhold — PLAN (pre-registered, FROZEN before any outcome)

Assignment: `docs/opencode/OPENCODE_W_oc_fundhold.md` (= IDEAS6 §5, rank 5) +
`docs/opencode/OPENCODE_W_COMMON_20261007.md` (+ AGENTS.md, OPENCODE_VF_COMMON.md,
`docs/opencode/IDEAS6_20261008.md` §5 read in full + CLOSED rows read in full).
Write ONLY `research/tournament/oc_fundhold/` + `tests/test_oc_fundhold.py`.
Engine / heavy 1m work via `scripts/heavy_slot.py` (one job at a time, one coin at
a time where 1m is touched, float32). Heartbeat print every 600 s in long jobs.
Progress print every ~10 min. Scratch only under `research/tournament/oc_fundhold/tmp/`.
GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/rm/commit/switch/rebase/merge.
No orders, no authenticated endpoints, no Kaggle uploads. No inspection outside the
workspace (no /proc, no system temp).

## Why (IDEAS6 §5, rank 5)

Gate funding is adverse-flat (longs pay 1 bp per 8h settlement held, shorts pay
nothing): extending a LONG dip timeout through an expensive funding settlement is
uncompensated bleed, while SHORT holds are free. CLOSED rows read: `oc_holdext`
(unconditional +4h hold of every non-TP timeout: NOT PROMISING, sum 1/5 + DD 1/5 —
exit at the next open stands) and `oc_condhold` (in-profit-only +4h hold:
NOT PROMISING, sum 3/5 + DD 1/5) — both hold WHEN unconditionally or on profit;
`oc_fundclock` (flatten book longs x0.5 into p90-PREDICTED settlements + dip cancel:
W2 dev4 +0.56 mean / DD -1.7 but clean year -0.16, FAILS gate (b); dip-cancel leg
worthless) — flatten on predicted level into the clock. This idea EXTENDS the dip
timeout only when the last SETTLED funding is cheap (bleed avoids expensive
settlements), signals frozen, maker-first exit with taker fallback, max one skip.
Kept per the IDEAS6 near-duplicate note.

## Variants (exactly two + base reference, no others)

- BASE = D0 replica timeout at the next 4h open (holdext-exact: TP 1.0sg maker,
  close5 stop 4sg / backstop 8sg taker, timeout at o2 taker + funding if settling).
- V1 = at a BASE timeout: if LONG and last settled funding > trailing-90d p70
  -> exit on time (V1 outcome = base); else extend the resting TP/stop one skip
  (+8h = two 4h bars, minutes 240..719, same frozen sl/bl/tp, maker-first TP with
  taker fallback, max one extension, timeout at o4 = open T+720 taker).
- V2 = same rule at trailing-90d p50.
- "F1 long" in IDEAS6 is read as "If long" (funding bleed applies to longs; shorts
  are free). The replica fills are dip LONGS only, so the rule reduces to:
  expensive-funding long timeouts exit on time, cheap-funding long timeouts extend.
  Book SHORT holds (always extend per the mechanism) are out of replica scope —
  disclosed; no book-short effect is claimed because the 4-phase engine is run ONLY
  if a variant passes the replica + placebo gate (see below).
- Frozen numbers (never fit): trailing-90d window, 7-day embargo, p70 (V1) / p50
  (V2) strict `>`, +8h = two bars, max one extension, no re-peg. All round numbers
  from IDEAS6, frozen ex-ante.
- G2 reference (R2B1D17BFG2, v421: dev [(2.588/10.86),(3.282/16.91),(6.045/15.81),
  (10.677/8.27)], Y4 (4.648/12.90), 5y 5.410, full-path DD 16.82) is COPIED labelled
  context only; `check_g2.py` reproduces it to the digit from `v421_runs.pkl` +
  `reset_metric` before any outcome is scored (CPU-only, no 1m).

## Settled-funding condition (exact causal definition, frozen)

- Funding: `data/raw/binance_premium_20260928/{BTC,ETH,SOL,BNB,XRP}USDT_funding.parquet`
  (`calc_time` settlement wall time with ms offset, `last_funding_rate` settled rate;
  2020-01..2026-08-31 16:00 UTC; SOL from 2020-09-13, BNB from 2020-02-10).
- Last settled funding at a BASE timeout Verd: F(T_out, sym) = `last_funding_rate`
  of the latest settlement row of coin sym with `calc_time` STRICTLY before the
  timeout open T_out = T+240 (the base exit open). Strict `<` is causal: a settlement
  stamped at the same minute (00/08/16:00:00.001) settles 1 ms AFTER the 4h open and
  is not yet known at the open. NaN when no prior settlement (data start / after
  2026-08-31) -> exit on time (never imputed).
- Thresholds per anchor A in {2021-09-24, ..., 2025-09-24} and coin sym: pool =
  {settled `last_funding_rate` : calc_time in [A-97d, A-7d)} (90 days ending 7d
  before the anchor; 7d embargo; strictly previous data only). q70[A,sym] = 70th
  percentile, q50[A,sym] = 50th percentile (linear interpolation, numpy default).
  Require >= 50 settlements in the pool else q = NaN and that coin-year NEVER
  extends (exit on time, disclosed skip, never imputed). Year y=[A, A+365d) uses its
  anchor's q on all bars. No test-year statistic feeds any threshold.
- Expensive iff finite F and finite q and F > q (strictly greater); NaN either side
  -> exit on time. V1 uses q70, V2 uses q50.

## Replica (holdext-exact single-phase + conditional +8h leg; frozen)

- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- 1m klines: `data/raw/btc_intraday_20260924` (BTC),
  `data/raw/majors_intraday_20260924` (others). Minutes used: t in
  [2020-08-01, 2026-09-24 00:00] UTC. Missing minutes (NaN) never fill, never
  trigger an exit touch, never count as flushing.
- Single 4h grid (holdext-exact, phase 0 only): bars from START = 2020-08-01 00:00
  UTC, 240-minute bars; only bars with open T in [2021-09-24, 2026-09-24) traded
  (5 anchor years Y0..Y4 keyed by T). One coin at a time in RAM (float32 O/C/H/L;
  all-five-coins O/C float32 for the n detector); RAM < 3 GB.
- sigma_4h(T): simple returns r_b = O_b/O_{b-1} - 1 of 4h bar opens; sigma = std
  (r over 360 bars ending at T-1, min_periods 120, ddof=1) = v293/oc_dipexit/
  oc_holdext definition. Known at the bar open T. Bars with non-finite O, sg <= 0
  or NaN skipped.
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths). Level lv = O(T)*(1-k*sg(T)).
- Correlation count at live minute m (offsets 16..238, holdext-exact): n = number of
  OTHER majors with finite O(T), C(T+m-1), sg(T) > 0 AND C(T+m-1) <= O(T)*(1-2.5*sg).
  Fill at FIRST offset f in 16..238 with low(T+f) < lv (STRICT trade-through) at px
  = lv, maker 0.0002. At most one fill per (bar, coin, k). w = 1/(1+n_fill) (B1).
- BASE exits D0 (holdext `outcome_base` exact): sl = px*(1-4sg), bl = px*(1-8sg),
  tp = px*(1+1.0sg); minutes f+1..239 then timeout at 240 (o2 = open T+240):
  backstop (low <= bl) at min(bl,open) taker; else TP (high > tp STRICT) at tp
  maker; else close5 stop ((m+1)%5==0, first close <= sl) at open(m+1) (or o2)
  taker; else timeout at o2 taker + 0.0001 if (T+4h).hour in (0,8,16). Stop-first:
  backstop wins ties, TP only if strictly earlier than stop, same-minute stop+TP ->
  stop. Fees: fill maker 0.0002; TP leg maker (2*maker total); stop/backstop/time
  legs taker 0.00055. Net returns are fractions of px.
- EXTENDED leg (+8h = minutes 240..719, `outcome_ext8_phase`): runs IFF base how ==
  "time" AND the funding rule says extend (cheap/NaN-safe per above; expensive ->
  base). Same frozen sl/bl/tp; clock (t+1)%5==0 on absolute offsets continues the
  wall grid; same stop-first priority; same per-leg fees. Funding (longs pay 0.0001
  per 8h settlement held): every extended exit held through T+240 pays 0.0001 if
  (T+240).hour in (0,8,16); exits at offset >= 480 additionally pay 0.0001 if
  (T+480).hour in (0,8,16); timeouts at o4 = open T+720 additionally pay 0.0001 if
  (T+720).hour in (0,8,16) (0, 1, 2 or 3 x 0.0001 total). Base intrabar exits pay no
  funding (unchanged); base timeout/stop-at-240 pay the mid fund exactly as before.
  Timeout at o4 is taker (market at the open, gate taker 0.00055). Maker-first (Idea
  1) would only SAVE fees vs this taker fallback, so the taker assumption is
  conservative and compliant (timeout exits are market/taker per the gate; entries
  are limits, stops market-taker, TPs limit-maker; live window starts at 16 > 5 so
  the minute-5 ban holds; resting TP/stop legs are not new orders).
- Kept fills (PAIRED across three arms): a fill is kept iff its BASE, V1 and V2 nets
  are ALL finite. Year key = bar-open anchor year; daily sums per arm per year group
  w*y by each arm's own EXIT date; maxDD of the cumulative daily-sum path from 0;
  win = fraction y > 0 strictly; timeout share = fraction exiting as "time".
- Coverage: settlements after 2026-08-31 have no F (funding feed ends) -> exit on
  time (gate naturally off); pools < 50 -> that coin-year never extends. Disclosed,
  never imputed.

## Gate + engine staging (fixed, per assignment)

- Replica + placebo gate FIRST (binding, dip-side rule): per year Y0..Y4 on
  single-phase w*y sums: PASS_sum(Y) iff S_V(Y) > S_BASE(Y) STRICTLY; PASS_dd(Y)
  iff DD_V(Y) <= DD_BASE(Y) (not worse; equal passes). PROMISING iff (a) PASS_sum
  in >= 4/5 years AND (b) PASS_dd in >= 4/5 years AND (c) dSum5y = sum_Y S_V -
  sum_Y S_BASE >= +0.273 (pooled placebo p95, `oc_placebo_dip`; same w*y units —
  disclosed application to single-phase sums). LOO sign stability reported.
  The 4-phase engine is run ONLY for variants passing all three legs. If neither
  V1 nor V2 passes, STOP with no engine (clean gate failure is a valid result per
  IDEAS6). G2 engine numbers stay COPIED labelled context (check_g2 reproduction).
- If a variant passes (not expected; IDEAS6 prior ~0 +-0.04, holdext 1/5, condhold
  3/5+1/5): stage dev runs [DEV0=2021-09-24, DEV1=2025-09-24) for REF + passing
  variants (REF first; must reproduce v421 G2 years 0..3 R/DD to the digit, else
  STOP), then stage last runs [DEV0, Y1=2026-09-23) ONCE for REF + the dev4 robust
  pick only (robust pick on dev4 ONLY: eligible iff DDmax <= 20 and no losing dev
  year; prefer dev4 mean >= 5 %/mo, then highest dev4 WORST-year monthly return,
  ties -> higher mean; every Y4 number labelled scored-once). Engine mechanism =
  exact copy of oc_fundclock/run_engine.py (= v414 pipe v321, corr-aware inv sizes
  kd=1.7, bear books, risk budget 0.26*1*1.7, sleeve_gross_cap G=2.0, win_start=5,
  gate costs inside) with the frozen funding rule applied to dip timeout holds
  (cheap -> hold +8h maker-first/taker-fallback max once; expensive -> exit on
  time). No re-runs after outcomes; any change becomes a disclosed extra row.

## Metrics / report (fixed)

- Gate costs inside replica outcomes (maker 0.0002, taker 0.00055, longs 0.0001 per
  8h settlement held, shorts 0; strict trade-through; live from 16; stop-first).
- Replica per-year tables (BASE/V1/V2: n, mean, win, sum w*y, timeout share, worst
  day, maxDD, efficiency), dSum per year + dSum5y, fee/funding split (aggregate
  w*fee and w*fund per arm from frozen per-leg fees + settlement flags), extension
  rate (share of base timeouts extended per variant-year) + threshold table
  (q70/q50 per anchor-coin, pool sizes, gated share).
- check_g2 reproduction (v421_runs.pkl + reset_metric + v388.mix: dev + Y4 + 5y
  5.410 + full-path DD 16.82 to the digit, asserted in-script).
- If engine runs: per-year 4-phase reset %/mo + DD via `reset_metric.year_reset`;
  dev4 geo mean, W, max yearly DD, losing count; 5y geo mean; full-path DD via
  `v388.mix` from 2021-09-24; pooled book/rung/all win rates + fee/funding split
  from engine events. If engine does not run: state so with the gate numbers.
- Leakage checklist in REPORT (feature timing, label windows, fit windows, fill
  timing). All five years were available when scored; findings need prospective
  validation. Finish with a 3-line Vietnamese verdict (adopt / reject / needs
  prospective evidence) + `results.json` next to REPORT.md.

## Compute plan (heavy_slot, resume-safe)

- `fund_rule.py`: pure helpers (`last_settled_before`, `anchor_of`,
  `quantile_pool`, `expensive_flag`) — no data access; unit-tested.
- `fundhold.py`: pure-numpy core (vendored holdext-exact `n_vector`, `find_fill`,
  `outcome_base`, `outcome_ext8_phase` for minutes 240..719 with mid1/mid2/final
  funding, `outcome_conditional` = base-or-extended per the frozen funding rule).
- `compute_funding.py`: per-coin settled funding only (no 1m) -> per-anchor q70/q50
  JSON + `thresholds.json`. CPU-only; via heavy_slot if > 0.4 GB (else direct).
- `check_g2.py`: f=0-style reproduction assert to the digit (CPU-only, no 1m).
- `run_replica.py`: single-phase coin loop (float32, one coin at a time, heartbeat
  every 600 s), paired ledger + exit-day sums -> `results_replica.json` (+ resume
  cache in tmp/). Via heavy_slot, one job, nohup + log.
- `analyze_replica.py`: CPU-only gate scoring (PASS_sum/DD legs + dSum5y + LOO +
  fee/funding split + extension rates) -> `results.json` input.
- Engine files (`run_engine.py`, `analyze.py`, `analyze_last.py`) are created ONLY
  if a variant passes the gate (same shape as oc_fundclock; REF reproduction first).
- Deliverables: PLAN.md (this file), fund_rule.py, fundhold.py, compute_funding.py,
  check_g2.py, run_replica.py, analyze_replica.py, results.json, REPORT.md,
  tests/test_oc_fundhold.py (>=1 causality/truncation test + >=1 hand-checked
  synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_fundhold.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the
  original row stays and the change is a disclosed extra row.)
