# oc_btcresid — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_btcresid.md` (= IDEAS8 §1, rank 1) +
`docs/opencode/OPENCODE_W_COMMON_20261007.md` (+ AGENTS.md, OPENCODE_VF_COMMON.md,
`docs/opencode/IDEAS8_20261008.md` §1 + CLOSED rows `oc_xsrev` + `oc_dombook` read in full).
Write ONLY `research/tournament/oc_btcresid/` + `tests/test_oc_btcresid.py`.
Engine / heavy 1m work via `scripts/heavy_slot.py` (one job at a time; gate math is
4h/hourly only, float32 where large). CPU only (no GPU). Heartbeat print every 600 s
in long jobs. Progress print every ~10 min. Scratch only under
`research/tournament/oc_btcresid/tmp/`, never the system temp folder.
GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/rm/commit/switch/rebase/merge.
No orders, no authenticated endpoints, no Kaggle uploads. No inspection outside the
workspace (no /proc).

## Why (IDEAS8 §1, rank 1)

Book concentration crowds one-way market beta (`oc_ddanat_g2`); residual-momentum lit
(OOS 2024-25, net Sharpe 1.44 after beta removal): after removing market beta a residual
momentum effect remains. Trade coin-specific edge, not crowded beta.
CLOSED rows read: `oc_xsrev` (1d cross-sectional-reversal SLEEVE long worst-2 / short
best-2, dollar-neutral gross 1.0x, overlaid 0.25x on R2B1D17BF; lost 5/5, NOT PROMISING)
— that was a NEW ranked sleeve/extra leg; this demeans the EXISTING book weights by BTC
beta, no new signal, no tilt. `oc_dombook` (ONE BTC-dominance LEVEL scaler x1.25/x0.75 on
ALL w_c) — that was a uniform exposure tilt adding size in BTC regimes; this is a
per-coin idiosyncratic demeaning removing crowded beta, plus an exposure-matched
constant control. So kept per the IDEAS8 near-duplicate note.

## Variants (exactly two + reference + two exposure-matched controls, no others)

- REF = G2 unchanged (R2B1D17BFG2, v421: rule inv, k 1.0, kd 1.7, bear True, G 2.0).
- V1 = BTC-residual book, raw beta: per standard-grid 4h bar T,
  `w_resid_c(T) = w_c(T) - beta_c[A(T)] * w_BTC(T)` for all 5 coins c
  (BTC leg: beta_BTC == 1 exactly, so `w_resid_BTC(T) == 0` by construction).
  Applied AFTER the exact v421 bear filter, BEFORE the shifted-clock forward fill.
  Dip untouched.
- V2 = same with beta clipped to [0,1]:
  `b_c = min(max(beta_c, 0), 1)`, `w_resid_c(T) = w_c(T) - b_c[A(T)] * w_BTC(T)`.
- C1 = exposure-matched constant control for V1 (DIAGNOSTIC, in-year, not tradable):
  per anchor year y, `m_C1[y] = mean_T gross_V1(T) / mean_T gross_REF(T)` over
  standard-grid 4h closes T in [A_y, A_y+365d), where
  `gross(T) = sum_c |w_postbear_c(T)|` (post-bear, pre-ffill book rows; NaN->0).
  `w_C1(T) = w_REF(T) * m_C1[anchor_of(T)]` every bar of that year (after bear,
  before ffill). Same C2 with V2 gross. Control uses the in-year realised mean scale
  (per the assignment + `oc_premexpo` in-year-average-exposure lesson) and therefore
  isolates residual TIMING/composition from a mere exposure cut; not a tradable rule.
- Claim rule (frozen): V (V1/V2) "beats exposure" iff dev4 geometric mean R(V) > R(C)
  AND DDmax(V) <= DDmax(C). A residual that trails its control is an exposure story.
- Frozen numbers (never fit): trailing beta window 1y = 372d, 7-day embargo, no other
  threshold/scale. Betas are OLS slopes (frozen round windows, no shrinkage).

## Beta (exact causal definition, frozen, no new parameter)

- Data (read-only, never edited): `research/tournament/ext/hourly_ext.parquet` ONLY
  (columns t, close, sym; t = bar START UTC, bar END = t+1h; majors only).
  No new data (per IDEAS8). If any anchor norm window has <100 overlapping finite
  return pairs for a coin, that coin's beta is NaN->0 that year (disclosed 0, never
  imputed from test data).
