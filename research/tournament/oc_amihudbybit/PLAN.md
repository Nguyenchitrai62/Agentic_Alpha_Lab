# oc_amihudbybit PLAN (pre-registered BEFORE any engine run, 2026-10-07)

Assignment: `docs/opencode/OPENCODE_W_oc_amihudbybit.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
+ `docs/opencode/OPENCODE_W_TEMPLATE_BOOKGATE_20261007.md`.
Write ONLY `research/tournament/oc_amihudbybit/` + `tests/test_oc_amihudbybit.py`.
Status: POST-HOC (labelled): motivated by seeing A1 fail the Bybit-price stress
(oc_amihudrobust S5 gap -0.005, full-path DD 21.3). Even a positive result is
paper evidence only, never a deployment claim.

## Hypothesis (fixed here)

- A1 (oc_lit_xs, Binance Amihud tilt) overweights BNB/XRP, which are much less
  liquid on Bybit (where the owner trades). A venue-consistent tilt measuring
  illiquidity where orders execute may keep the gain on Bybit prices.
- AB1: identical to A1 except Amihud is computed from BYBIT daily data.
  Prior: low (A1's edge is +0.24pp dev4 and vanishes on S5; 5-coin XS is thin;
  this is 1 post-hoc variant, multiple-testing risk disclosed).

## Data (fixed, no fetching)

- Binance daily (A1 repro only): `data/raw/xs_universe_20260924/<SYM>_1d.parquet`
  (open_time, close, quote_volume), spans per oc_lit_xs PLAN (BTC 2019-09-09..,
  SOL 2020-09-15.., all to 2026-09-23). Logic copied bit-exact from
  `oc_lit_xs/xs_signal.py` (no edits there).
- Bybit daily (AB1): built from `data/raw/bybit_linear_1m_20261004/<SYM>_1m.parquet`
  (1m linear perps; columns open_time(ms), open, high, low, close, volume,
  **turnover**). USES THE TURNOVER COLUMN (present for all 5 symbols, USDT).
  No `close x volume` fallback needed (stated per assignment).
  Manifest spans: BTC/ETH/XRP 2021-06-01.., BNB 2021-06-29 07:18..,
  SOL 2021-10-15.., all to 2026-10-03, zero missing minutes.
- Bybit daily construction (causal, calendar days UTC):
  - day D = minutes with 00:00(D) <= open_time < 00:00(D+1).
  - close_d = close of the last minute bar of day D (NaN if day empty).
  - turnover_d = sum(turnover) over day D (NaN if day empty or non-positive sum).
  - r_d = close_d / close_{d-1} - 1 (NaN if either close missing/non-finite).
  - amihud_d = |r_d| / turnover_d (NaN if r non-finite or turnover missing/
    non-positive/non-finite).
  - Amihud30(D) = mean(amihud_d over D-29..D), require >= 20 non-NaN else NaN.
  - Full consecutive daily index per coin (gaps stay NaN, no ffill).
  - Coverage consequence (disclosed): SOL Amihud30 needs 20 days from
    2021-10-15, so SOL raw is NaN until ~2021-11-03; BNB until ~2021-07-28.
    Fallback (same as A1): NaN raw -> NaN z -> multiplier 1.0; XS z with <2
    finite syms or std 0/non-finite -> 0 for finite raws.

## Signal definitions (fixed, causal; AB1 mirrors A1 exactly)

- Decision-time mapping (same as A1): for a 4h decision time T, last fully
  closed daily bar is `D*(T) = date(T) - 1 day` (day D usable iff D+1 00:00 <= T).
  Raw inputs at T use only days <= D*(T).
- Cross-sectional z at T (same-T only): `z = (x - mean)/std(ddof=1)` across
  finite syms; <2 finite or std 0/non-finite -> 0 for finite raws; NaN raw -> NaN.
- Multiplier (both legs, same K/clip/side rules as A1):
  `AB1 = clip(1 + 0.25 * z_bybit, [0.5, 1.5])`, NaN -> 1.0.
  Applied to every non-zero bear-filtered STANDARD book weight (both legs),
  same v426 slot as A1 (after bear filter, before shifted-clock ffill;
  rows before 2021-09-24 untilted).
- K=0.25, window 30d/min-20, clip [0.5,1.5], both-legs. No other variant.
  No size-neutralisation, no longs-only leg (assignment names AB1 only).

## Book-gate mechanism (fixed, v426 copy via oc_lit_xs / oc_amihudrobust)

- Base = G2 (`R2B1D17BFG2` in v421: rule inv, k 1.0, kd 1.7, bear True, G 2.0).
  Multiplier on STANDARD book rows after the bear filter (BTC 4h open <
  1200-bar mean -> longs x0.5) and before the shifted-clock forward fill.
  Harness, costs, fills, reset metric, full-path DD exactly as v426/v421/
  oc_amihudrobust (gate costs maker 0.0002, taker 0.00055, longs 0.0001/8h at
  00/08/16 UTC, shorts nothing; limit fills only on 1m trade-through, no fill
  in first 5 min after a 4h close (`win_start=5` base); stop-first same bar).
- Exposure-matched control CTRL_AB1 (per template): per anchor year constant c
  = AB1's realised mean multiplier over non-zero cells in that year (both legs;
  realised-exposure only, no return information). Applied to every non-zero
  row of that year. Same constants on both price grids (signal is grid-free).
  AB1 must beat CTRL_AB1 on dev4 mean to claim timing value.
- Pre-registered rows (ONLY these 8 engine rows):
  - Base grid (Binance 1m via pod.minutes()): G2, A1, AB1, CTRL_AB1.
  - S5 grid (Bybit 1m via bybit_minutes(), standard index filtered to
    >= 2021-11-15 before shift, `live0 = 2021-11-15 + shift`, win_start=5):
    G2_S5, A1_S5, AB1_S5, CTRL_AB1_S5.
  - A1 = Binance-Amihud repro (must match oc_amihudrobust to the digit).

## Reproduction gate (stop if failed)

- Cached `v421_runs.pkl` via `reset_metric.year_reset` + `v388.mix`:
  5.41 %/mo, W 2.588, max yearly DD 16.91, full-path DD 16.82, yearly rows
  (2.588/10.86, 3.282/16.91, 6.045/15.81, 10.677/8.27, 4.648/12.9). Else STOP.
- Engine must re-run to the digit before any AB1 comparison is valid:
  G2 dev4 5.601/W 2.588/DD 16.91; A1 dev4 5.844/W 2.798/DD 16.81;
  G2_S5 dev4 4.994 / 5y 4.883 (oc_amihudrobust numbers); A1_S5 dev4 4.989 /
  5y 4.884. Else STOP, no overlay claim.

## Selection (ONLY on dev4 2021-09-24..2025-09-23)

- Template candidate rule, applied on EACH grid vs that grid's G2:
  dev4 mean > G2 dev4 mean AND dev4 worst > G2 dev4 worst AND max yearly DD <=
  G2 max yearly DD + 0.5 AND beats its control on dev4 mean.
  Base-grid G2: 5.601 / 2.588 / 16.91. S5-grid G2_S5: 4.994 / 2.129 / 18.11.
- Primary verdict grid is S5 (Bybit prices, where the owner trades):
  venue-consistent iff AB1_S5 beats G2_S5 and CTRL_AB1_S5 on dev4 mean with
  DD discipline, and full-path DD <= 20.
- The most recent year 2025-09-24..2026-09-23 and the 5y path are reported as
  LABELLED byproducts for all rows (assignment requires them); they are never
  selection inputs. No choosing between A1 and AB1 on the last year.
- Robust view also reported (DD<=20, no losing dev year; prefer dev4 mean>=5
  then highest dev4 worst; ties -> higher mean).

## Leakage checks (pre-registered)

- Feature timing: Bybit daily day D built from minutes < D+1 00:00 only;
  D+1 00:00 <= T mapping; sampled-T truncation test must leave multipliers
  unchanged; +-1s boundary exposes exactly the prior day. Turnover column is a
  realised volume sum (no price lookahead); close_d is the last minute close.
- Label windows: none fitted (engine uses realised 1m path).
- Fit windows: no fits; XS mean/std at same T only; K/window/clip/side rules
  fixed here (copied from A1).
- Fill timing: engine win_start=5 + 1m trade-through + stop-first (v426
  harness, G2/A1/S5 bit-exact). Tests assert these constants.

## Deliverables

- `research/tournament/oc_amihudbybit/`: PLAN.md (this file), `bybit_signal.py`
  (Bybit daily + XS z + AB1 multipliers + bit-exact Binance A1 path),
  `compute_bybit_engine.py` (8-row 4-phase engine via heavy_slot),
  `results.json`, `REPORT.md` (per-year tables both grids, what failed,
  3-line Vietnamese verdict: venue-consistent gain on Bybit with DD<=20?
  Even if yes: post-hoc -> paper only).
- `tests/test_oc_amihudbybit.py`: >=1 causality/truncation test + >=1
  hand-checked synthetic case; run `.venv/Scripts/python.exe -m pytest
  tests/test_oc_amihudbybit.py -q`. Stop when done.

## Post-hoc log

- Outcome 2026-10-07: harness proof passed (G2/A1/G2_S5/A1_S5 to the digit).
  Base dev4: AB1 5.748/W 2.735/DD 17.60 vs G2 5.601/2.588/16.91 vs CTRL 5.674
  (beats mean/worst/control, FAILS template DD 17.60 > 17.41, loses to A1).
  S5 dev4: AB1_S5 5.039/W 2.251/DD 19.95 vs G2_S5 4.994/2.129/18.11 vs CTRL
  4.992 (beats mean/worst/control, FAILS template DD 19.95 > 18.61;
  full-path DD 22.48 > 20). No definition was changed after seeing outcomes
  (one pre-outcome code fix only: removed leftover placeholder line in
  `build_tilt_frames_std` before the first engine launch).
