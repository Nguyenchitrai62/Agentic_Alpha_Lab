# oc_presampletilt — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_presampletilt.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md read). Write ONLY `research/tournament/oc_presampletilt/`
+ `tests/test_oc_presampletilt.py`. No other file is edited (registry, ledgers,
NEXT_AGENT.md, ../Kronos, git state untouched; GIT READ-ONLY: never stash/reset/
checkout/restore/clean/rm/commit/switch/rebase/merge). Scratch only under
`research/tournament/oc_presampletilt/tmp/`. Heartbeat print every 600 s in long
jobs; progress print every 10 minutes. CPU for RV6/GARCH; Chronos inference on
GPU via heavy_slot (reuse `research/tournament/oc_chronos/pylib` + its run-script
logic; model `amazon/chronos-bolt-small` revision `772f3d25d38aec6d914c8949dab4462e2d46f5d8`).
RAM is tight: one heavy job at a time through
`.venv/Scripts/python.exe scripts/heavy_slot.py run --tag <tag> --min-free-gb 2.0 -- <cmd>` (never `--leader`).

## Why (from assignment)

oc_voltilt / oc_chronos / oc_toto / oc_timesfm / oc_kronoshidden: every "bigger dip
rungs when downside vol is forecast high" tilt times dips well in 2023-2026 and not
in 2021-2022. Chronos-Bolt and RV6/GARCH never saw crypto, so years BEFORE 2021 are
genuinely unseen for them. oc_presample + oc_presample2 already replay the frozen dip
sleeve on 2017-2020 — reuse that machinery for the ledger, add frozen vol/Chronos
tilts on top.

## Frozen variants (ONLY these three, no ensemble, no refit, no tuning)

- V_RV6: risk = risk_RV6 (oc_voltilt definition), multiplier rule below with the
  EARLIEST frozen fit (oc_voltilt `fits.json` `V_RV6` anchor `2021-09-24`).
- V_GARCH: risk = risk_GARCH (oc_voltilt definition, GARCH params = anchor-2021 fit
  frozen from `oc_voltilt/garch_params.json`), same rule with the EARLIEST frozen fit
  (`V_GARCH` anchor `2021-09-24`).
- C2: risk = -ch_q10 (Chronos inference exactly as oc_chronos), same rule with the
  EARLIEST frozen fit (`oc_chronos/fits.json` anchor `2021-09-24`).
- All three: hi/lo = 1.25/0.75, direction +1 (all three anchor-2021 dirs are +1),
  missing/NaN risk -> 1. Fits of 2021 applied to ALL pre-sample years on all 4 shifts.
  Labelled everywhere "fit from later data, rule frozen" (fixed rule on unseen years;
  pre-sample years never used for any fit). No selection is made on pre-sample;
  this is a report-only diagnostic.

Frozen fit constants (copied verbatim, never refit):

| variant | direction | q20 | q80 | train rho |
|---|---|---|---|---|
| V_RV6 2021-09-24 | +1 | 0.837211709240698 | 1.9839920144443897 | 0.0805 |
| V_GARCH 2021-09-24 | +1 | 1.0241413111212145 | 1.8039629065556178 | 0.0929 |
| C2 2021-09-24 | +1 | 1.110054237503456 | 2.8608138206510407 | 0.0364 |

Frozen GARCH anchor-2021 params (from `oc_voltilt/garch_params.json`, per sym;
filter only, never refit):

| sym | omega | alpha | beta | v0 |
|---|---|---|---|---|
| BTCUSDT | 2.962749661683187e-06 | 0.06526335208168146 | 0.927825881135516 | 0.00030457605407065315 |
| ETHUSDT | 9.972397326731373e-06 | 0.06760328712823072 | 0.9113538693053522 | 0.0005169218725223849 |
| BNBUSDT | 9.640560196328421e-06 | 0.10024750483483949 | 0.8886495920681354 | 0.0007154168357336774 |
| XRPUSDT | 1.107902967921202e-05 | 0.1460578011936826 | 0.8529388899901152 | 0.001066255372848162 |
| SOLUSDT | 6.65824954650193e-05 | 0.1186419810746963 | 0.8370588436909113 | 0.0014765894890886972 (unused pre-sample; SOL absent) |

