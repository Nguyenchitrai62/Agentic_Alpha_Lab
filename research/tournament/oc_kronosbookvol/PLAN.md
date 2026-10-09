# oc_kronosbookvol — PLAN (pre-registered BEFORE any outcome is computed)

Assignment: docs/opencode/OPENCODE_W_oc_kronosbookvol.md + docs/opencode/OPENCODE_W_COMMON_20261007.md.
Kronos 4-shift features VERIFIED COMPLETE before starting: 20/20 (shift, sym) groups
(BTC/ETH/BNB/XRP ~13069-13070 rows each, SOL ~12804-12805 — later listing; T 2020-10-06 .. 2026-09-23).
G2 baseline REPRODUCED from cache before any outcome: v421 R2B1D17BFG2 =
R 5.41 / max-yearly-DD 16.91 / full-path-DD 16.82; dev4 Rs [2.588, 3.282, 6.045, 10.677]
geo 5.601 / W 2.588 / DD 16.91; last year R 4.648 / DD 12.9.

## Hypothesis

Kronos-small's zero-shot volatility forecast beats trailing sigma on dev
(rng1 IC 0.19-0.28 vs 360-bar sigma 0.05-0.12, only +0.01..+0.06 over a 42-bar
trailing std). Earlier book vol-sizing (v129 small gain; v251 rejected) used trailing
estimators. Inverse forecast-vol scaling of the BOOK (both long and short) should
cut book drawdown at small return cost. CAVEAT (assignment): dev years are probably
inside Kronos pretraining (released 2025-08) -> dev = UPPER BOUND; the most recent
year 2025-09-24 .. 2026-09-23 is post-release = the clean test. Kronos must beat the
cheap trailing baseline (CTRL) to claim value.

## Inputs (read-only, never edited)

- Kronos: research/tournament/oc_kronoshidden/kronos_features_4shift.parquet
  (sym, shift, T, sigma, C0, er1, er6, vol1, vol6, rng1, low1, pdrop2, pdrop3).
  Feature at bar open T uses only bars closed <= T (oc_kronoshidden PLAN).
- CTRL bars: research/tournament/oc_kronoshidden/bars_4h_4shift.parquet
  (sym, shift, T, open, ..., nmin). Only 3 incomplete bars exist (SOL first bars,
  nmin 60/120/180); CTRL requires nmin == 240 else missing.
- Reference: research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl
  strat R2B1D17BFG2 (rule inv, k 1.0, kd 1.7, bear True, G 2.0) + v421_result.json.
- Engine: v321 BOT pipe via research/diagnostics/phase_offset_full (same kw/trade
  as v421 worker: corr-aware dip sizes rule inv kd 1.7, risk_mult k 1.0,
  sleeve_risk_budget 0.26*k*kd, sleeve_gross_cap G 2.0, bear-filtered books,
  win_start 5, gate costs). Copy of v426_book_brake.py structure (per-(T,sym)
  multiplier -> simulate), adapted per-shift below.

## Rule (fixed; 4-phase engine on top of G2)

Base path per phase s (identical to v421): sb = bear-filtered standard books
(research_books_d2, BTC < 1200-bar MA -> longs x0.5), books_bear_s = sb ffill to
idx_s = books154.index + s hours. v426 applied its gate on STANDARD rows before the
ffill; Kronos rows live on SHIFT-s grids, so the per-shift analogue is applied ON THE
PHASE GRID: books_scaled_s = books_bear_s * m_s, elementwise per (idx row t, sym),
BOTH long and short. Dip leg, costs, funding, fills unchanged (engine handles:
maker 0.0002, taker 0.00055, longs pay 0.0001/8h, limits fill only on 1m
trade-through, no fill first 5 min after a 4h close, stop-first in shared 1m bar).

