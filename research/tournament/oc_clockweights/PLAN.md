# oc_clockweights PLAN (FROZEN before any outcome — 2026-10-08)

## Idea (IDEAS6 #6, rank 6, prior 8%)
`oc_phasedisp` singles disperse 3.10–6.92 %/mo: fixed 1/4 capital overfunds the
cold clock. Re-weight HOW capital is shared across the 4 phase clocks; signals,
rungs, SL/TP, fills untouched. No veto/gate/filter.

## Pre-registered variants (ONLY these two)
- V1 `invDD`: at each anchor, weight ∝ 1 / trailing-1y max-DD (marked), sum 1.
- V2 `sharpe`: at each anchor, weight ∝ max(trailing-1y Sharpe, 0), sum 1.
No other variant. No post-hoc variant unless added as disclosed extra row.

## Fixed data + grid (read-only, never edited)
- `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl`,
  strat `R2B1D17BFG2` only. Each phase value = {t, eq, eq_min} on 4h-close grid.
- Helpers (import read-only): `v388_bot_stop_distance.py` (ANCH, Y1, hourly()),
  `research/diagnostics/r2_decompose5/reset_metric.py` (year_reset logic).
- Hourly grid via `v388.hourly()` exactly: g0 = 2021-09-24 04:00 UTC,
  g1 = Y1 + 12h = 2026-09-23 12:00 UTC, 1h ffill, fillna 1.0,
  mn = min(lo, e), lo indexed at t−4h.
- Anchors A_y = 2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24, 2025-09-24
  (00:00 UTC). Year y = (A_y, A_y + 365d]. Dev = y 0..3; post-release y=4
  scored ONCE for the dev4 robust pick + REF only (labelled).

## Fixed causal rule (embargo 7d, frozen all year)
- Trailing window for anchor A_y: W_y = [A_y − 7d − 365d, A_y − 7d], snapped to
  hourly grid (rows with grid time in W_y). Uses ONLY rows ending ≤ A_y − 7d.
  No intra-year update: weights w(y) frozen for the whole year segment.
- y=0 (2021-09-24): no trailing history exists (grid starts g0) → equal 1/4.
  Rule: if usable trailing rows < 2400 h (~100 d), fallback to equal 1/4.
- V1 trailing max-DD per phase s: slice E_s, M_s to W_y, rebase by
  b = E_s at last grid ≤ W_y start (1.0 if none), es = E/b, ms = M/b,
  DD_s = 100·max(1 − ms / running-max(es)), clipped to [1.0, 100] before
  inversion (floor binds only near-zero DD; avoids 1/0). w_s = (1/DD_s)/Σ(1/DD).
- V2 trailing Sharpe per phase s: hourly simple returns r = E(t)/E(t−1) − 1 on
  W_y grid (ffill series, drop first NaN). Sharpe_s = mean(r)/std(r,ddof=1) ·
  sqrt(8760); std=0/NaN/non-finite → 0. w_s = max(Sharpe_s,0)/Σ; if Σ ≤ 0
  (all ≤ 0) → equal 1/4. Weights ≥ 0, Σ = 1 exactly (renormalised), no leverage,
  no short clock.
- Sum-to-1 (no leverage) asserted in code (<1e-12).

## Fixed harness (overlay accountant + reset metric, NO engine rerun)
- Per-year reset metric (weighted): for year y, per phase b_s = E_s at last
  grid ≤ A_y; E4_s = E_s[seg]/b_s, M4_s = M_s[seg]/b_s; es_w = Σ_s w_s(y)·E4_s,
  ms_w = Σ_s w_s(y)·M4_s; R_y = 100·(es_w_end^(1/12) − 1);
  DD_y = 100·max(1 − ms_w/running-max(es_w)) (same pk convention as year_reset,
  no prepended 1.0). REF (equal 1/4) must reproduce v421_result G2 years,
  R=5.41, W=2.588, DD=16.91, full=16.82 TO THE DIGIT or stop and report.
- Continuous full-path (for DD gate): stitch yearly weighted segments with
  compounding: A_anchor(0)=1.0; A(t)=A_anchor(y)·es_w_seg(t),
  M(t)=A_anchor(y)·ms_w_seg(t); A_anchor(y+1)=A_anchor(y)·es_w_seg(end).
  Full-path DD = max(close DD on A, marked DD on M vs running peak of A) from
  2021-09-24, v421 convention. 5y/dev4 means = geometric means of yearly
  monthlies: 100·(Π(1+R/100)^(1/n) − 1).
- Overlay is exact at 1x under linear sizing (positions/fees/funding scale with
  capital; signals and fills unchanged). Engine re-run ("confirm") NOT executed:
  would need per-year-weighted 4-phase 1m engine; user trade rules (limit
  entries maker 0.0002, SL market taker 0.00055, TP limit maker 0.0002,
  trade-through, minute-0–4 ban, stop-first, expiry no market fallback) are
  preserved by construction (stored G2 equity already embeds them; no new
  orders, no fill-timing change). Fee/funding splits and win rates are NOT in
  v421_runs.pkl (t/eq/eq_min only) → reported N/A with reason; engine confirm
  would be needed for those.
- LIGHT: one process, hourly grid only (~44k rows × 4), no 1m, no GPU, no
  heavy_slot (expected < 0.4 GB).

## Fixed selection + report
- Compare V1 vs V2 ONLY on dev4 (y 0..3). Robust: eligible = dev DD ≤ 20 every
  year AND no losing dev year; prefer dev4 mean ≥ 5; among those highest dev4
  WORST; ties → higher mean. If none ≥ 5, same ordering among eligible. If none
  eligible, pick highest WORST (disclosed fallback).
- Score y=4 ONCE for the dev4 winner + REF only; loser y=4 = NOT_SCORED.
- Outputs: `compute_clockweights.py`, `results.json`, `REPORT.md` (per-year
  table, dev4 pick, 5y REF-labelled, full-path DD, fee/funding N/A note,
  leakage checklist, 3-line Vietnamese verdict), `tests/test_oc_clockweights.py`
  (causality/truncation + synthetic hand-check). Run pytest on the test file.

## Leakage notes (pre-registered)
Weights use pre-anchor trailing window only (ends A−7d), never the test year.
Sum 1, no leverage. Feature timing: hourly closes known at close. Fill timing:
unchanged from G2 engine (minute-5 ban, trade-through, stop-first kept).
Fit windows: trailing W_y only. If anything changes post-outcome, original row
kept + change as disclosed extra row.
