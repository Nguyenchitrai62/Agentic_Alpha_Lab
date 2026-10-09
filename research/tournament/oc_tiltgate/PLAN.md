# oc_tiltgate — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_tiltgate.md` +
`docs/opencode/OPENCODE_W_COMMON_20261007.md` (+ AGENTS.md,
OPENCODE_VF_COMMON.md read). Write ONLY
`research/tournament/oc_tiltgate/` + `tests/test_oc_tiltgate.py`.
No GPU, no new packages. Scratch only under
`research/tournament/oc_tiltgate/tmp/`. Engine + ledger extension via
heavy_slot (RAM tight: one engine job at a time). Heartbeat print every
600 s in long jobs.

## Why (from assignment)

oc_voltilt dip-size vol tilts (V_RV6, V_GARCH; same signature as the
foundation-model tilts K2/C2/Toto/TimesFM) time dips well in 2023-2026
(placebo pct 97-100) but not in 2021-2022 (pct 2-19), so they lose the
robust dev pick on the 2021 worst year. Question: does a PARAMETER-FREE
"follow last year" gate, decided at each anchor from data before A - 7 d
only, keep the good regimes and skip the bad ones?

## Frozen inputs (read-only, never edited)

- `research/tournament/oc_voltilt/vol_features_4shift.parquet`
  (risk_RV6 / risk_GARCH per (sym, shift, T); T from 2020-09-30) +
  `fits.json` (V_RV6 / V_GARCH per-anchor direction/q20/q80; all +1).
- `research/tournament/oc_voltilt/tilt_rule.py` (`assign_mult`,
  `anchor_of`; imported read-only, rule bit-identical).
- `research/tournament/oc_voltilt/run_engine.py` (mechanism copied
  verbatim: v414 pipe v321, corr-aware inv sizes kd=1.7, bear books,
  risk budget 0.26*1*1.7, sleeve_gross_cap G=2.0, win_start=5, gate costs
  inside the engine).
- `research/tournament/oc_k2placebo/tmp/ledger.npz` + `bt_all.npy`
  (D0+B1 replica ledger for bars open in [2021-09-24, 2026-09-24);
  read-only reuse; gate n == 22312, base sum5y == 7.718304 +- 0.002).
- `research/tournament/oc_placebo_dip/compute_placebo_dip.py`
  (replica core: imported read-only for the ledger extension).
- `research/tournament/harness.py` (`load()` universe for the 2020-fit
  row-count check).
- `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl` +
  `v421_result.json` row R2B1D17BFG2 (G2 baseline; REF must reproduce
  dev years 0..3 R/DD (2.588/10.86, 3.282/16.91, 6.045/15.81,
  10.677/8.27), Y4 (4.648/12.90) and full-path DD 16.82 to the digit,
  else STOP).

## Gate rule (pre-registered, no free parameter)

Anchors ANCH5 = 2021-09-24 .. 2025-09-24. Year y covers
[A_y, A_y + 365 d) (same `anchor_of` convention as oc_voltilt, all four
shifts).

For anchor A (2021..2025): tilt ON for the whole year [A, A + 365 d)
iff effect(A) > 0 (STRICT; effect == 0 or NaN -> OFF), where effect is
computed over the 12-month window W(A) = [A - 372 d, A - 7 d):

  effect_V(A) = sum_{fills i: T_i in W(A)} (mult_i - 1) * w_i * y10_i
                / n(A),

- fills = dip-rung replica fills (D0 outcomes + B1 sizes), all four
  phases pooled; T_i = bar-open time of fill i; n(A) = number of fills
  with T_i in W(A) (fills with missing feature count in n with
  mult = 1, i.e. contribute 0).
- w_i = deployed B1 weight (1/(1+n_fill)); y10_i = D0 net rung return
  at TP 1.0 sigma (after maker/taker costs + v293 settle funding), so
  w_i * y10_i is the deployed-weighted net rung P&L in w*y units and
  (mult_i - 1) * w_i * y10_i is the tilt's incremental P&L.
- mult_i = `assign_mult` with the fit that WAS live in that prior
  year: for A = 2022..2025, fits.json entry of anchor (A - 1 year)
  (e.g. gate of 2024-09-24 uses the 2023-09-24 fit); risk = risk_RV6
  (G_RV6) or risk_GARCH (G_GARCH); hi/lo = 1.25/0.75; missing/NaN
  risk -> 1. Join key (sym, shift = phase, T) exactly like
  oc_voltilt/compute_placebo.py.
- for A = 2021 the prior fit is a 2020 fit: fit EXACTLY like
  oc_voltilt/make_fits.py (majors rows of harness.load() with
  t_exit < 2020-09-17 AND shift-0 feature present; direction = sign of
  Spearman(risk, y_dep); edges q20/q80) IFF the harness universe has
  enough rows (total rows with t_exit < 2020-09-17 >= 1000); else NO
  fit is attempted and gate = OFF for 2021 (reported as such).
  Expected: 948 total rows < 1000 (checked 2026-10-08 by counting only,
  no outcome) -> 2021 OFF without fitting. The count is recomputed in
  compute_gate.py as a gate; outcome-independent.

Ledger coverage: the k2placebo ledger starts at 2021-09-24, so W(2022)
misses [2021-09-17, 2021-09-24) and W(2021) is fully missing.
extend_ledger.py replays the SAME replica core (imported read-only from
compute_placebo_dip) for bars open in [2020-09-17, 2021-09-24) and
stores tmp/ledger_ext.npz + tmp/bt_ext.npy (same arrays
phase/coin/bar_time/w/y10 + bt datetimes; START epoch identical so
bar_time ordinals are directly comparable). Gate windows then use the
exact [A - 372 d, A - 7 d) range on bar-open times. Fills with
T < 2020-09-30 have no vol feature -> mult = 1 (pre-registered).

