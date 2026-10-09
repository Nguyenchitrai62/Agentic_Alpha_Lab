# oc_netting PLAN (pre-registered BEFORE any outcome, 2026-10-08 — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_netting.md` + common header
`docs/opencode/OPENCODE_W_COMMON_20261007.md` + `AGENTS.md` + `OPENCODE_VF_COMMON.md`
(GIT READ-ONLY: no stash/reset/checkout/restore/clean/rm/commit/switch/rebase/merge).
Implements IDEAS6 #3 (`docs/opencode/IDEAS6_20261008.md`, rank 3) EXACTLY:
mechanism, causal rule, two pre-registered variants, data, harness, leakage notes.
This file freezes every choice before any number is computed. Any change after
seeing an outcome is kept as a disclosed extra row, never a silent edit.

## 1. Mechanism (IDEAS6 #3 verbatim)

4 clocks x1/4 + book/dip hold gross; book-SHORT vs dip-LONG (or 2 clocks LONG)
pays fees + adverse funding twice for net ~0. OMS: net inventory. HOW edge is
harvested, not WHEN: signals unchanged, no veto/gate/filter.

## 2. Pre-registered variants (ONLY these two)

- N1 book-vs-dip net (within each phase sub-account): after signals per coin,
  offset cancelled, survivor keeps own SL/TP; freed margin to 95% budget, no new
  risk. Exact causal rule (no parameter, tolerance 0): at each holding bar `i`,
  coin `a`, let `tgt = books_bear[i,a]` (bear-scaled d2 ffilled to the shifted
  grid, known at the decision close, same series the engine trades). If
  `tgt[a] < 0` strictly (book SHORT signal) then ALL dip LONG rung bids for
  `(i,a)` are cut to 0 (skipped, all 4 rungs 2.5/3/3.5/4 sigma); else dips
  unchanged. Survivor = book SHORT (its SL/TP path untouched); dip offset never
  opens. Implementation hook: `sleeve_filter(i,a,r) -> 0.0/1.0` on the N1 rows
  only; `sleeve_fill_size` stays the G2 corr-size x agent-size wrap (bit-identical
  when the gate passes); risk budget / gross cap / 95% budget checks unchanged;
  skipped rungs free budget that is NEVER re-used (no adds, no resizing).
  Rationale for firing: dip is LONG-only so only SHORT-vs-LONG is opposite;
  LONG-vs-LONG keeps both (gross is intended exposure). Uses target sign, not
  open weight, so it fires whenever the book is SHORT (unlike `oc_bookdipnet`'s
  open-weight guard, which is degenerate because the dip sleeve is flat at every
  holding-bar boundary — see CLOSED §5).
- N2 = N1 + merge same coin+direction across clocks (one TP/stop, earliest
  price). Engine part = N1 engine bit-identical (same gate, same fills). Merge
  part = pooled fee-only overlay on the N1 4-phase engine output (LABELLED
  approximation, no re-simulation): for each wall-clock hour `h` and coin `c`,
  count phases with same-direction book targets (`tgt>0` LONG / `tgt<0` SHORT,
  close-known, mapped to the hourly grid by ffill exactly like `v388.hourly`);
  redundant legs = max(0,n_long-1)+max(0,n_short-1). When a redundant leg's phase
  books an exit in `h` (from N1 `events`: `book_tp` maker 0.0002 / `book_stop`
  taker 0.00055 on its exit notional `|weight|x equity`), that exit fee is saved
  (merged OMS leg exits once; survivor price = earliest entry's TP/stop — fee
  uses the realised exit fee, no price improvement assumed). Savings accrue as
  `dSave` into the pooled mix accountant `A(t)=A(t-1)*(1+r_mix(t))+dSave(t)`
  (same form as `oc_carrycompound`), then per-year R/DD with the SAME reset
  convention (rebase 1.0 at each anchor). No funding saved for same-direction
  merges (net notional unchanged); opposite-direction cross-clock nets are NOT
  claimed (would need pooled re-simulation; excluded). Signals unchanged.

No other variants. No thresholds, no fits, no tuning on outcomes.

## 3. Deployed reference G2 (frozen)