- 4h closes on the standard grid G = {00,04,08,12,16,20 UTC}:
  C4(sym,T) = hourly close of the bar starting at T-1h (last bar with END <= T);
  NaN if that hourly bar is missing. Grid 2020-08-04 00:00 .. 2026-09-23 20:00 UTC.
- 4h log return r(sym,T) = log(C4(sym,T)/C4(sym,T-4h)); NaN if either close
  missing/non-positive/non-finite. r(T) uses ONLY closes <= T.
- Beta per anchor A, per coin c != BTC:
  pairs {(r_c(T), r_BTC(T)) : T in [A-372d, A-7d), both finite} on the standard grid;
  require >= 100 pairs AND sum((r_BTC-mean)^2) > 0, else beta = NaN -> 0.0.
  `beta_c(A) = sum((x-xb)(y-yb)) / sum((x-xb)^2)` with x = r_BTC, y = r_c
  (OLS with intercept, same ddof top/bottom). BTC: beta == 1.0 exactly (never estimated).
  Year y=[A, A+365d) uses beta(A) on all four phase shifts. No test-year statistic
  feeds any beta.
- Residual at book-bar T (standard grid; engine forward-fills books to holding bars
  with the same causal ffill, so the residual sees exactly the state the books saw):
  w = post-bear book row (NaN->0.0, exactly as the engine's fillna(0.0));
  wBTC = w["BTCUSDT"]; w_resid_c = w_c - b_c * wBTC with b from anchor_of(T)
  (V1 raw b = beta incl. negative/>1; V2 b clipped [0,1]; beta NaN->0.0).
  Rows with T < 2021-09-24 are never adjusted (frozen; w_resid = w).
  w_resid uses ONLY close-known weights + pre-anchor betas (leakage note in IDEAS8).

## Members / signals (frozen, no retraining)

- Book weights = `scripts/forward_v205.py:research_books_d2(eu)` =
  0.8 x O1 (v240 order-level whale+TV: member_A/Aq_O1_orders + member_B/Bq_tv) +
  0.2 x (D+Dq)/2 (Coinbase-premium v144+v111+v285 / quarterly v202),
  union index, missing->0.0 — loaded READ-ONLY from `eu.er.CACHE`
  (artifacts/research/engine_real). No retraining, no new fit, no label change.
  Member builders cited: v92 pooled HGB, v94 horizons, v233 T3 TV, v236 W2 whale,
  v240 O1 orders, v144+v111+v285 D-premium, v202 quarterly Aq/Bq/Dq.
- This idea is NOT a retraining idea, so no per-anchor training run exists; the
  builder-reproduction check is vacuous here and is stated as such: the pipeline
  loads the cached members unchanged (no code path edits them). Any future retrain
  would reproduce cached members <1e-12 first (v233/v286/v287/v288/v312 pattern).

## Engine (fixed; per-bar book-row copy of v421/spillgate mechanism)

- v414 pipe v321, corr-aware inv sizes kd=1.7, bear books built EXACTLY as v421
  (`btc = _opens_std["BTCUSDT"].reindex(books154.index)`,
  `bear = (btc < btc.rolling(1200, min_periods=600).mean())`,
  `sb.loc[bear] = sb.loc[bear].where(sb<=0, sb*0.5)`), risk budget 0.26*1*1.7,
  sleeve_gross_cap G=2.0, win_start=5, gate costs inside the engine (maker 0.0002,
  taker 0.00055 incl. SL/timeout, longs pay 0.0001/8h, shorts 0; limit fill only on
  1m trade-through; nothing in first 5 min after a 4h close; stop-first in shared
  1m bar — engine handles).
- Residual/controls applied AFTER the bear filter, BEFORE the shifted-clock forward
  fill, on the standard grid: `sbb_V = resid(sb_std, beta[anchor])`;
  `sbb_C = sb_std * m_C[anchor_of(T)]` per-row constant. Dip `tilt(i,a)` = 1.0 for
  ALL five rows (book-side idea; dip sleeve untouched).
- Rows run through the engine (ONLY these five): REF, V1, V2, C1, C2.
- Stages: stage dev runs [DEV0=2021-09-24, DEV1=2025-09-24) for the five rows
  (REF first; must reproduce v421 G2 years 0..3 R/DD to the digit, else STOP).
  Stage last runs [DEV0, Y1=2026-09-23) ONCE for REF + the dev4 robust pick + its
  matched control ONLY (every Y4 number labelled scored-once; REF Y4 must reproduce
  v421 G2 Y4 to the digit). No re-runs after seeing outcomes; any change becomes a
  disclosed extra row.
- Long jobs: `heavy_slot run --tag oc_btcresid ...` + `nohup ... > tmp/<log> 2>&1 &`
  + poll the log; heartbeat every 600 s.

## Metrics / gates (fixed)

- Gate costs as above (inside engine).
- Per-year 4-phase reset %/mo + DD via `reset_metric.year_reset`; dev4 geo mean,
  W (worst-year R), max yearly DD, losing count; 5y geo mean (years 0..4 on stage-last
  runs); full-path DD via `v388.mix` equal-1/4 mix from 2021-09-24 (max of reset DDs
  and full-path for the gate); pooled book/rung/all win rates + fills/year +
  realised mean gross scale m per variant-year + BTC-leg zero check (same collection
  as oc_spillgate/run_engine.py; dip tilt mult reports 1.0); fee/funding split.
- Robust pick on dev4 ONLY among V1/V2 (controls are diagnostics, REF is baseline):
  eligible iff DDmax <= 20 and no losing dev year; prefer dev4 mean >= 5 %/mo, then
  highest dev4 WORST-year monthly return, ties -> higher mean. (If none eligible, pick
  = "none-eligible" and the last stage runs REF only.)
- G2 baseline to reproduce (v421_result R2B1D17BFG2): dev
  [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27)], Y4 (4.648/12.90),
  5y 5.410, full-path DD 16.82. Reproduce REF to the digit first, else STOP.

