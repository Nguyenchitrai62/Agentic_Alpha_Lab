# oc_skewbook — PLAN (pre-registered BEFORE any outcome is computed)

## Hypothesis

Deribit options skew (OTM put IV minus OTM call IV) and the put-buy share
measure crash-hedging demand. As BOOK context for the deployed BOT book
(`forward_v205.research_books_d2`, a slow momentum book): in high-skew bars
the book's near-term gross P&L is worse (it leans into the falling knife /
gets squeezed on relief rallies), so conditioning the book on skew (flatten
or shrink when skew is high) could cut drawdowns. Put-buy share is a
secondary, volume-based context variable for the same mechanism.

## Inputs (read-only, never edited)

- Books: `research_books_d2` rebuilt EXACTLY as `scripts/forward_v205.py`
  (same formula/files as `research/tournament/oc_bookic/compute_bookic.py`).
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens).
- Options: `data/raw/deribit_opt_20260926/BTC_options_4h.parquet` (primary)
  and `ETH_options_4h.parquet` (secondary diagnostic only).
- Bar convention (from `research/mj/fetch_deribit_options_4h.py`): an options
  row labelled `bar = T` aggregates taker trades with timestamps in
  `[T, T+4h)`; `iv_otm_put`/`iv_otm_call` are notional-weighted mean IVs of
  OTM puts (strike < index) / OTM calls (strike > index), expiry <= 60d.
- Symbols: BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides the
  tournament-harness dev cutoff; all five years are research data, findings
  still need prospective validation). No 1m data is used.

## Exact definitions (fixed before seeing numbers)

- Grid: inner join of books index with opens index, sorted 4h grid, kept at
  decision times `t < 2026-09-24 00:00 UTC`. Index `t` is the bar open time;
  bar `t` covers `[t, t+4h)`; weight `w[t]` is known at the close of bar `t`
  (i.e. at time `t+4h`, the price `open[t+1]`).
- Skew feature (causal): `skew[t]` = `iv_otm_put - iv_otm_call` of the last
  COMPLETE options bar as of the decision at `t+4h`, i.e. the options row
  with `bar == t` (trades in `[t, t+4h)`, all timestamped before the
  decision). Implementation: `merge_asof(backward)` of the grid on the
  options `bar`, so a missing options bar falls back to the most recent
  earlier complete bar (still strictly before the decision); bars with no
  earlier options bar at all stay NaN and are excluded from skew sorts
  (counted in coverage).
- Primary context series = BTC skew, applied to every major (BTC options are
  the only full-history market-wide gauge; SOL/BNB/XRP have no Deribit
  options series here). Secondary diagnostics: ETH skew vs ETH and BTC
  forward returns; BTC put-buy share vs every major.
- Put-buy share (causal, same bar): `putbuy[t] = put_buy / total`, where
  `total = call_buy + call_sell + put_buy + put_sell` (USD notional); 0.0 if
  `total == 0`; NaN propagates like skew when no earlier bar exists.
- Forward returns per coin: `R6[t] = open[t+6]/open[t]-1` (1 day),
  `R42[t] = open[t+42]/open[t]-1` (7 days). Rows whose forward window runs
  past available opens are dropped per-metric (so the last 6 / 42 grid bars
  have no R6 / R42); every IC reports its `n`.
- Anchor years: `A_k = 2021-09-24, ..., 2025-09-24`; year `k` = bars with
  `open_time` in `[A_k, A_{k+1})` for `k = 0..3` and
  `[A_4, A_4 + 365d)` for the last (same leap-year partition fix as
  oc_bookic: 2023-09-24..2024-09-24 spans Feb-29 2024).
- IC: per (year, coin), Spearman corr of `(skew[t], R6[t])` and
  `(skew[t], R42[t])` over bars `t` in the year with both sides available.
  Secondary: same with `putbuy[t]`; and ETH-skew versions for ETH/BTC only.
- Tercile cut-offs (causal, "from previous years"): for year `k`, `q33_k`
  and `q67_k` = 33rd/67th percentiles of `skew[t]` (BTC) over ALL grid bars
  with `t < A_k` (expanding history back to 2019; no year-k or later data).
  Year-k bars assigned: low `s <= q33_k`, mid, high `s > q67_k`. NaN skew
  bars are unassigned (excluded from tercile sums, reported as `n_nan`).
- Book P&L (gross, vectorised, no costs — same as oc_bookic):
  `pnl[t] = w[t] * (open[t+1]/open[t]-1)`, per coin. Reported per
  (year, coin, tercile) and split by leg: long (`w[t] > 0`), short
  (`w[t] < 0`); flat `w == 0` contributes 0 to both legs.
- PRIMARY effect (exactly one, fixed now): per anchor year,
  `E_y = pnl_high_y - pnl_low_y`, where each term is the year-y gross book
  P&L summed over all 5 coins AND both legs for bars in that skew tercile.
  Pre-registered sign expectation (not used in the verdict): negative —
  high skew marks fear/hedging states where a slow momentum book underperforms.
- Leave-one-year-out (LOYO): `S = sign(sum_y E_y)`; `S_{-j}` = sign of the
  sum over all years except `j`. Year `j` "holds" iff `S_{-j} == S`.

## Decision (verdict) rule — fixed now (assignment default)

- PROMISING iff (a) `sign(E_y)` is the SAME in >= 4 of the 5 anchor years
  AND (b) LOYO holds in >= 4 of 5. Otherwise NOT PROMISING.
- If PROMISING: propose AT MOST ONE rule (a skew-conditioned book gate with
  the fitted tercile cut-off logic stated walk-forward). If NOT PROMISING:
  propose NO rule.
- Per-leg splits, IC tables, ETH-skew and put-buy diagnostics are supporting
  context only and can never overturn the verdict.

## Resources / constraints

- Write ONLY to `research/tournament/oc_skewbook/` (+
  `tests/test_oc_skewbook.py`). No commits, no edits outside these paths.
- One process; only 4h parquets are loaded (books, opens, two options
  files); RAM << 1 GB. No 1m data.

## Post-hoc log (allowed by VF_COMMON; definition fix, before REPORT)

- 2026-10-05, bug fix (code now matches the PLAN text above; no definition
  changed): the first implementation computed tercile cut-offs over grid bars
  with `t < A_k`, but the grid starts at the first book bar (2021-09-24), so
  year 1 had `n_hist = 0`, NaN cut-offs, all 2190 bars fell in "mid" and
  `E_2021 = 0.0` by construction. Fixed to use the raw BTC 4h options skew
  history (`bar < A_k`, back to 2019-01-01) as the PLAN's "expanding history
  back to 2019" requires. Found after the initial run showed the degenerate
  `E_2021 = 0.0`.
- 2026-10-05, bug fix: leg splits used `tm & long_m[ym]` (boolean Series &
  DataFrame), which aligns the Series index against the DataFrame columns and
  silently selected nothing (all leg P&Ls were 0.0 while totals were not).
  Fixed with positional numpy indexing. Found via the same initial run
  (2021-mid total 0.3205 vs legs 0.0). Totals and E were unaffected.

## Outputs

- `compute_skewbook.py` (the single scoring script),
  `results.json` (per-year-per-coin IC + n, tercile cut-offs, pnl by
  year x tercile x leg x coin, E_y, LOYO, coverage),
  `REPORT.md` (tables + one-line verdict + at most one proposed rule).