## Frozen inputs (read-only, never edited)

- `data/raw/spot_1m_presample_20261007/` (Binance SPOT 1m 2017-08..2020-09-30; BTC/ETH
  from 2017-08-17, BNB from 2017-11-06, XRP from 2018-05-04; SOL absent; manifest.json
  sha256-verified). Read-only; copy nothing, edit nothing.
- `research/tournament/oc_voltilt/fits.json`, `garch_params.json`, `tilt_rule.py`
  (`assign_mult` copied verbatim), `build_vol_features.py` (definitions copied verbatim).
- `research/tournament/oc_chronos/fits.json`, `tilt_rule.py`, `run_chronos_4shift.py`,
  `compute_placebo.py` (method copied), `pylib/` (Chronos env, read-only reuse).
- `research/tournament/oc_k2placebo/compute_k2placebo.py` + `tmp/ledger.npz` (2021-2026
  reference only) + `research/tournament/oc_placebo_dip/compute_placebo_dip.py`
  (replica core: n_vector/size_mult/find_fill/outcome_mu, read-only import).
- `research/tournament/oc_presample/presample.py` + `oc_presample2/presample2.py`
  (spot loaders, ORIGIN grid, warm-up rule, gate costs; core copied, not imported).
- 2021-2026 side-by-side numbers are COPIED from `oc_voltilt/tmp/placebo_vol.json`,
  `oc_chronos/tmp/placebo_c2.json` (+ `oc_k2placebo/results.json` base reference),
  never recomputed. Expected copies (frozen):
  V_RV6 timing pct y0..y4 = 2.40/14.49/97.10/100.0/100.0, block = 1.40/16.78/96.00/100.0/100.0;
  V_GARCH timing = 12.39/7.29/99.90/100.0/100.0, block = 8.39/19.18/100.0/100.0/100.0;
  C2 timing = 90.11/88.31/100.0/100.0/99.20, block = 85.61/89.01/100.0/100.0/98.90.

## Pre-sample years + coins (fixed, same as oc_presample2)

- Y2017 = [2017-10-16, 2018-01-01), Y2018 = [2018-01-01, 2019-01-01),
  Y2019 = [2019-01-01, 2020-01-01), Y2020p = [2020-01-01, 2020-09-01).
  Rungs opened on bars with open in the interval; exits may realise after.
- Majors available on Binance at the time (say in REPORT): Y2017 BTC+ETH only
  (BNB/XRP before warm-up); Y2018+ BTC/ETH/BNB (+XRP from 2018-07-03 warm-up);
  SOL absent all pre-sample legs. B1 n counts coins-present-only.
- The extra window 2020-09-24..2021-09-23 is NOT evaluated here: the spot store ends
  2020-09-30 (only 6 days overlap), so no spot-feature year can be built; the perp
  leg for 2020-09-20..2021-09-21 already exists in oc_tiltgate (5301 fills) with a
  different store and is cited as reference only. Mixing stores would break feature
  consistency.
- Warm-up (identical to oc_presample/oc_presample2): no trading before first finite
  bar + 60 days per coin (BTC/ETH 2017-10-16, BNB 2018-01-05, XRP 2018-07-03).

## 4h bars + features (fixed, causal, same 4 clocks)

- 4h grid: ORIGIN = 2020-01-01 00:00 UTC, bar j of phase s covers
  [ORIGIN + s h + 4h*j, +4h) for ALL integer j (negative j extends back to 2017),
  phases s in {0,1,2,3}. Built from spot 1m (o,h,l,c): open = first finite open,
  high = max high, low = min low, close = last finite close, nmin = finite-minute
  count; a 4h bar with zero finite minutes is NaN (never traded, never a feature).
- sigma[E] (EXACT oc_voltilt/oc_chronos replica): lo = log(open),
  sig[E] = rolling(360).std(ddof=1) of diff(lo) at E (pandas default; uses opens <= T[E]).
- r[i] = log(C[i]) - log(C[i-1)] (r[0] = NaN). RV6[E] = std(ddof=1) of r[E-6..E-1]
  (= r.rolling(6).std().shift(1); requires E>=7 and all 6 finite). risk_RV6 = RV6/sig
  (NaN if sig missing/nonpositive/nonfinite).
