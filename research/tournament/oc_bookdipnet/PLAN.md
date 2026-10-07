# oc_bookdipnet PLAN (pre-registered BEFORE any outcome is computed, 2026-10-05)

Implements idea #19 ("book/dip long-overlap guard") EXACTLY as described in
`docs/opencode/OPENCODE_W_oc_bookdipnet.md`. This PLAN is written before any
guard outcome is computed. Single fixed rule, no fitted parameter.

## Hypothesis

In crashes the dip sleeve and the book are BOTH long the same coins, so losses
add (oc_ddanat17: FTX Nov-22 combines book-long and dip losses; the 2023-04/06
episode combines book-long and dip losses on BNB/ETH). Halving a coin's book
LONG target while >= 2 average dip rungs of that coin are open (filled in the
previous bar, still open) should cut the combined (book + dip) drawdown path at
small yearly-P&L cost, because the guard fires only on a small minority of
coin-bars.

## Inputs (read-only, never edited)

- Engine replica event stream of R2B1D17BF phase s=0 (shift 0):
  `research/tournament/oc_ddanat17/{events_s0.parquet, rungs_s0.parquet,
  raw_s0.pkl}` produced by `run_ddanat17.py` (exact v411 worker replica:
  dips x1.7 inv-rule, budget 0.26x1.7, bear-book filter longs x0.5, R2 agents,
  v216 grid trade policy, win_start=5). Live 2021-09-24..2026-09-23 (+12h mix
  end); 1m read to 2026-09-24 00:00 UTC.
- 4h books only for the book-target sign (no 1m data): `research_books_d2`
  rebuilt EXACTLY as `scripts/forward_v205.py` (same files, same math as
  oc_bookbrake: `o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2`, `d2 = 0.8*o1 +
  0.2*(D+Dq)/2`, union index, missing -> 0.0) from
  `artifacts/research/engine_real/`; bear filter EXACTLY as `run_ddanat17.py`:
  rows where BTCUSDT standard 4h open (`opens_v154.parquet`) < rolling-1200
  mean (min 600) have positive entries x0.5.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment override of
  the tournament-harness dev cutoff; all five years are research data,
  findings still need prospective validation).
- LIGHT job: one process, RAM < 1 GB, no 1m data. Only `raw_s0.pkl` (attrib),
  `rungs_s0.parquet`, and small 4h parquets are loaded.

## Exact causal definitions (fixed now, before seeing numbers)

- Clocks. Attrib bar start `B` = `attrib[t]` times from `raw_s0.pkl`
  (= holding-bar start = decision idx + 4h; the replica's `idx` equals the
  `books154` 4h index for shift 0). Previous bar = `[B-4h, B)`. All
  timestamps are UTC.
- Book P&L per coin-bar (reconstruction, exact — NOT the vectorised
  fallback). `raw_s0.pkl` attrib rows are `(t, per-asset book PnL array,
  sleeve PnL)` in fractions of bar-start equity, appended per live bar by
  `engine_user.simulate` (`asset_pnl[a] = end_val - qa*o1 - fund`, i.e. NET of
  book fees and book funding; `sleeve_pnl` NET of rung fees). Column order is
  `books154` order `[BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT]`.
  So base book P&L of coin `c` in bar `B` = `abook[j, a(c)]`, base dip P&L of
  bar `B` = `asleep[j]`, base combined net of bar `B` = `sum_a abook + asleep`
  (compounds to the replica equity up to linear-vs-compounding residuals;
  cross-checked against `raw_s0.pkl` eq). Because attrib IS the engine's own
  per-coin-bar book accounting, the assignment's fallback (vectorised
  `research_books_d2` open-to-open P&L with 0.05%/turnover) is NOT used.