## Leakage / checks (stated in REPORT)

- Feature timing (4h closes <= T only; r(T) ends <= T; residual-bar's own future flow
  never used; truncation-tested in tests/test_oc_btcresid.py); label windows (no
  labels fit; betas are unsupervised OLS slopes); fit windows (betas from
  [A-372d,A-7d) per anchor, 7d embargo, frozen per year, no statistic from any test
  year feeds any choice); fill timing (win_start=5 + 1m trade-through + stop-first,
  engine). Gate costs inside the engine. w_BTC is the close-known post-bear weight.

## Compute plan (heavy_slot, resume-safe)

- `resid_rule.py`: pure helpers (`ols_beta`, `clip01`, `resid_row`, `anchor_of`,
  `control_mult`) — no data access; unit-tested.
- `compute_beta.py`: hourly -> 4h closes (float32) -> 4h log returns -> per-anchor
  betas `betas.json` {anchor: {coin: beta}} -> residual diagnostics + control
  constants `controls.json` {m_C1/m_C2 per anchor + realised gross means}.
  CPU-only; via heavy_slot (hourly parquet > 0.4 GB working set). Resume-safe
  per-step caches in tmp/.
- `check_g2.py`: f=0-style reproduction assert (v421_runs.pkl + reset_metric) to digit.
- `run_engine.py`: sequential shifts per stage, heartbeat every 600 s, caches
  `tmp/runs_dev.pkl` / `tmp/runs_last.pkl` (resume-safe). Via heavy_slot, one job,
  nohup + log.
- `analyze.py`: CPU-only scoring of stage-dev (reset metric + v388.mix + wins) ->
  `tmp/dev_table.json`; `analyze_last.py`: stage-last ONCE (pick + matched control +
  REF) -> `tmp/last_table.json` (+ 5y means + full-path DD).
- Deliverables: PLAN.md (this file), resid_rule.py, compute_beta.py, check_g2.py,
  run_engine.py, analyze.py, analyze_last.py, results.json, REPORT.md,
  tests/test_oc_btcresid.py (>=1 causality/truncation test + >=1 hand-checked
  synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_btcresid.py -q`).

## Post-hoc log

- 2026-10-08 (pre-outcome): `compute_beta.py` indexing bug (`m.to_numpy()` on an
  ndarray mask) fixed; no outcome had been computed; definitions unchanged.
- 2026-10-08 (post dev outcomes): `run_engine.py` extended to ALSO record the
  engine's own `stats` dict (fees/funding/fills; no rule or engine-input change);
  dev + last stages re-run, new runs verified bit-identical (equity + wins) to the
  backed-up first runs (`tmp/*.equitybak.pkl`). Original rows stay, no new variant.
  (empty otherwise; any further change after an outcome is logged here with date +
  reason; the original row stays and the change is a disclosed extra row.)