- GARCH filter (causal, frozen params above): var[0] = unconditional
  omega/(1-alpha-beta) (fallback v0); for E>=1 forecast for bar open T[E] uses only
  r[E-1] and earlier (non-finite r treated as 0 in the recursion, exactly as
  oc_voltilt `garch_filter`); sigma_GARCH[E] = sqrt(var[E]); risk_GARCH = sig_G/sig
  (NaN if sig missing/nonpositive or E<360 burn-in).
- Chronos C2 (exactly oc_chronos Part A): per (sym, shift) context = last 512 closes
  (log) ending at the bar closing at T[E] (bars E-512..E-1); horizon 1; quantiles
  0.1..0.9 from Chronos-Bolt-small; ch_q10 = (q10 - log C0)/sig (C0 = close of bar
  closing at T, sig = same sigma above); risk = -ch_q10. First usable bar needs
  E>=512 AND sig finite, i.e. ~85 days after each coin's data start. Deterministic
  quantile heads, seed 20261007, batch 128, torch BEFORE pandas, GPU via heavy_slot.
  Record package versions + requested model revision + resolved revision in results.
- Output: `bars_4h_presample.parquet` (sym,shift,T,open,high,low,close,nmin),
  `vol_features_presample.parquet` (sym,shift,T,sigma,risk_RV6,risk_GARCH),
  `chronos_features_presample.parquet` (sym,shift,T,ch_q10,ch_q50,ch_q90,sigma).
  Engine join is missing -> 1, so extra early rows are inert.
- Causality: truncation test (features recomputed from 1m truncated at a cut date
  are identical on the kept prefix with FROZEN GARCH params; Chronos rerun on the
  truncated store is identical on the kept prefix up to float tolerance).

## Dip replica ledger (fixed; same D0+B1 replica as oc_k2placebo/oc_tiltgate, on spot)

- Same core as `compute_placebo_dip` (n_vector v399-exact coins-present-only with
  closes up to minute f-1, find_fill STRICT low trade-through, outcome_mu TP legs
  0.9/1.0/1.1 with close5 4sg stop + 8sg backstop + TP + timeout at next 4h open,
  maker 0.0002/taker 0.00055, adverse long funding 0.0001 on settle timeouts/stops
  at 240, stop-first, live offsets 16..238). NO budget, NO gross cap (pure replica;
  presample/presample2 budget/cap machinery is NOT used here).
- Per (bar T, coin, rung k in {2.5,3,3.5,4,5}): lv = O(T)*(1-k*sg(T)) (sg = the
  presample sigma with min_periods 120, same as build_grids/compute_sigma family;
  bars with non-finite O/sg skipped); fill at FIRST f in 16..238 with low(f) < lv;
  w = 1/(1+n_fill); y10 = outcome_mu(..., mu=1.0, ...) (y09/y11 computed for the kept
  rule only). Kept iff filled AND y09/y10/y11 ALL finite (paired legs, exactly as
  k2placebo `build_base`). NaN 1m gaps never fill/trigger/exit (inherited).
- Years Y2017/Y2018/Y2019/Y2020p (bars with open in the interval) + reference
  2021-2026 numbers copied (not rebuilt). Coins per bar limited to warmed-up coins
  with finite O/sg (absent coins excluded from n-counts too).
- Output: `tmp/ledger_presample.npz` (phase/coin/year/bar_T/rung/w/y10) +
  `tmp/bt_presample.npy` (bar-open datetimes) + per-leg fill counts. Spot-vs-perp
  caveat on every number (SPOT fills/exits, perp gate costs).

## Tilt evaluation (fixed; replica-ledger placebo, same as k2placebo/voltilt/chronos)

- Per fill join (sym, shift=phase, T=bar open) to the pre-sample feature tables;
  assign_mult with the FROZEN 2021 fits above (hi/lo 1.25/0.75, missing -> 1).