Variants (exactly two): G_RV6 (V_RV6 gated), G_GARCH (V_GARCH gated).
Features / fits from oc_voltilt (frozen).

## Engine rows (ONLY these three)

- REF = G2 unchanged (tilt 1).
- G_RV6 = REF + V_RV6 tilt in gate-ON years, tilt 1 in gate-OFF years
  (fits.json V_RV6, anchor-y fit for year y, missing -> 1).
- G_GARCH = same with V_GARCH.
An OFF year is exactly REF by construction (tilt 1 on every rung).
Stages: dev [DEV0=2021-09-24, DEV1=2025-09-24) for all three rows (REF
first; exact-reproduction gate, else STOP); last [DEV0, Y1=2026-09-23)
for all three rows ONCE (every Y4 number labelled scored-once).
No re-runs after outcomes; any change becomes a disclosed extra row.
Where a gated row is bit-identical to an oc_voltilt row over a full
stage (all-ON -> V, all-OFF -> REF), the oc_voltilt cached runs may be
reused; otherwise the gated rows are simulated fully. Per-year reset R
in an OFF (ON) year must equal REF (V) to the digit as a consistency
check.

## Metrics / gates (fixed)

- Gate costs inside the engine: maker 0.0002, taker 0.00055 (stops and
  market exits taker), longs pay 0.0001/8h (00/08/16 UTC), shorts
  nothing. Limits fill only on 1m trade-through, nothing in the first 5
  min after a 4h close (win_start=5); stop-first in a shared 1m bar.
- Per-year 4-phase reset %/mo + DD via `reset_metric.year_reset`; dev4
  geo mean, W (worst-year R), max yearly DD, losing count; 5y geo mean;
  full-path DD via `v388.mix` equal-1/4 mix from 2021-09-24; pooled
  book/rung/all win rates + fills (same collection as oc_voltilt).
- Robust pick among REF / G_RV6 / G_GARCH on dev4 ONLY: DD <= 20, no
  losing dev year; prefer dev4 mean >= 5 %/mo, then highest dev4
  WORST-year monthly return, ties -> higher mean.
- Reference rows V_RV6 / V_GARCH COPIED from oc_voltilt REPORT/
  results.json (dev R, last-year R, placebo pcts) as reference, NOT
  re-run. Expected (frozen): V_RV6 dev [2.271,3.399,6.235,10.848]
  last 4.811; V_GARCH dev [2.398,3.265,6.447,10.571] last 4.932;
  REF dev [2.588,3.282,6.045,10.677] last 4.648.

## Leakage / checks (stated in REPORT)

- Feature timing (RV6: 6 closes <= T; GARCH filter: r[E-1] and earlier
  with per-anchor params from bars closing before A - 7 d; sigma:
  opens <= T; inherited truncation-tested from oc_voltilt).
- Gate timing: W(A) ends at A - 7 d; mult uses the (A - 1 yr) fit whose
  training rows end before (A - 1 yr) - 7 d <= W(A) start; no statistic
  from year [A, A + 365 d) enters the gate for year A.
- Label windows (harness t_exit < anchor - 7 d inherited), fit windows
  (shift-0 only + 7 d embargo, anchor-y fit for year y), fill timing
  (win_start=5 + 1m trade-through + stop-first, engine). No statistic
  from any test year feeds any choice. Dev4 comparison only.

## Compute plan (heavy_slot, resume-safe)

- `gate_rule.py`: pure helpers (`gate_effect`, `decide`) + re-export of
  `assign_mult`/`anchor_of` semantics (unit-tested).
- `extend_ledger.py`: heavy replica replay for [2020-09-17,
  2021-09-24) -> `tmp/ledger_ext.npz` + `tmp/bt_ext.npy` (resume-safe:
  skips if present; heartbeat every 600 s). Via heavy_slot.
- `compute_gate.py`: CPU-only 2020-fit row-count gate + per-anchor
  gate effects (exact windows, prior-year fits) -> `tmp/gate.json`
  (decision per anchor per variant with effect value + n fills).
- `run_engine.py`: sequential shifts per stage, heartbeat every 600 s,
  caches `tmp/runs_dev.pkl` / `tmp/runs_last.pkl` (resume-safe). Via
  heavy_slot.
- `analyze.py`: CPU-only scoring -> `tmp/dev_table.json` +
  `tmp/last_table.json` (incl. OFF==REF / ON==V consistency checks).
- Deliverables: PLAN.md (this file), gate_rule.py, extend_ledger.py,
  compute_gate.py, run_engine.py, analyze.py, tmp/gate.json,
  results.json, REPORT.md, tests/test_oc_tiltgate.py (>= 1
  causality/truncation test + >= 1 hand-checked synthetic case;
  `.venv/Scripts/python.exe -m pytest tests/test_oc_tiltgate.py -q`).

## Post-hoc log

- 2026-10-08 (before any engine outcome; gate decisions computed): the
  ON-year == V consistency check is softened to report-only in
  analyze.py. Reason: an ON year preceded by OFF years starts from the
  REF path state, not the always-on V path state (book positions carry
  across year boundaries), so exact equality need not hold; asserting it
  would abort a valid run. OFF years with all-prior-OFF history remain
  asserted == REF (identical tilt and identical history -> identical
  path). Original rows unchanged; no variant added.