G2 = `R2B1D17BFG2` in `research/parallel/rounds/parallel-20260906-r2/v421`
(`v421_runs.pkl` strat R2B1D17BFG2; `v421_result.json`): 5y R 5.410 / W 2.588 /
max-yearly-DD 16.91 / full-path DD 16.82, no losing year. Years (R %/mo, DD %):
2021 (2.588, 10.86), 2022 (3.282, 16.91), 2023 (6.045, 15.81), 2024 (10.677,
8.27), 2025-09-24 labelled (4.648, 12.90). G2 config (v421_gross_cap.py worker,
non-REF branch): v321 pipe (history_tm + v221 + v216 GRID trader, agents ON via
hist.R2_TABLE), books = research_books_d2 with x0.5 bear filter on longs ffill
to shifted clocks, corr-size inv/kd=1.7, risk_mult=1.0, sleeve budget 0.26*1.7,
gross cap 2.0, sleeve ON, trade mode, win_start=5, default gov (0.20, 0.10).
Gate costs: maker 0.0002, taker 0.00055 (stops/market exits), longs 0.0001/8h,
shorts nothing, limit fill only on 1m trade-through, no fill minutes 0-4,
stop-first on ties. Metric: `reset_metric.year_reset` per anchor year (fresh 1.0
at each anchor) + `v388.mix` hourly full-path DD (max of close/marked, same as
v421). Reproduce G2 (5.41 / 16.91 / 16.82) EXACTLY from `v421_runs.pkl` before
any overlay/engine; if reproduction fails, stop and report.

## 4. CLOSED rows cited (read first)

- `oc_bookdipnet` (signal BRAKE, never fires): strict open-weight guard fires
  0/54720 coin-bars (dip flat at every B by construction: max rung life 224m <
  240m, all timeouts exit at the next 4h open); lenient boundary-inclusive extra
  363 bars, maxDD improves 3/5, NOT PROMISING. N1 avoids the degeneracy by gating
  on the close-known TARGET SIGN (SHORT), not on open inventory at B.
- `oc_phaserebal` (cutoff): monthly/weekly rebalance lowers 5y and raises DD,
  NOT PROMISING. N2 does NOT rebalance capital (weights stay 1/4, never moved).
- `oc_governor` (cutoff): loosening/pooling the governor is a pure risk dial
  (dev +0.5pp at +2.2 DD, recent <5), REJECT. Netting does NOT touch the
  governor (default (0.20,0.10) kept, per-phase, same 2-bar lag).

## 5. Data (fixed; engine state only)

- Read-only inputs: `v421_runs.pkl` + `v421_result.json` (G2 baseline),
  `v388_bot_stop_distance.py` (ANCH/Y1/hourly/mix), `reset_metric.py`
  (year_reset), `phase_offset_full.py` (prep_idx float32 cube, pipe_setup v321),
  `phase_offset_dips.py` (minutes), `backend/history_tm.py` (R2_TABLE per shift),
  `v221_grid_hysteresis.py` (KW/eu/v216), `scripts/forward_v205.py`
  (research_books_d2), engine `engine_user.py`/`engine_real.py` (simulate,
  UNEDITED). Existing 1m via `pod.minutes()` only inside the engine harness.
- No new market data, no external history, no fits. N1 gate uses only
  `books_bear` target signs (engine state, close-known). N2 overlay uses only N1
  engine events + target signs on the hourly grid. All five anchor years are
  research data for SCORING ONLY under the selection protocol below; no
  statistic from any test year feeds any choice (there is nothing to fit).

## 6. Harness (fixed; Book/account idea => 4-phase engine vs G2 + fee/funding split)

- Stage 0 (LIGHT, no 1m): reproduce G2 from `v421_runs.pkl` via `year_reset`
  (5y R/W/DD + per-year) and `v388.mix` full-path DD; assert
  R==5.410, W==2.588, DD==16.91, full==16.82 to the digit.
- Stage 1 dev (selection): 4-phase engine (shifts s=0..3, SEQUENTIAL, one engine
  at a time, float32 cube, one coin at a time inside custom loops — the audited
  `simulate` call itself is unchanged) rows G2REF (gate off, harness check) +
  N1 (gate on), live = DEV0+sh .. DEV1+sh (DEV0=2021-09-24, DEV1=2025-09-24, from
  `phase_offset_full`). Score dev years y=0..3 (anchors 2021/2022/2023/2024-09-24,
  each [A, A+365d)) with `year_reset` on the fresh runs; full-path DD on the dev
  window via `v388.mix`-equivalent stitch for context (gate = full 5y path at
  Stage 2). Fee/funding split from engine `stats` (fees, funding) + win rates
  from `events` (book_win via `pof.book_win`; per-year book exits / rung wins).
