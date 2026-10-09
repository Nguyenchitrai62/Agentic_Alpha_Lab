# oc_b7c2 — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_b7c2.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, docs/opencode/OPENCODE_VF_COMMON.md read in full).
Write ONLY `research/tournament/oc_b7c2/` + `tests/test_oc_b7c2.py`. Scratch only under
`research/tournament/oc_b7c2/tmp/`. GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/
rm/commit/switch/rebase/merge. Engine / heavy 1m work via `scripts/heavy_slot.py` (RAM tight: one engine
job at a time, load one coin at a time where applicable). Long jobs: nohup + log file under tmp/, poll
the log. Heartbeat print every 600 s in long jobs. Progress print every 10 minutes.

## Why

B7 (`research/tournament/oc_cascadeboost`: dip budget x1.5 for 7 days after a > 4 sigma 4h move) acts on
WHEN to add dip capital; C2 (`research/tournament/oc_chronos`: rung size x1.25 / x0.75 by Chronos
downside quantile) acts on WHICH rungs get more. Different mechanisms — the stack may be additive.
B7 dev4: mean 6.738, WORST 2.955, DDmax 17.92 (pick over B3/REF). C2 dev4: mean 5.739, WORST 2.711,
DDmax 15.48 (dev4 robust pick over K2/C2K2, informational). Both are pure dip-sizing tilts; the book
leg stays byte-identical to G2 and the dip gross cap 2.0 still binds, so the stack is bounded.

## CONTAMINATION LABEL (pre-registered, from the assignment)

Both components were already scored on the post-release year (B7 also contaminated, see
oc_cascadeboost: idea formed after seeing the delay replica incl. the post-release year) -> every
post-release-year (2025-09-24 .. 2026-09-23) number in this study is a LABELLED DIAGNOSTIC (not clean
evidence); selection on dev4 ONLY (anchors 2021-2024). Only prospective paper could confirm.
This label is stated here BEFORE any outcome and repeated in REPORT.md / results.json.

## Variants (exactly two + reference/copies; no other variant, no tuning)

- REF = G2 unchanged (dip mult 1) — engine reproduction row (v421 R2B1D17BFG2).
- B7 = COPY from oc_cascadeboost (dip budget x1.5 for 7d after cascade bar; market-wide per shift).
  Not rerun on base; numbers copied to the digit from oc_cascadeboost REPORT/results.json + tmp tables.
- C2 = COPY from oc_chronos (rung x1.25 / x0.75 outer quintiles of risk = -ch_q10, per-anchor fits).
  Not rerun on base; numbers copied to the digit from oc_chronos REPORT/results.json.
- B7C2 = REF + BOTH multipliers applied as a PRODUCT: m(sym,T,shift,y) = m_B7(T,shift) * m_C2(sym,T,y).
- B7C2_cap = product CLIPPED: m = min(m_B7 * m_C2, 1.5).
- The dip gross cap 2.0 and every other G2 limit still bind (kw["sleeve_gross_cap"] = 2.0, unchanged).
  Book untouched in both stack variants.
- Stack multiset: B7C2 in {0.75, 1.0, 1.125, 1.25, 1.5, 1.875}; B7C2_cap in {0.75, 1.0, 1.125, 1.25, 1.5}.
  (m_B7 in {1.0,1.5}, m_C2 in {0.75,1.0,1.25}.)

## Frozen inputs (read-only, never edited, never refit)

- `research/tournament/oc_cascadeboost/boost_mult_4shift.parquet` (shift,T,mult_B7/mult_B3; B7 col only
  used here; union triggers per shift 264/266/263/255; closes-only |r|>4*SIG(540,min120), tc=T+4h,
  window (tc,tc+7d] market-wide per shift — VERBATIM oc_cascadedelay/oc_cascadeboost, no recompute).
- `research/tournament/oc_chronos/chronos_features_4shift.parquet` (sym,shift,T,ch_q10 + others;
  258,085 rows; ch_q10 only used here; context = last 512 closes ending at bar closing at T).
- `research/tournament/oc_chronos/fits.json` (per-anchor direction +1 all five anchors, q20/q80 of
  risk = -ch_q10; anchor-2025 fit for the post-release year; shift-0 + 7d embargo inherited).
- `research/tournament/oc_cascadeboost/REPORT.md` + `results.json` + `tmp/dev_table.json` +
  `tmp/last_table.json` (expected B7 numbers for the copy gate).
