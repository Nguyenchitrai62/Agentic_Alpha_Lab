# oc_bookoffset — PLAN (pre-registered BEFORE any outcome is computed)

Implements idea #32 ("volatility-scaled book entry offset") EXACTLY as described
in `docs/opencode/OPENCODE_W_oc_bookoffset.md`. This PLAN is written before any
fill/P&L outcome is computed. One fixed rule, no fitted parameter.

## Hypothesis

Book entries rest 60 minutes at a FIXED 10 bps better than the minute-0 price.
A fixed offset is too shallow in high-volatility bars (adverse selection, fills
right before the move continues) and unnecessarily deep in quiet bars (missed
fills that would have earned the holding-bar drift). Posting at
`offset = 0.10 x sigma4h` of the coin (clipped to [5, 40] bps) should keep the
fill rate roughly constant across volatility regimes while improving the average
entry price on filled entries, so total book P&L (filled entries to the episode
end, net of maker entry fees) is higher than the fixed 10 bps rule in most
anchor years.

## Inputs (read-only, never edited)

- Books: `research_books_d2` rebuilt EXACTLY as `scripts/forward_v205.py`
  (`o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2` with A=`member_A_O1_orders`,
  Aq=`member_Aq_O1_orders`, B=`member_B_tv`, Bq=`member_Bq_tv`;
  `d2 = 0.8*o1 + 0.2*(D+Dq)/2` with D=`members_v154[D]`,
  Dq=`members_quarterly_D`; union index, missing -> 0.0) from
  `artifacts/research/engine_real/` (same files, same math as oc_bookvol).
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens).
- 1m data (majors, one coin at a time, float32): BTC from
  `data/raw/btc_intraday_20260924/klines_1m_20*.parquet`, ETH/SOL/BNB/XRP from
  `data/raw/majors_intraday_20260924/<SYM>_1m_20*.parquet`
  (columns open_time, open, high, low, close).
- Symbols: BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides the
  old tournament-harness dev cutoff; all five years are research data, findings
  still need prospective validation).
- MEDIUM job: one process, one coin at a time, 1m high/low/open held as
  float32 for the coin in process only (RAM < 3 GB).

## Exact causal definitions (fixed now, before seeing numbers)

- BOUND = 2026-09-24 00:00 UTC. Decision grid = inner join of books_d2 index
  with opens_v154 index (dropna all), sorted 4h. Decision `t` has target weight
  `w_c[t]` (signed fraction of equity, known at the close of bar `t`).
  Holding-bar open `T = t + 4h`, exit `X = T + 4h`. Scored decisions satisfy
  `T in [2021-09-24, BOUND)` and `X <= BOUND` (episode fully observed), so the
  last scored `T = 2026-09-23 20:00` (`X = BOUND`).
- Minute-0 price `P0_c[T]` = 1m open at minute 0 of the holding bar
  (`open_time == T`), fallback to the 4h open `O_c[T]` if the minute-0 1m row
  is missing. `P0` is known at `T`. Exit price `PX_c[T]` = 4h open `O_c[X]`
  (next 4h open, known only at `X`).
- sigma4h (known at the bar open, strictly before `T`): let `O_c` be the 4h
  open series, `R_c[s] = O_c[s]/O_c[s-4h] - 1`. Then
  `sigma4h_c[T] = std(R_c[T-360*4h .. T-4h])` (360 returns ending at `T-4h`,
  ddof=1, min_periods 120), i.e. `O.pct_change().rolling(360,
  min_periods=120).std().shift(1)` evaluated at `T`. Uses only opens `<= T-4h`
  `< T`, hence known at the decision time and at `T`. Cold-start NaN (not
  expected: opens start 2017, grid starts 2021) falls back to fixed 10 bps for
  the vol rule (disclosed).
- Offsets (fractions, 1 bps = 1e-4):
  `off_fix = 0.001` (10 bps).
  `off_vol_c[T] = clip(0.10 * sigma4h_c[T], 0.0005, 0.004)` ([5, 40] bps).
  Limit: buy (`w_c[t] > 0`): `L = P0*(1-off)`; sell (`w_c[t] < 0`):
  `L = P0*(1+off)`. "Better than minute-0" by construction.
- ENTRY EVENTS (from-flat simplification, disclosed): every scored
  `(coin c, decision t)` with `|w_c[t]| >= 1e-12` (non-flat target) and finite
  `P0`, finite `PX`, and a usable 1m window (see below) is one entry attempt
  under BOTH rules (same attempted set, so fill-rate differences come only
  from the offset). Rationale: the simplified engine starts each bar flat
  (`unfilled -> no position until the next decision`), so each non-zero target
  is attempted from flat; carry, adds/reduces, SL/TP, governor, vol target and
  min-notional are IGNORED to isolate the offset effect (no re-simulation).
  Flips vs continuations are not distinguished (sensitivity: per-trade
  entry-only would have an order of magnitude fewer events; rejected before
  seeing outcomes for power reasons).