- Stage 2 recent year (2025-09-24 .. Y1=2026-09-23, scored ONCE): full-window
  runs for the dev4 robust pick ONLY (+ G2 REF from store, labelled, not
  re-selected). No iteration after.
- N2 overlay computed from the N1 runs' events+targets (no extra engine); N2
  per-year R/DD from the adjusted pooled hourly path with the same reset
  convention; N2 full-path DD from the adjusted continuous path.
- Bit-identity: Stage 1 G2REF dev runs must match stored G2 dev segments
  (max-abs-diff 0.0 / bit-exact where lengths equal); N1 runs with gate off
  (=G2REF config) reproduce G2REF bit-exact (test asserts).

## 7. Selection (dev years ONLY)

Robust criterion (AGENTS.md): eligible = max yearly DD <= 20 and no losing dev
year; prefer dev4 mean >= 5 %/mo if any; among those pick highest dev4 WORST-year
monthly R; ties -> higher mean. Compare ONLY anchors 2021-2024. Score the most
recent year ONCE, only for the chosen variant (+ REF, labelled). If nothing is
eligible, no Stage-2 engine run beyond the REF label; REPORT states rejection.
Expected effect (IDEAS6, not a gate): +0.01-0.06 %/mo, DD flat/-0.3. A clean
gate failure is a valid result.

## 8. Leakage checklist (to be stated in REPORT.md)

- Feature timing: `books_bear` = latest standard-grid book row <= shifted
  decision time (ffill; identity at s=0); R2 agent size/TP keyed by holding bar
  T=idx+4h (lookup `(T,sym,rung)`, decided at bar open); sigma/vol-scale/
  governor causal with 2-bar lag; sig4 from closes <= decision.
- Label windows: none (no labels, no model, no thresholds fitted).
- Fit windows: none (gate has no parameter; N2 has no parameter; embargo N/A —
  nothing is fitted on any window).
- Fill timing: win_start=5 (no fill minutes 0-4), limit fills only on 1m
  trade-through (strictly through, `fill_through_bps=0`), stop-first on same-1m
  stop+TP ties, unfilled entry limits expire (no market fallback), stops market
  taker 0.00055 / TP limit maker 0.0002, adverse funding longs 0.0001/8h.
  N1 gate decided at bar open (data <= decision); N2 savings from realised exits
  at exit minute only (exit time <= accrual hour).

## 9. Resources / constraints (assignment-specific)

- Write ONLY `research/tournament/oc_netting/` (+ `tests/test_oc_netting.py`).
  Never edit registry/ledgers/docs (except this PLAN)/bot/backend/scripts/other
  workers/`../Kronos`; no commits; no exchange orders; no Kaggle uploads.
- HEAVY via `.venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_netting
  --min-free-gb 2.0 -- <cmd>`; never `--leader`. One engine job at a time
  (sequential shifts, NO Pool(2)); one coin at a time in custom 1m loops;
  float32 cube. Long jobs via nohup + a log under `oc_netting/tmp/`, poll the
  log; never inspect /proc or folders outside the workspace. Print progress
  every ~10 min.
- Tests: `tests/test_oc_netting.py` (>=1 causality/truncation test + >=1
  hand-checked synthetic netting case; run `.venv/Scripts/python.exe -m pytest
  tests/test_oc_netting.py -q`). Stop when done.

## 10. Outputs (ONLY these paths)

- `research/tournament/oc_netting/PLAN.md` (this file, frozen),
  `compute_g2check.py` (Stage-0 LIGHT reproduce), `compute_engine.py` (Stage-1/2
  4-phase G2REF+N1, sequential shifts, events+stats capture),
  `compute_n2overlay.py` (N2 fee-only pooled overlay from N1 outputs),
  `analyze.py` (selection + per-year tables + fee/funding split + DD),
  `results.json`, `REPORT.md` (per-year table dev + recent-ONCE labelled, dev4
  robust pick, 5y, full-path DD, win rates, fee/funding split, leakage
  checklist, Vietnamese 3-line verdict), `tmp/` logs/pickles.
- `tests/test_oc_netting.py`.
