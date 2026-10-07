# oc_ethbtc — PLAN (pre-registered BEFORE any outcome is computed)

## Hypothesis

ETH/BTC relative strength and a BTC-dominance proxy are slow, causal
regimes: when ETH outperforms BTC (high log ETH/BTC trend) or when BTC
dominates the majors (high BTC-minus-equal-weight return), dip-buying the
majors and/or the deployed BOT book behave differently. A stable
tercile spread would motivate a regime gate; an unstable one closes the
direction.

## Inputs (read-only, never edited)

- 4h opens: `artifacts/research/engine_real/opens_v154.parquet`
  (BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, from 2017-08).
- Dip fills: `research/tournament/ext/fills_U_ext.parquet`
  (all fills 2020-08..2026-09; `T = t_fill - f minutes`; outcomes
  `y0.5/y1.0/y1.5`; majors rows at R2 depths = BOT rungs).
- Books: `forward_v205.research_books_d2` rebuilt EXACTLY as
  `research/tournament/oc_bookic/compute_bookic.py::research_books_d2`
  (same files, same math; union index, missing -> 0.0).
- Market data up to 2026-09-24 00:00 UTC may be read (assignment
  overrides the old tournament-harness dev cutoff; all five anchor
  years are research data, findings still need prospective validation).
- No 1m data. One process, small frames (RAM << 1 GB).

## Exact causal definitions (fixed before seeing numbers)

Grid = 4h bar open times `t` from the opens index (tz-aware UTC).
`O_s[t]` = open of coin `s` at `t`. 180 bars = 30 d, 540 bars = 90 d
(6 bars/day). All ratios use opens with index `<= t` only.

- `ratio[t] = O_ETH[t] / O_BTC[t]`
- `ethbtc30[t] = log(ratio[t] / ratio[t-180])` (30 d log change of ETH/BTC)
- `ethbtc90[t] = log(ratio[t] / ratio[t-540])` (90 d log change of ETH/BTC)
- `R_s30[t] = log(O_s[t] / O_s[t-180])` per coin; equal-weight majors
  30 d return `M30[t] = mean_s R_s30[t]` over the 5 majors;
  `dom30[t] = R_BTC30[t] - M30[t]` (BTC 30 d return minus equal-weight
  majors 30 d return; positive = BTC dominance episode).
- Warm-up: rows with any missing lag are NaN and dropped. Opens start
  2017-08, so every scored year (from 2021-09-24) has full windows.

Anchor years (5, assignment-literal): `Y_k = [A_k, A_k + 365 d)` with
`A_k = 2021-09-24, ..., 2025-09-24` (UTC). Note: 2023-09-24 + 365 d =
2024-09-23 (leap year), so the six 4h bars of 2024-09-23..24 belong to
no year; they are excluded from per-year AND 5y aggregates (count
disclosed in results.json). Fills/bars at exactly 2026-09-24 00:00 UTC
or later are excluded (data cutoff).

### (a) Dip rung edge by regime tercile

- Universe MAIN = `sym` in the 5 majors AND rung depth `x1` in
  `{2.5, 3.0, 3.5, 4.0, 5.0}` (R2 BOT depths). Outcome = `y1.0`
  (exact net return per fill at TP 1.0 sigma, unit rung size). No other
  outcome is used for selection.
- Fill regime = regime grid value at `max(grid t <= T)`, `T = t_fill -
  f minutes`. Since grid `t <= T` uses opens `<= t <= T`, it is known
  strictly before the fill. Fills with `T` before the first valid
  regime timestamp are dropped (count disclosed; expected 0).
- Previous-years cut-offs: for year `k`, `lo_k/hi_k` = 33rd/67th
  percentiles of the regime variable over MAIN fills with `T < A_k`
  (all history from 2020-08-21, strictly before the anchor). Fill
  tercile: value `< lo_k` -> lo, `> hi_k` -> hi, else mid (boundary
  ties go mid; never imputed).
- Per (year, variable): `n`, mean `y1.0` per tercile in bps
  (1 bps = 1e-4), `n` per tercile, effect `d = mean_hi - mean_lo`
  (bps). Effect sign = `sign(d)` (zero/NaN = fail, never imputed).

### (b) Book gross P&L by regime tercile

- Books `w[t]` (5 majors) inner-joined with opens on the 4h grid,
  sorted; next-bar simple return `r[t] = open[t+1]/open[t] - 1`;
  vectorised gross P&L (no costs) `pnl[t] = w[t] * r[t]` summed over
  the 5 coins for regime splits (per-coin sums also stored). Last grid
  bar (no forward return) dropped. Units diagnose the book signal, not
  engine net (before vol target, governor, fees, funding, sleeve).
- Regime at bar `t` uses opens `<= open[t]` (known at the close of `t`
  when `w[t]` is known). Same causal timing as oc_bookic.
- Previous-years cut-offs: for year `k`, `lo_k/hi_k` = 33rd/67th
  percentiles of the regime variable over 4h grid bars with
  `open_time < A_k` (all valid history, strictly before the anchor).
- Per (year, variable): `n` bars, `n` per tercile, sum `pnl` per
  tercile, mean per-bar `pnl` per tercile in bps/bar, effect
  `d = meanbar_hi - meanbar_lo` (bps/bar). Sign rule as in (a).

## Decision (verdict) rule — fixed now (assignment default)

Six effects = 3 variables x 2 parts. One effect is PROMISING only if
BOTH hold (per effect, parts scored separately):

1. Sign consistency: `sign(d)` identical in `>= 4` of the 5 anchor
   years (NaN/zero counts as a fail).
2. Leave-one-year-out: for each held-out year `h` (5 folds), cut-offs =
   33rd/67th percentiles over the pooled other-4-years data (MAIN
   fills for (a), grid bars for (b)); training sign = sign of the
   pooled other-4-years hi-lo with those cut-offs; the fold HOLDS if
   held-out hi-lo (same cut-offs) has the same non-zero sign as the
   training sign with minimum data (`n_lo,n_hi >= 30` fills for (a),
   `>= 50` bars per side for (b); otherwise the fold fails). PROMISING
   needs `>= 4` of 5 folds holding.

Cost context: round-trip cost ~4-8 bps; dip `y1.0` means are per-fill
bps; book means are per-bar bps/bar (6 bars/day). Spreads far below
cost are not actionable even if "consistent".

## Causality / alignment tests (tests/test_oc_ethbtc.py)

- `test_regime_causal_truncate`: 10 sample grid times; recompute the 3
  regimes from opens truncated to `<= t` and assert equal to the full
  run; plus a future-spike check (doubling opens after `t` leaves the
  row at `t` unchanged).
- `test_fill_regime_precedes_fill`: every kept fill has
  `grid_t <= T < next_grid_t` and cut-offs for year `k` use only
  fills/bars strictly before `A_k`.
- `test_aggregation`: tercile `n` sums to year `n`; tercile pnl sums to
  year total (part b); hi-lo diffs equal the stored tercile means
  difference; results.json schema (5 years x 3 vars x both parts).

## Outputs

`research/tournament/oc_ethbtc/`: PLAN.md (this file),
`regimes_ethbtc.py`, `analyze_ethbtc.py`, `results.json`, REPORT.md.
`tests/test_oc_ethbtc.py`. No tuning on results; any post-hoc change
logged in REPORT.md.