- Book LONG target sign for bar `B`. `tgt_c[B]` = bear-scaled `d2` value for
  coin `c` ffilled at `B-4h` (the decision close whose holding bar starts at
  `B`; equals the replica's `books_bear` row `B[i]` since `idx ==
  books154.index` for shift 0). Long iff `tgt_c[B] > 0` strictly; shorts
  (`< 0`) and flat (`== 0`, tolerance 0) are never scaled. Target signs are
  known at/before `B` (decided at `B-4h`), hence causal.
- Dip average rung weight (fixed scale, disclosed). `avg_c` = mean `weight`
  over ALL rungs of coin `c` in `rungs_s0.parquet` (full 5y, fixed constant;
  weights are sizing units in fractions of bar-start equity, not fitted to
  returns). Threshold `thr_c = 2 * avg_c` (i.e. "2 average rungs open").
  Full-sample mean is a fixed unit conversion; the overlap sum itself is
  strictly causal (see next). A causal expanding-mean sensitivity is reported
  as a side row only (not the decision).
- Overlap open weight (strictly causal, observable live at `B`). For coin
  `c` and bar start `B`: `openW_c[B] = sum of weight` over rungs of coin `c`
  with `fill_t in [B-4h, B)` AND `exit_t > B` (filled in the previous holding
  bar and still open at `B`). Fill times and the open inventory at `B` are
  both known at `B`; no future information is used. Rung `fill_t`/`exit_t`
  come from `rungs_s0.parquet` (paired fill->exit from the engine event
  stream).
- GUARD (single fixed rule, no parameter). At bar start `B`, for each coin
  `c`: if `openW_c[B] >= thr_c` AND `tgt_c[B] > 0` then that coin-bar is
  guard-on and its book LONG target for bar `B` is x0.5; otherwise unchanged
  (shorts/flat never scaled). Guard state uses only information known at `B`.
- Guarded P&L (disclosed LIGHT approximation, no re-simulation). Guarded book
  P&L of a guard-on long coin-bar = `0.5 * abook[j, a(c)]` (halving the target
  halves both gross and its fees/funding proportionally; discrete
  fill/min-notional/stop non-linearities are ignored — disclosed as an
  approximation of the true re-simulated guard). All other coin-bars keep base
  book P&L. Dip sleeve P&L is unchanged (`asleep[j]`). Guarded combined net
  per bar `n_guard[j] = book_guard_total[j] + asleep[j]`; base `n_base[j] =
  book_base_total[j] + asleep[j]`.
- Anchor years. `A_k = 2021-09-24 .. 2025-09-24`, `A_5 = 2026-09-24`. Year `k`
  = bars with bar-start `B in [A_k, A_{k+1})` (as in oc_bookbrake; the 2023
  year holds 2196 bars, the rest 2190, covering all attrib bars once).
- Per (variant, year) on year bars, equity rebased to 1.0 at the year start:
  compounded equity `eq[j+1] = eq[j]*(1+n[j])` (weights are fractions of
  equity). Combined SUM = compounded yearly net `prod(1+n)-1` (linear sum
  `sum(n)` reported alongside). Combined daily path: 4h equity resampled to
  UTC-date closes (last bar of each date); maxDD = `max(1 - eq_d/running-peak)`
  on daily closes; worst day = min daily net `prod(1+n over the date's
  bars)-1`. Book-long P&L = linear sums over coin-bars with `tgt_c[B] > 0` of
  base vs guarded book fractions. Guard-on coin-bars = count of `(B, c)` with
  `openW_c[B] >= thr_c` AND `tgt_c[B] > 0` (plus the overlap-only count as a
  side row).

## Decision rule (assignment-specific, fixed now)

- PROMISING only if BOTH hold on the COMBINED (book + dip) path: (a) guarded
  daily-close maxDD < base daily-close maxDD strictly (tolerance 0) in >= 4 of
  5 anchor years, AND (b) guarded combined SUM (compounded yearly net) >= base
  (not lower, tolerance 0) in >= 3 of 5 years. NaN on either side counts as
  FAIL. No LOYO (no fitted parameter). This replaces the default
  same-sign/LOO rule. One-line verdict in REPORT.md (PROMISING / NOT
  PROMISING).

## Resources / constraints

- Write ONLY to `research/tournament/oc_bookdipnet/`
  (+ `tests/test_oc_bookdipnet.py`). No commits, no edits outside these paths.
- One process; only `raw_s0.pkl` + `rungs_s0.parquet` + small 4h parquets are
  loaded. No 1m data.

## Outputs

- `research/tournament/oc_bookdipnet/`: PLAN.md (this file),
  `compute_bookdipnet.py`, `results.json`, REPORT.md (tables + one-line
  verdict). No tuning on results; any post-hoc change logged in REPORT.md.

## Post-hoc log

- 2026-10-05 (after seeing the STRICT rule fires 0 times, before seeing any
  guarded P&L): added a disclosed extra variant with `exit_t >= B`
  (inclusive boundary — keeps the 2422 rung_timeouts that exit exactly at the
  B open). Reason: max rung lifetime is 224m < 240m holding bar and every
  timeout exits exactly on a B, so NO rung is ever strictly open across a
  holding-bar boundary (the dip sleeve is flat at every B); the strict rule is
  degenerate by construction. The inclusive variant (a dip-timeout brake, not
  true simultaneous exposure — the just-closed rungs earn nothing during bar
  B) is reported as `decision_inc` alongside the pre-registered `decision`;
  the one-line verdict follows the pre-registered strict rule. No parameter
  was fitted or changed (still x0.5, still >= 2 average rungs).