- `research/tournament/oc_chronos/REPORT.md` + `results.json` (expected C2 numbers for the copy gate).
- `research/tournament/oc_chronos/run_engine.py` + `tilt_rule.py` and
  `research/tournament/oc_cascadeboost/run_engine.py` + `boost_rule.py` (mechanism copied verbatim;
  only the dip mult lookup becomes the frozen product / capped product).
- `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl` + `v421_result.json` row
  R2B1D17BFG2 (G2 baseline: dev years [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27)],
  Y4 (4.648/12.90), 5y 5.410, max yearly DD 16.91, full-path DD 16.82) — engine stage only.
- `research/tournament/oc_c2bybit/compute_c2bybit_engine.py` + `analyze_c2bybit.py` (S5 Bybit harness
  copied verbatim; only the dip mult lookup becomes the stack product; S5 = Bybit 1m from 2021-11-15).
- `data/raw/bybit_linear_1m_20261004/<SYM>_1m.parquet` (S5 only).

## Mechanism (exact copy of oc_chronos/run_engine.py = oc_cascadeboost/run_engine.py = v414 pipe v321)

- 4 phases (shifts 0..3, 4h grid opens at s,s+4,... UTC); pipe v321 via phase_offset_full.pipe_setup;
  corr-aware dip sizes mult 1/(1+n)*1.7*tilt*base (n = coins with C<=O*(1-2.5*sig)); risk_mult 1.0;
  sleeve_risk_budget 0.26*1*1.7; sleeve_gross_cap G=2.0; bear books (BTC 4h open < 1200-bar mean halves
  LONG targets; standard rows, before shifted-clock ffill).
- Gate costs inside the engine: maker 0.0002, taker 0.00055 (stops/market taker), longs pay 0.0001/8h,
  shorts 0. Limits fill only on 1m trade-through, nothing in the first 5 min after a 4h close
  (win_start=5); stop-first in a shared 1m bar (engine handles).
- Dip leg: rung size x m_stack (product or capped product as above); book leg byte-identical to G2.
- Stack lookup per dip sizing (i,a): T = holding-bar open on that shift's grid; y = anchor year of T;
  m_B7 = 1.5 iff boosted_B7(T,shift) else 1.0 (exact (shift,T) match, fallback latest grid time <= T
  ffill causal, missing -> 1.0, same as oc_cascadeboost); m_C2 = assign_mult(-ch_q10(sym,T),
  dir_y, q20_y, q80_y, 1.25, 0.75), missing/NaN -> 1.0 (same as oc_chronos, fits of anchor y applied
  to all four shifts in year y); m_B7C2 = m_B7*m_C2; m_cap = min(m_B7C2, 1.5).
- S5 Bybit: identical except 1m source = bybit_minutes() from the Bybit dir, live0 = 2021-11-15+shift,
  standard index filtered to >= 2021-11-15 before shift (year 2021 = SHORT window, labelled everywhere),
  win_start=5. Same stack lookup.

## Stages (fixed; all engine via heavy_slot, one job at a time, resume-safe)

- Stage dev runs [DEV0=2021-09-24, DEV1=2025-09-24): rows REF, B7C2, B7C2_cap (REF first; must reproduce
  v421 G2 years 0..3 R/DD to the digit AND B7/C2 copy numbers must match their frozen sources to the
  digit at scoring time, else STOP). Cache tmp/runs_dev.pkl; heartbeat every 600 s.
- Stage last runs [DEV0, Y1=2026-09-23) ONCE for REF + B7C2 + B7C2_cap (no re-runs after outcomes; any
  change becomes a disclosed extra row). Determinism check: dev segments of stage-last equal stage-dev.
  REF Y4 must reproduce v421 G2 Y4 (4.648/12.90) to the digit. Every Y4 number LABELLED scored-once
  DIAGNOSTIC (contaminated, see top). Cache tmp/runs_last.pkl.
- Stage S5 runs full window on Bybit prices [2021-11-15+shift, Y1+shift) ONCE for REF, B7, B7C2,
  B7C2_cap (superset; report REF / B7 / dev4-pick per assignment; B7_S5 is a fresh engine row, REF_S5
  must reproduce oc_c2bybit REF_S5 to the digit else STOP). Cache tmp/runs_S5.pkl.
- No re-runs after seeing outcomes; any change becomes a disclosed extra row.

## Metrics / selection (fixed)

- Per-year 4-phase reset %/mo + DD via `reset_metric.year_reset`; dev4 geo mean, W (worst-year R), max
  yearly DD, losing count; 5y geo mean; full-path DD via `v388.mix` equal-1/4 mix from 2021-09-24
  (max of marked/close; gate uses max of yearly DDs and full-path); worst 1m-marked DD episode per row
  (peak/trough/depth on dd(t) = 1 - ms(t)/peak(es)(t)); pooled book/rung/all win rates + fills/year +
  sized mean stack multiplier + boosted share.
