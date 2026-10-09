# oc_bybitgap PLAN (pre-registered BEFORE any new outcome, 2026-10-07)

Assignment: `docs/opencode/OPENCODE_W_oc_bybitgap.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
+ `AGENTS.md` + `docs/opencode/OPENCODE_VF_COMMON.md`.
Write ONLY `research/tournament/oc_bybitgap/` + `tests/test_oc_bybitgap.py`.
Status: DESCRIPTIVE DECOMPOSITION ONLY. No rule change, no new trading variant,
no pre-registration of a fix (fixes are described-only for the leader).

## Pre-registered rows (ONLY these; no variants)

- G2 = deployed reference `R2B1D17BFG2` (research/parallel/rounds/parallel-20260906-r2/v421).
- G2_S5 = G2 run on Bybit 1m prices from 2021-11-15 (S5 friction exactly as
  v421_audit/robust_v421.py and oc_amihudrobust/compute_robust_engine.py:
  standard index filtered to >= 2021-11-15 before shift, win_start=5).
- No AB1/A1/jitter/control rows. No choosing between variants on any year.

## Fixed settings (frozen here)

- Gate costs: maker 0.0002 (entries, TPs, dip fills), taker 0.00055 (stops,
  market/timeout exits); longs pay 0.0001 per 8h settlement held (00/08/16 UTC),
  shorts receive nothing. Limit fills only on a 1m trade-through
  (strictly through the price); no fill in the first 5 minutes after a 4h close
  (win_start=5); stop-first when stop and TP are both touched in the same 1m bar.
- Anchors: 2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24 (dev4 selection window
  for reference only) and 2025-09-24 (most recent year, LABELLED byproduct only).
  Each year = [A, A+365d). 2021 S5 year is a short window from 2021-11-15 (labelled).
- Metric: 4-phase reset metric (research/diagnostics/r2_decompose5/reset_metric.py
  year_reset) for %/month geometric mean; full-path DD = max(4h-close, 1m-marked)
  continuous path (v388.mix convention). Single-phase oc_bookvenue numbers are
  labelled single-phase diagnostics, never mixed with the 4-phase gate.
- Deployed reference numbers to reproduce EXACTLY before any decomposition claim:
  G2 dev4 5.601 / W 2.588 / DD 16.91; G2 5y 5.410 / full-DD 16.82;
  G2_S5 dev4 4.994 / 5y 4.883 / full-DD 18.09 (oc_amihudrobust engine_results.json).
  Cached v421_runs.pkl must assert 5.41 / W 2.588 / DD 16.91 / full 16.82. Else STOP.

## Data (fixed, no fetching, no uploads)

- Binance 1m: `data/raw/btc_intraday_20260924` (BTC klines_1m_20*.parquet) +
  `data/raw/majors_intraday_20260924` (<SYM>_1m_20*.parquet), columns
  open_time/open/high/low/close (open_time tz-aware UTC).
- Bybit 1m: `data/raw/bybit_linear_1m_20261004/<SYM>_1m.parquet`, open_time in ms,
  columns open/high/low/close (+volume/turnover unused here).
- Published aggregates only (read-only, never edited):
  oc_amihudrobust/engine_results.json (G2/G2_S5 4-phase),
  research/diagnostics/oc_bookvenue/results.json (s0/s2 4-way book/dip split),
  research/tournament/oc_venuegap/results.json+fills.parquet (B1 replica dip),
  oc_bybittp/results.json, oc_bnbvenue/results.json, oc_contrib/results.json,
  oc_kpi_g2/results.json, oc_topbook/results.json.
- No exchange orders, no authenticated endpoints, no Kaggle.

## Method (frozen)

1. Reproduction gate (light, no new engine): load v421_runs.pkl + v421_result.json
   and oc_amihudrobust/engine_results.json; assert the six numbers above to the
   digit; recompute dev4/5y gaps per year (G2 minus G2_S5) from the stored yearly
   rows. No new 4-phase engine run (two prior studies already reproduce to the
   digit with the identical harness; a third full replay adds no information).
2. Book vs dip leg (read-only reuse, labelled): quote oc_bookvenue s=0/s=2
   base/s5/book_byb/book_bin per-year %/month and full-window gaps; book eff =
   book_byb-base, dip eff = book_bin-base, residual = gap-book-dip (Bybit-open
   sizing + interaction). State explicitly these are single-phase R2B1D17BF
   diagnostics, not the 4-phase G2 gate.
3. Per coin (read-only reuse): oc_venuegap per_coin_year 5y gaps (B1 replica
   rung-y sums, labelled NOT %/month); oc_contrib BNB weight table (additive mix%,
   reference only); state that no per-coin book-leg table exists in oc_bookvenue.
4. Per component (read-only reuse + bounds): book fills/fill-rate/stops/TPs and
   matched limit/fill/stop/TP bps diffs (oc_bookvenue diffs); dip fills/TPs/SL/
   timeouts and TP-rate deltas (oc_bookvenue book blocks); funding bound
   (adverse longs-only 0.0001/8h; venue funding diff only from divergent
   position paths, bounded by the near-identical fill counts); vol-scale and
   governor: NEW light computation (this study) comparing venue-native 4h-open
   rolling-360 sigma (mean ratio, median |diff|) and noting governor g uses
   equity path (venue-dependent only via realised equity, no separate fit).
5. NEW price-series diagnostics (this study, script `diagnose_venue.py`, via
   heavy_slot, streaming per coin, peak < 0.4 GB target; if it exceeds, it still
   runs inside the slot):
   - 4h grid from 2020-08-01 00:00 UTC; overlap bar open T in [2021-11-15, 2026-09-24).
   - Per coin: Bybit-vs-Binance 1m close basis in bps (median, p50/p90/p95 |diff|,
     mean|diff|); minute-low wick depth differences (low minus min(open,close)
     per minute; median and p95 per venue + paired diff); 4h-open shift (median,
     mean|.|) for cross-check vs oc_bookvenue/oc_venuegap.
   - Trade-through agreement at G2-relevant prices: book limit
     (minute-0 open -/+ max(10bps, 0.25*sigma_4h) venue-native, long side; short
     side symmetric reported as one row) and dip rungs lv=O*(1-k*sg) k in
     (2.5,3.0,3.5,4.0,5.0) venue-native sigma: per (coin,k): bars, both-fill,
     bin-only, byb-only, neither; P(bin fill | byb fill) and P(byb fill | bin fill);
     exit-agreement on both-fill rungs deferred to oc_bybittp (quoted, not recomputed).
   - Vol-scale: venue-native 4h-open sigma (pct-change rolling 360, min 120, shift 1)
     per bar per coin: median sigma ratio (byb/bin) and median |sigma diff| in bps
     of price; rung-level shift implied (k*dsigma) reported.
   - All timestamps UTC; years by exit/bar date with the same 2021-11-15 short-window
     label. No returns, no fits, no thresholds tuned on any year.

## Selection / verdict rule (descriptive; no variant picked)

- No selection input uses the most recent year (2025-09-24..2026-09-23); it is
  scored/quoted once as a labelled byproduct.
- Verdict is descriptive: name the coin(s)/component(s) carrying the gap with
  numbers, or state the gap is diffuse; describe (do not run) the obvious
  pre-registrable venue fixes for the leader. A negative/diffuse result is valid.

## Leakage checks (pre-registered)

- Feature timing: diagnostics use only minutes < bar close for levels (O(T), sg(T)
  from opens strictly before T) and minutes in [T+16m, T+238m] for fills;
  basis/wick stats are contemporaneous minute comparisons (no prediction).
- Label windows: none fitted (realised 1m path comparisons only).
- Fit windows: no fits; sigma is a trailing rolling std (min_periods 120, shift 1);
  no quantile/threshold is tuned on any test year.
- Fill timing: strict `low < lv` (long rungs; symmetric for shorts) from minute 16,
  stop-first documented; book-limit analogue uses minute-0 open and trailing sigma
  only. Tests assert strict-through, minute-16 start, and truncation causality.

## Deliverables

- `research/tournament/oc_bybitgap/`: PLAN.md (this file), `diagnose_venue.py`
  (reproduction gate + new price diagnostics), `results.json` (reproduced gaps +
  quoted book/dip + new price tables), `REPORT.md` (per-year tables, components,
  what failed, 3-line Vietnamese verdict), `tmp/` scratch only.
- `tests/test_oc_bybitgap.py`: >=1 causality/truncation test + >=1 hand-checked
  synthetic case; run `.venv/Scripts/python.exe -m pytest tests/test_oc_bybitgap.py -q`.
- Progress printed every 10 minutes during the scan (per-coin progress lines).
- Stop when done.

## Post-hoc log (append-only; entries after outcomes go here)

- (none yet; PLAN written before any new computation)