- 1m window: holding-bar 1m lows `Lo[m]`, highs `Hi[m]`, `m = 0..239`
  (`m` = minutes since `T`). Missing minutes are forward-filled within the bar
  from minute 0 (as the engine cube does); if minute 0 itself is missing the
  event is unscored (reported under coverage). If more than 10 of the 60
  window bars are originally missing, the event is unscored. Fill window =
  minutes `[5, 65)` (Python slice `5:65`, 60 bars, resting 60 minutes from
  minute 5, no fill in the first 5 minutes for pipeline latency, as the user
  rule and the assignment's `5..65`).
- FILL (strict trade-through, `ft = 0`, as the engine default): buy fills iff
  `min(Lo[5:65]) < L`; sell fills iff `max(Hi[5:65]) > L`. Touch (`==`) does
  NOT fill (no queue position from OHLC). Fill price = `L` (maker), fill minute
  = first `m` in `[5,65)` satisfying the condition (diagnostic only).
  Unfilled -> no position, actual P&L 0 until the next decision, as the engine.
- Episode & P&L (one holding bar): episode = `[T, X)`, end = next 4h open.
  For a FILLED attempt with signed weight `w = w_c[t]`, limit `E = L`:
  `gross = w*(PX/E - 1)` (signed; long gains when `PX > E`, short when
  `PX < E`); `net = gross - |w|*0.0002` (maker 0.02% on the entry notional,
  gate cost model; exit at mid with no fee, same for both rules — disclosed).
  For a MISSED attempt actual P&L = 0; hypothetical missed P&L
  `hyp = w*(PX/P0 - 1)` (minute-0 entry, no fee) is reported to diagnose
  selection (whether a rule misses winners or losers). Total book P&L per
  (rule, year) = linear sum of `net` over filled events in the year (fractions
  of equity; compounded `prod(1+pn)-1` reported as a side row — ranking
  identical at these magnitudes).
- Entry improvement (bps, filled only): `side*(P0-E)/P0*1e4 = off*1e4`
  (fill at the limit, so improvement equals the posted offset by construction;
  the comparison is mean posted-vs-filled offset plus fill-rate tradeoff).
- Anchor years (assignment literal): `A_k = 2021-09-24 .. 2025-09-24`,
  year `k` = holding-bar opens `T in [A_k, A_k+365d)`. The 2023 year
  (`2023-09-24..2024-09-23`) leaves 6 bars (`2024-09-23..2024-09-24`) orphaned
  by the leap day; orphans are counted and excluded (disclosed here before
  seeing outcomes; alternative partition `[A_k,A_{k+1})` would assign them to
  2023 — sensitivity reported as a side row only if trivial to compute, not
  part of the decision).
- Per (rule, year): attempted N, filled N, fill rate, mean attempted offset
  (bps), mean filled offset (bps) = mean entry improvement, filled gross/net
  sums, missed hypothetical sum, total net book P&L (decision metric),
  compounded year return (side row), coverage (unscored share).

## Decision rule (assignment-specific, fixed now)

- Effect per year: `d_k = total_net_vol_k - total_net_fix_k` (vol minus fixed;
  positive = vol-scaled better). NaN on either side counts as FAIL.
- LOYO stability (descriptive, from the default rule): `LOYO_h` passes iff
  `sign(d_h) == sign(mean_{k!=h} d_k)` and that training mean is `> 0`
  (NaN -> fail).
- Variant VOL is PROMISING iff `d_k > 0` strictly (tolerance 0) in >= 4 of 5
  anchor years. LOYO `>= 4/5` is reported alongside (default-rule stability)
  but is NOT part of the verdict — the assignment's rule is book-P&L-higher
  in >= 4/5 years. One-line verdict in REPORT.md (PROMISING / NOT PROMISING).
- First-four-year (2021-2024) sensitivity is reported descriptively (repo
  selection window) but is NOT part of the verdict.

## Causality / coverage tests (tests/test_oc_bookoffset.py)

- test_fill_window_causal: shifting all 1m data at/after `X` leaves the fill
  outcome unchanged; fills use only `Lo/Hi[5:65)` of the holding bar.
- test_sigma_uses_only_bars_before_T: perturbing all 4h opens at/after `T`
  leaves `sigma4h[T]` (and hence `off_vol`) unchanged.
- test_no_lookahead_limit: limit uses only `P0` (minute-0 open) and `sigma`
  (bars strictly before `T`); synthetic hand-check: buy limit below `P0`,
  sell limit above `P0`, strict (touch does not fill).
- test_year_partition: the 5 `[A_k,A_k+365d)` masks are disjoint; per-year
  attempted N sums to scored N plus orphans; orphan count reported.
- test_results_schema: results.json has per-year attempted/filled/fill_rate,
  offsets, filled/missed/total P&L for both rules, effects `d_k`, LOYO,
  `promising` consistent with `d_k > 0` counts.

## Outputs

- `research/tournament/oc_bookoffset/`: PLAN.md (this file),
  `compute_bookoffset.py`, `results.json`, REPORT.md (tables + one-line
  verdict). No tuning on results; any post-hoc change logged in REPORT.md.
  No commits.