- Rows reported: REF, B7 (copy), C2 (copy), B7C2, B7C2_cap — dev4 per year / mean / WORST / DD,
  5y, full-path DD, worst 1m-marked episode, post-release year (labelled diagnostic).
- Robust pick on dev4 ONLY among REF / B7 / B7C2 / B7C2_cap (NOT C2 — C2 is a copy-only reference):
  DD <= 20 and no losing dev year; prefer dev4 mean >= 5 %/mo, then the highest dev4 WORST-year
  monthly return, ties -> higher mean.
- S5 rows: same metrics on Bybit prices for REF / B7 / the dev4 pick (plus the non-picked stack row
  disclosed for completeness; selection does NOT use S5).
- Reproduction gates (STOP if failed): REF dev 0..3 == v421 G2 to the digit, REF Y4/5y/full ==
  v421 G2 to the digit; B7 copy == oc_cascadeboost B7 (dev 2.955/14.67, 3.264/17.92, 8.537/15.94,
  12.486/11.01, mean 6.738, W 2.955, DDmax 17.92, full-dev 17.75; Y4 4.88/13.81; 5y 6.364, full 17.75);
  C2 copy == oc_chronos C2 (dev 2.711/11.52, 3.460/15.48, 6.250/15.07, 10.721/8.29, mean 5.739,
  W 2.711, DDmax 15.48, full-dev 15.42; Y4 4.754/12.86; 5y 5.542, full 15.42); REF_S5 ==
  oc_c2bybit REF_S5 (dev4 4.994/W 2.129/maxDD 18.11; 5y 4.883/full 18.09; y2021 SHORT window labelled).

## Leakage / checks (stated in REPORT)

- Feature timing (B7 triggers: closes with close_time <= tc only; SIG window excludes the tested bar;
  boost window strictly after tc (0 < T-tc <= 7d); C2 forecast for T uses only 512 closes of bars
  closing <= T; stack lookup uses only (sym,shift,T) at the holding bar; truncation-tested in
  tests/test_oc_b7c2.py: recompute stack mults from truncated frozen tables -> identical on kept
  prefix; multiset check), label windows (B7: no labels fit anywhere; C2: harness t_exit < A - 7d
  inherited, not recomputed), fit windows (B7: no fits, frozen threshold/windows/N/boost; C2:
  frozen fits.json shift-0 only + 7d embargo, year y uses anchor-y fit only, never a later anchor; no
  statistic from any test year feeds any choice), fill timing (win_start=5 + 1m trade-through +
  stop-first; perms n/a here; S5 same with Bybit minutes), gate costs inside the engine.
- Coverage: disclose any skipped anchor year (none expected; missing boost history -> 1.0, missing
  ch_q10 -> 1.0, counted and disclosed with sized-mean multipliers).

## Compute plan (heavy_slot only for engine, resume-safe)

- `stack_rule.py`: pure helpers (`assign_c2` copy of tilt_rule.assign_mult, `stack_mult(m_b7, m_c2)`,
  `stack_mult_cap(..., cap=1.5)`, `anchor_of`) — no data access; unit-tested.
- `run_engine.py`: base 4-phase engine (REF/B7C2/B7C2_cap, --stage dev/last, --shifts, --rows) — same
  shape as oc_cascadeboost/run_engine.py + oc_chronos/run_engine.py, mult lookup = frozen product.
- `compute_s5_engine.py`: S5 Bybit engine (REF/B7/B7C2/B7C2_cap, --shifts, --rows) — same shape as
  oc_c2bybit/compute_c2bybit_engine.py, mult lookup = frozen product (+ B7-only branch for the B7_S5 row).
- `analyze.py`: CPU-only scoring (reset metric + v388.mix + wins + worst 1m-marked episode) ->
  `tmp/dev_table.json`, `tmp/last_table.json`, `tmp/s5_table.json`; REPORT.md + results.json written
  from those tables only (B7/C2 rows copied from frozen sources, asserted equal).
- Deliverables: PLAN.md (this file), stack_rule.py, run_engine.py, compute_s5_engine.py, analyze.py,
  results.json, REPORT.md, tests/test_oc_b7c2.py (>=1 causality/truncation test + >=1 hand-checked
  synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_b7c2.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the original row stays and
  the change is a disclosed extra row).
