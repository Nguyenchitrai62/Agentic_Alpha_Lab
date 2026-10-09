# oc_c2frontier — PLAN (pre-registered 2026-10-08, BEFORE any outcome)

Assignment: `docs/opencode/OPENCODE_W_oc_c2frontier.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md read). Write ONLY `research/tournament/oc_c2frontier/`
+ `tests/test_oc_c2frontier.py`. Engine via heavy_slot (one job at a time; RAM tight).
Heartbeat print every 600 s. Scratch only under `research/tournament/oc_c2frontier/tmp/`.

## Question

Does the Chronos C2 dip tilt move the BOT return/drawdown frontier outward (DD < 15 goal)?
Context (given, read-only): BOT overlays move along one frontier; DD < 15 only at
~4.97 %/mo (D13BF, dip-mult 1.3, frontier map). C2 (oc_chronos) lowered G2's full-path
DD by 1.4 pp at +0.13 %/mo. If the frontier shifts, a lower dip-mult + C2 might give
>= 5 %/mo with DD < 15.

## Frozen inputs (read-only, never edited)

- `research/tournament/oc_chronos/chronos_features_4shift.parquet` (sym, shift, T, ch_q10).
- `research/tournament/oc_chronos/fits.json` (C2 fits, all direction +1):
  2021 q20 1.110054237503456 q80 2.8608138206510407; 2022 1.1847269503398057 / 3.0250640748629083;
  2023 1.0735691511209666 / 2.773698097596179; 2024 1.0644316852926394 / 2.65023108446202;
  2025 1.0742922959916594 / 2.5976577907281015. C2 mult hi=1.25 / lo=0.75, missing -> 1.
- `research/tournament/oc_chronos/REPORT.md` + `results.json` + `tmp/dev_table.json` +
  `tmp/last_table.json` (expected G2 / G2+C2 numbers, reproduction reference).
- `research/tournament/oc_chronos/run_engine.py` + `tilt_rule.py` (mechanism copied verbatim,
  only kd/G parameterised; no behaviour change at kd=1.7/G=2.0).
- `research/tournament/oc_c2bybit/compute_c2bybit_engine.py` + `analyze_c2bybit.py` (S5 Bybit
  pattern: `bybit_minutes()` from `data/raw/bybit_linear_1m_20261004/<SYM>_1m.parquet`,
  live0 = 2021-11-15 + shift, win_start=5).
- `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl` + `v421_result.json`
  row R2B1D17BFG2 (G2: 5.41 %/mo, max yearly DD 16.91, full-path DD 16.82).
- `research/parallel/rounds/parallel-20260906-r2/v424/v424_result.json` row R2B1D13BF
  (D13BF: 5y 4.971, years 2.485/10.21, 3.286/14.98, 4.975/14.76, 9.526/7.33, 4.723/10.97,
  full-path DD 14.86) and `v422/v422_result.json` row G2K20 (5y 5.874, full 17.69).
- `research/parallel/rounds/parallel-20260906-r2/v388/v388_bot_stop_distance.py` (`mix`,
  `hourly`, Y1=2026-09-23, ANCH) + `research/diagnostics/r2_decompose5/reset_metric.py`
  (`year_reset`) for scoring (same as oc_chronos/oc_c2bybit).
- `research/diagnostics/docs_frontier/frontier_table.csv` + `docs/FRONTIER_MAP_VI.md`
  (known frontier points quoted side by side, never recomputed here).

## Variants (ONLY these; no tuning, no extra knob)

Base mechanism for every new row = verbatim oc_chronos/run_engine.py (pipe v321 via
phase_offset_full.pipe_setup; corr-aware dip sizes 1/(1+n)*kd*tilt*base with F=2.5 default;
risk_mult 1.0; sleeve_risk_budget 0.26*1*kd; bear books halved LONG; gate costs inside engine:
maker 0.0002 / taker 0.00055 / longs pay 0.0001 per 8h; limit fills only on 1m trade-through,
win_start=5, stop-first). kd/G per row:

- D13BF = kd 1.3, bear True, NO gross cap (pipe default None, as v424 R2B1D13BF), tilt 1.
- D13BF+C2 = kd 1.3, bear True, NO gross cap + C2 tilt (frozen fits above).
- G2 = D17BFG2 = kd 1.7, bear True, G=2.0, tilt 1 — COPY oc_chronos REF (no rerun here).
- G2+C2 = kd 1.7, bear True, G=2.0 + C2 tilt — COPY oc_chronos C2 (no rerun here).
- G2K20+C2 = kd 2.0, bear True, G=2.0, F 2.5 default (as v422 G2K20) + C2 tilt (new engine).
- S5 Bybit (as oc_c2bybit, win_start=5, Bybit 1m, live0 2021-11-15+shift, y2021 SHORT labelled):
  D13BF_S5 (kd1.3 no-G tilt 1), D13BF+C2_S5 (kd1.3 no-G + C2). No other friction.

Fits of anchor A applied to year A on all four shifts (year y = [ANCH5[y]+sh, min(+365d, live1));
ANCH5 = 2021..2025-09-24); missing/NaN ch_q10 -> mult 1. No refit anywhere.

## Windows / metrics (fixed)

- Anchors 2021..2025-09-24; dev4 = years 0..3 ([A,A+365d)); post-release year Y4 =
  2025-09-24..2026-09-23 scored ONCE for all rows (labelled; G2/G2+C2 Y4 already scored once
  by oc_chronos so quoted read-only, never rescored); 5y = years 0..4. No selection is made
  on Y4 (descriptive frontier check, not a pick); dev4 robust criterion stated for context only.
- Per-year 4-phase reset %/mo + DD via `reset_metric.year_reset`; dev4/5y geo mean, WORST,
  max yearly DD, losing count; full-path DD via `v388.mix` equal-1/4 mix from 2021-09-24
  (max of reset DDs and full-path for the gate); pooled book/rung/all win rates (same
  collection as oc_chronos run_engine.py).
- Reproduction gates (STOP if failed): (1) v421 G2 reproduced exactly via stored runs
  scoring (CPU, no engine); (2) D13BF base years 0..4 R/DD == v424 R2B1D13BF to the digit
  (validates kd parameterisation + no-G path); G2/G2+C2 quoted from oc_chronos (its own
  gates already PASS to the digit). G2K20+C2 has no separate base row here; v422 G2K20 is
  quoted as the known frontier point.
- Frontier table: (5y R, full-path DD) for D13BF, D13BF+C2, G2, G2+C2, G2K20+C2 (Binance)
  + D13BF_S5, D13BF+C2_S5 (Bybit) next to known points (G2 5.410/16.82, D13BF 4.971/14.86,
  G2K20 5.874/17.69, v409_D15B08 4.626/14.94, v423_X45 5.118/15.81).
- Verdict rule (fixed): answer in 3-line Vietnamese verdict whether any row has 5y >= 5
  with full-path DD < 15 on Bybit prices (S5). No adoption decision here.

## Leakage / contamination (pre-registered checks, stated in REPORT)

- Feature timing: Chronos forecast for bar open T uses ONLY the 512 closes ending at the
  bar closing at T on that shift's grid (inherited Part A); tilt reads only (coin,
  holding-bar T) ch_q10. Truncation test on frozen features (prefix-identical, multiset
  in {0.75,1.0,1.25}).
- Label windows: fits.json reused frozen (harness t_exit < A-7d, shift-0 only); year y uses
  anchor-y fit only, never a later anchor.
- Fit windows: no refit here; S5 is a price-source switch, not a fit.
- Fill timing: win_start=5 asserted in test (S5 live0 2021-11-15 + Bybit dir); engine fills
  only on 1m trade-through with stop-first (inherited harness).
- Contamination caveat next to EVERY dev number: Chronos-Bolt released 2024-11 (mostly
  non-crypto + synthetic -> LESS risk than Kronos) but dev still possibly-contaminated ->
  UPPER BOUND; post-release year (after BOTH releases) is the clean verdict (scored ONCE).

## Compute plan (heavy_slot, resume-safe)

- `tilt_rule.py`: pure `assign_mult` + `anchor_of` verbatim copy of oc_chronos logic (unit-tested).
- `compute_frontier_engine.py`: full-window runs [DEV0,Y1) like oc_c2bybit (not dev/last split);
  configs D13BF / D13BF_C2 / G2K20_C2 on base + D13BF / D13BF_C2 on S5; sequential shifts 0..3
  (one heavy process), heartbeat every 600 s, caches `tmp/runs_<cfg>_<fric>.pkl`
  (resume-safe: skip cached shifts). Invoked as
  `.venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_c2frontier_eng --min-free-gb 2.0 -- ...`.
- `analyze_frontier.py`: CPU-only scoring (reset metric + v388.mix + wins) ->
  `tmp/frontier_table.json`; REPORT.md + results.json written from that table only (+ quoted
  oc_chronos G2/G2+C2 and v422/v424 known points, labelled).
- Deliverables: PLAN.md (this file), tilt_rule.py, compute_frontier_engine.py,
  analyze_frontier.py, results.json, REPORT.md, tests/test_oc_c2frontier.py.

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the original row
  stays and the change is a disclosed extra row.)