- Per pre-sample year y (4 legs pooled as 4-phase means, same as k2placebo
  `phase_mean_sums`): base(y) = mean_p sum(w*y10), tilt(y) = mean_p sum(w*mult*y10),
  realised_mean(y) = mean mult over fills in y, norm(y) = tilt(y)/realised_mean(y),
  gain(y) = norm(y)-base(y). "Helps" in a year iff gain(y) > 0. Report n fills too.
- Timing placebo per year (primary): 1000 uniform bar-level permutations of the
  variant multipliers over that year's decision-bar universe (seed 20261007+y),
  normalised by the ACTUAL realised mean (constant denominator); percentile =
  100*(1+#{perm<=actual})/1001; significant iff >= 95.
- Block placebo per year: 42-bar blocks per (sym, shift) permuted within the year
  (seed 20261008+y), same normalisation/percentile/significance.
- 2021-2026 columns are COPIES from the frozen files above (base/norm/timing/block),
  labelled "2021-2026 copied, not recomputed". No statistic from any test year
  feeds any choice (fits are frozen 2021; permutations are within-year only).

## Metrics / verdict (fixed)

- Table: per pre-sample year x {V_RV6, V_GARCH, C2}: n fills, base, tilt, realised
  mean, normalised gain (norm, gain), timing pct, block pct; plus the same numbers
  for 2021-2026 side by side (copied).
- Verdict (Vietnamese, 3 lines in REPORT.md): in how many of ALL available years
  (pre-sample 4 + 2021-2026 5 = 9) does each tilt help (gain>0, and of those how many
  with timing>=95), and is 2023-2026 the rule or the exception? Adopt/reject/needs
  prospective label for the tilt family (no engine adoption here; diagnostic only).
- Gate costs: maker 0.0002, taker 0.00055 (stops/market exits taker), longs pay
  0.0001/8h settlement held, shorts n/a (long-only sleeve); limits fill only on
  strict 1m trade-through, nothing in minutes 0..15 (replica LIVE_A=16); stop-first
  in the same 1m bar (replica core handles). State in REPORT how feature timing,
  label windows (none fit here; fits frozen 2021 with harness t_exit < A-7d
  inherited), fit windows (shift-0 2021 fits + 7d embargo inherited; GARCH params
  from bars closing before 2021-09-17, prices only) and fill timing were checked.

## Compute plan (heavy_slot, resume-safe, heartbeat every 600 s)

- `tilt_rule.py`: `assign_mult` + frozen 2021 fits table copy (unit-tested).
- `build_bars_presample.py`: CPU spot-1m -> 4h OHLC per (sym, shift) ->
  `bars_4h_presample.parquet` (resume-safe per-group checkpoint; heartbeat 600 s).
- `build_vol_presample.py`: CPU RV6 + sigma + frozen-GARCH filter ->
  `vol_features_presample.parquet` (resume-safe; heartbeat 600 s).
- `build_ledger_presample.py`: heavy CPU replica (one coin's 1m slice per leg in RAM
  at a time, float32; all fills from same in-RAM arrays) -> `tmp/ledger_presample.npz`
  + `tmp/bt_presample.npy` (resume-safe per-leg checkpoint). Via heavy_slot.
- `run_chronos_presample.py`: GPU inference (torch BEFORE pandas; sys.path pylib;
  revision pinned above; sequential (sym,shift) groups, checkpoint per group,
  heartbeat 600 s) -> `chronos_features_presample.parquet`. Via heavy_slot.
- `compute_tilt_presample.py`: CPU-only join + per-year sums + 1000 timing/block perms
  per variant (numpy; seeds above) -> `tmp/tilt_presample.json`.
- `analyze_presample.py`: CPU-only side-by-side with copied 2021-2026 ->
  `results.json` + `REPORT.md` tables (REPORT written from tables only).
- Deliverables: PLAN.md (this file), tilt_rule.py, build_bars_presample.py,
  build_vol_presample.py, build_ledger_presample.py, run_chronos_presample.py,
  compute_tilt_presample.py, analyze_presample.py, bars/vol/chronos parquets,
  tmp/ledger files, tmp/tilt_presample.json, results.json, REPORT.md,
  tests/test_oc_presampletilt.py (>=1 causality/truncation test + >=1 hand-checked
  synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_presampletilt.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the original
  row stays and the change is a disclosed extra row.)