- KV1: f = vol1 (Kronos forecast-vol, sigma units).
- KV2: f = rng1 (Kronos forecast range, sigma units).
- CTRL: f = sigma42/sigma (cheap baseline; sigma = rolling-360 std and
  sigma42 = rolling-42 std of diff(log open), per (shift, sym) on bars_4h_4shift,
  same math as run_inference_4shift.py; ratio undefined when sigma missing/<=0).
- m(t, sym; y, s) = clip(median_train(y, s, sym) / f(t), 0.6, 1.4).
  median_train = median of f over training rows of anchor A_y: Kronos/CTRL rows
  with T < A_y - 7d, SAME shift s and SAME sym ("same sym" + shift isolation so each
  phase is self-contained), finite and > 1e-12 (CTRL additionally nmin == 240).
  Feature lookup: latest row with T <= bar open t (merge_asof backward; in practice
  exact T == t except the last few idx_s past Kronos coverage, which ffill the last
  row — still T <= t). Missing/non-finite/f <= 1e-12, or empty/non-positive median
  -> m = 1.0. Rows before 2021-09-24+sh use anchor-0 fits (engine live starts there).

## Rows (ONLY these; G2 from cache, no rerun)

- G2 = v421 R2B1D17BFG2 cached (reproduced above; bit-exact reference).
- KV1, KV2, CTRL as defined above. No other variant, no tuning.

## Two-stage execution (most-recent-year-ONCE)

- Anchors A = 2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24 (dev4),
  2025-09-24 (last). Year y on phase s = [A_y+sh, min(A_y+365d+sh, live1)).
- STAGE 1 (dev): full 4-phase runs for KV1 + KV2 with live1 = 2025-09-24+sh
  (last year never simulated, never scored). Score dev4 via reset_metric.year_reset
  per anchor + yearly DD + dev full-path DD (v388.mix continuous from 2021-09-24).
  Choose KV1 vs KV2 on dev4 ONLY by the robust criterion below. Freeze the choice.
- STAGE 2 (once): full-period 4-phase runs (live1 = 2026-09-23+sh, v388 precedent so
  positions carry across the dev boundary) for the CHOSEN row + CTRL, scored ONLY on
  the last year (reset_metric year 4 + yearly DD) plus full-path DD over the full
  path; G2 last-year/full-path from cache. Dev years recomputed in stage-2 runs are
  a determinism check only (must match stage 1 to 1e-9) and cannot change the choice.
  If no KV row is eligible, chosen = none and stage 2 runs CTRL only (+ G2 cached).
- Heavy runs through scripts/heavy_slot.py (never --leader); per-phase cache in
  tmp/ so a killed phase resumes without recompute.

## Decision rule (robust criterion, dev4 only for KV1 vs KV2)

Eligible: dev4 max-yearly-DD <= 20 AND no losing dev year. Among eligible prefer
dev4 mean >= 5 %/month; among those (or among all eligible if none >= 5) pick the
highest dev4 WORST-year monthly return; ties -> higher dev4 mean. Verdict on the
most recent year (clean evidence): Kronos claims value only if the chosen KV row
beats CTRL and is not worse than G2 on risk; final 3-line Vietnamese verdict
(adopt / reject / needs prospective evidence) in REPORT.md.

## Leakage / causality checks (stated in REPORT.md)

Feature timing (Kronos T uses bars closed <= T; lookup T <= bar open t; books ffill
r <= t_s with r decided at r+4h <= t_s+4h as deployed); label windows N/A (no fitted
labels); fit windows (medians use only T < A_y - 7d, per (shift, sym)); fill timing
(engine win_start 5, trade-through, stop-first — untouched). Tests prove phase s
sees only shift-s rows with T <= its bar open.

## Outputs

research/tournament/oc_kronosbookvol/: PLAN.md (this file), compute_kronosbookvol.py
(engine + multipliers), results.json, REPORT.md (per-year %/mo + DD + trades/win +
mean |m-1|, what failed, 3-line Vietnamese verdict). tests/test_oc_kronosbookvol.py:
causality/truncation + hand-checked synthetic multiplier cases. No commits.
