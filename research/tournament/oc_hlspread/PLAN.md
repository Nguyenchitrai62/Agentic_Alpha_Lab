# PLAN.md — oc_hlspread (pre-registered BEFORE any outcome; SHORT-SPAN)

Assignment: `docs/opencode/OPENCODE_W_oc_hlspread.md` + common header
`docs/opencode/OPENCODE_W_COMMON_20261007.md`. Idea B1 / data D4 from
`docs/opencode/IDEAS_20261007c.md`; funding description from
`research/tournament/data_hlfunding/REPORT.md`.

## Pre-registered scope (fixed before any outcome)

SHORT-SPAN task. Only anchor years 2023-09-24 and 2024-09-24 have usable
history (2025-09-24 partially). Label everything SHORT-SPAN. NO dev4
selection, NO deployment from this span. At best "log prospectively".

## Data (read-only)

- HL: `data/raw/hyperliquid_20261007/HL_<COIN>_funding_1h.parquet`
  (BTC/ETH/SOL/BNB from 2023-05-12, XRP from 2023-06-18; hourly after
  ~2023-06-08, 8h-cadence before; 3 hourly rows missing span-wide).
- Binance settled: `data/raw/binance_premium_20260928/<SYM>_funding.parquet`
  (`calc_time` at 00/08/16 UTC, `last_funding_rate` per 8h; ends
  2026-08-31 16:00 UTC — exact overlap end stated in REPORT).
- Prices for the descriptive leg only: `artifacts/research/engine_real/opens_v154.parquet`
  (4h opens, 5 majors). No 1m in the descriptive leg.

## Signal (fixed, causal)

Per 8h window `w` (win start floored to 8h UTC):
`HL8[w] = sum(HL fundingRate rows with floor(time,8h)==w)` (windows with no
HL row skipped, never imputed); `BN8[w] = Binance last_funding_rate at w`.
`Draw[w] = HL8[w] - BN8[w]` (inner join).

At each 4h bar close `T`: `D(T) = mean(Draw[w])` over the last 21 windows
with `w + 8h <= T` (i.e. `w <= T-8h`, fully settled before T; 7 days).
If fewer than 21 such windows exist, `D(T)=NaN`.

`z(T) = (D(T) - mean1y(T)) / std1y(T)` where `mean1y/std1y` are the
sample mean/std of prior `D(T')` values with `T-365d <= T' < T`
(strictly before T, current excluded; population std ddof=1; std==0 -> NaN).
Require >= 720 prior finite `D` values (120 days of 4h bars); else NaN.
NaN -> no signal (multiplier 1.0).

Hypothesis (fixed now, contrarian to crowding): `|z|` large = crowded /
segmented tape -> the book's position in that coin should be SMALLER:
`z > +1.5` -> book LONG weights x0.5; `z < -1.5` -> book SHORT weights x0.5.
Thresholds +/-1.5 fixed; multiplier 0.5 fixed; both sides gated
symmetrically (unlike single-side brakes).

## Variants (ONLY these; no tuning)

- `G2` = reference `R2B1D17BFG2` (rule inv, k 1.0, kd 1.7, bear True, G 2.0),
  loaded from `v421/v421_runs.pkl`; must reproduce 5.41 / 16.91 / 16.82
  (reset-metric R / yearly-max DD / full-path DD) to the digit first,
  else stop.
- `H1` = G2 + the rule above: on STANDARD book rows (sb index, after the
  v410 bear-book filter, before the shifted-clock forward fill), per
  (T,sym): if `z> +1.5` and `w_base>0` -> x0.5; if `z< -1.5` and
  `w_base<0` -> x0.5; else unchanged. Rows before 2021-09-24 never gated
  (v426 convention; no-op here since z starts 2023).
- `CTRL` = exposure-matched constant multiplier, no timing: per anchor
  year `y`, `cL_y` = H1 realised mean multiplier on book LONG cells
  (standard-index, bear-filtered `w_base>0`) that year, `cS_y` = same on
  SHORT cells (`w_base<0`); applied to ALL long (resp. short) cells that
  year (NaN-z periods included in the means, so sparse years -> ~1.0).
  Judges timing vs mere exposure cut.

## Tests (fixed)

1. Descriptive (2023-05-01 .. 2025-09-23 00:00 UTC only; never >=2025-09-24):
   per coin, Spearman IC of `z(T)` vs next-24h and next-7d
   vol-normalised forward return; share of bars with `|z|>1.5`
   (and split `z>+1.5` / `z<-1.5`). Forward from 4h opens:
   `r24 = open[T+6]/open[T]-1`, `r7d = open[T+42]/open[T]-1`;
   trailing vol `s = std(4h open-to-open returns over [T-30d,T), min 60 bars)`;
   normed `r/(s*sqrt(6))` resp. `r/(s*sqrt(42))`; s NaN/0 -> NaN (excluded).
   Spearman over bars with finite z and finite normed forward.
2. Engine (4-phase, heavy_slot, Pool(2), tag `oc_hlspread`): G2/H1/CTRL with
   the v426_book_brake mechanism (per-(T,sym) multipliers on sb, ffill to
   shifted clocks); gate costs maker 0.0002 / taker 0.00055, longs funding
   0.0001/8h, shorts 0; limit fills only on 1m trade-through, no fill first
   5 min after a 4h close, stop-first. Report per anchor year 2023, 2024,
   2025 (2025 labelled most-recent-year, scored once) via
   `reset_metric.year_reset` + `v388.mix` full-path DD; plus standard-index
   gated-cell shares and CTRL constants. No dev4 mean, no selection.

## Leakage statement (fixed upfront)

- Funding windows enter `D(T)` only when fully settled (`w+8h<=T`).
- `z(T)` trailing stats use strictly prior `D(T'<T)`; thresholds fixed.
- Descriptive forwards use `open[T+k]` only as labels; vol uses returns
  over `[T-30d,T)`; Spearman window capped at 2025-09-23.
- Engine: gate panel joined as-of standard-row `T` only, applied after the
  bear filter and before ffill (v426 order); CTRL constants are per-year
  realised means (no cross-year peek; 2025 constants from 2025 H1 only).
- Fits/thresholds use no test-year statistic; the +/-1.5 is fixed in this
  PLAN before any outcome.

## Deliverables (write-only)

`research/tournament/oc_hlspread/`: PLAN.md (this file), `signal.py`
(panel + descriptive), `run_engine.py` (4-phase), `panel.parquet`,
`descriptive.csv`, `results.json`, `REPORT.md` (per-year tables, gated
shares, what failed, leakage checks, 3-line Vietnamese verdict).
`tests/test_oc_hlspread.py` (causality/truncation + hand-checked synthetic).
Scratch under `tmp/` only. No other files touched.

## Post-hoc log

- (none yet; any change after an outcome adds a disclosed extra row, keeps the original)
