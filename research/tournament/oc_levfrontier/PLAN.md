# oc_levfrontier — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_levfrontier.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, docs/opencode/OPENCODE_VF_COMMON.md read in full).
Write ONLY `research/tournament/oc_levfrontier/` + `tests/test_oc_levfrontier.py`. Scratch only under
`research/tournament/oc_levfrontier/tmp/`, never the system temp folder; do not inspect /proc.
GIT IS READ-ONLY FOR WORKERS: never stash/reset/checkout/restore/clean/rm/commit/switch/rebase/merge.
Engine / heavy 1m work via `scripts/heavy_slot.py` (RAM tight: ONE engine job at a time, sequential
shifts, one heavy process; never `--leader`). Long jobs: nohup + log file under tmp/, poll the log.
Heartbeat print every 600 s in long jobs. Progress print every 10 minutes.

## Question (verbatim assignment)

The deployable return/drawdown frontier on BYBIT prices with carry (leverage x C2 x B7):
at full-path DD <= 20 on Bybit prices (the owner's venue) with the quarterly carry overlay
f 0.25, which exposure level and overlay give the best return, and does any row reach
>= 5 %/month in the most recent year?

Context (given, read-only): oc_cboostctrl: most of B7's gain is exposure (~70% plain extra
exposure; timing keeps ~26-39%), so the real question is the frontier over exposure x overlay.

## Rows (ONLY these 8 BOT configs; no tuning, no extra knob, no ensemble)

All rows: everything else EXACTLY G2 (pipe v321 via phase_offset_full.pipe_setup; corr-aware
dip sizes 1/(1+n)*kd*tilt*base with F=2.5 default; rule inv k=1.0; risk_mult 1.0;
sleeve_risk_budget 0.26*1*kd; bear books halved LONG; G2's gross cap G=2.0 binds on EVERY row;
gate costs inside the engine: maker 0.0002, taker 0.00055, longs pay 0.0001/8h, shorts 0;
limit fill only on 1m trade-through, nothing in the first 5 min after a 4h close (win_start=5);
stop-first in a shared 1m bar — engine handles). Book leg byte-identical everywhere.

dip-mult kd in {1.7 (G2), 2.0 (G2K20)} x overlay in {none, C2, B7, B7xC2}:

- L00 G2        = kd 1.7, tilt 1 (REF).
- L01 G2+C2     = kd 1.7 + C2 tilt (frozen oc_chronos fits.json, risk=-ch_q10, hi 1.25/lo 0.75,
  missing/NaN -> 1.0; fits of anchor A applied to year A on all four shifts).
- L02 G2+B7     = kd 1.7 + B7 boost (frozen boost_mult_4shift.parquet mult_B7: 1.5 in the 7d
  window (tc,tc+7d] after any >4sg 4h bar, else 1.0; market-wide per shift; exact (shift,T)
  match with causal ffill fallback, missing -> 1.0).
- L03 G2+B7xC2  = kd 1.7 + PRODUCT m_B7*m_C2 uncapped (oc_b7c2 B7C2;
  multiset {0.75,1.0,1.125,1.25,1.5,1.875}). The capped min(product,1.5) variant is NOT part
  of this study (disclosed only as a quoted side number where needed).
- L10 G2K20     = kd 2.0, tilt 1 (v422 G2K20 definition: rule inv, k 1.0, kd 2.0, bear True,
  G=2.0, F 2.5).
- L11 G2K20+C2  = kd 2.0 + C2 tilt (same frozen C2 as above).
- L12 G2K20+B7  = kd 2.0 + B7 boost (same frozen B7 as above).
- L13 G2K20+B7xC2 = kd 2.0 + PRODUCT m_B7*m_C2 uncapped (same frozen stack as L03).

Each BOT config runs on TWO venues: base Binance prices AND Bybit S5 prices (S5 harness of
oc_c2bybit: bybit_minutes() from data/raw/bybit_linear_1m_20261004/<SYM>_1m.parquet, live0 =
2021-11-15 + shift, standard index filtered to >= 2021-11-15 before shift, win_start=5;
y2021 on S5 is a SHORT window, labelled everywhere). 8 x 2 = 16 BOT legs.
Then the carry overlay EXACTLY as research/tournament/oc_c2carry (quarterly carry f=0.25,
ONE-account compounding, same frozen 33 trades) on EACH of the 16 legs -> 16 carry legs
(+ 16 f=0 BOT legs for the reproduction/method table; 32 account rows total, 16 deployable).

If anything changes after seeing an outcome, the original row stays and the change is added
as a disclosed extra row (none planned).

## Frozen inputs (read-only, never edited, never refit)

- `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl` + `v421_result.json`
  row R2B1D17BFG2 (G2: dev [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27)],
  Y4 4.648/12.90, 5y 5.410, W 2.588, max yearly DD 16.91, full-path DD 16.82).
- `research/parallel/rounds/parallel-20260906-r2/v422/v422_runs.pkl` + `v422_result.json`
  row G2K20 (kd 2.0 G 2.0: dev [(2.832/12.01),(3.272/17.79),(7.149/15.79),(11.644/9.34)],
  Y4 4.716/13.65, 5y 5.874, W 2.832, DD 17.79, full 17.69).
- `research/tournament/oc_chronos/chronos_features_4shift.parquet` (ch_q10 only) +
  `fits.json` (C2 fits, all direction +1: 2021 q20 1.110054237503456 q80 2.8608138206510407;
  2022 1.1847269503398057/3.0250640748629083; 2023 1.0735691511209666/2.773698097596179;
  2024 1.0644316852926394/2.65023108446202; 2025 1.0742922959916594/2.5976577907281015;
  hi 1.25/lo 0.75, missing -> 1).
- `research/tournament/oc_cascadeboost/boost_mult_4shift.parquet` (shift,T,mult_B7;
  closes-only |r|>4*SIG(540,min120) triggers, union over 5 majors per shift, window
  (tc,tc+7d] market-wide per shift) + `boost_rule.py` arithmetic (copied verbatim here
  as `lev_rule.py` B7 half; BOOST 1.5, B7_DAYS 7, THRESH 4.0, WINDOW 540, MIN 120).
- `research/tournament/oc_chronos/run_engine.py` + `tilt_rule.py` and
  `research/tournament/oc_cascadeboost/run_engine.py` + `research/tournament/oc_b7c2/`
  `run_engine.py`/`compute_s5_engine.py`/`stack_rule.py` (mechanism + stack product copied;
  only kd parameterised 1.7/2.0 — no behaviour change at kd=1.7 vs oc_b7c2).
- `research/tournament/oc_c2bybit/compute_c2bybit_engine.py` + `analyze_c2bybit.py` (S5 Bybit
  pattern copied verbatim; only the dip mult lookup becomes kd x overlay).
- Stored runs reused VERBATIM (bit-exact, asserted to the digit at scoring time):
  v421 G2; v422 G2K20; oc_chronos C2 (tmp/runs_last.pkl C2 == oc_c2bybit runs_base.pkl C2);
  oc_c2bybit runs_base.pkl (REF/C2) + runs_S5.pkl (REF_S5/C2_S5);
  oc_cascadeboost runs (B7 base) == oc_cboostbybit runs_base.pkl B7;
  oc_cboostbybit runs_S5.pkl (REF_S5/B7_S5); oc_b7c2 tmp/runs_last.pkl (B7C2 base) +
  tmp/runs_S5.pkl (B7C2_S5); oc_c2frontier tmp/runs_G2K20_C2_base.pkl (G2K20+C2 base).
- Carry overlay: `research/tournament/oc_carrycompound/analyze_carrycompound.py` +
  `research/tournament/oc_c2carry/analyze_c2carry.py` (method copied EXACTLY: hourly grid
  2021-09-24 04:00..2026-09-23 12:00 UTC, v388.hourly per-phase Es/Ms, causal last-CLOSED-hourly
  S/F carry MtM, entry fee 0.001+0.00055, ONE-account UTA A(t)=A(t-1)*(1+r_bot(t))+dU(t),
  f=0 short-circuit bit-exact, per-year reset to 1.0, v421 continuous full-path DD) +
  `research/tournament/oc_cashcarry/results.json` (33 entered frozen, threshold 0.04,
  13 skipped, 2 incomplete) + `data/raw/qbasis_20261003`, `data/raw/spot_majors_20260925`,
  `research/tournament/ext/hourly_ext.parquet`.
- Bootstrap model: `research/tournament/oc_mcdd/mcdd_bootstrap.py` stationary Politis-Romano,
  exactly as oc_c2carry (mean block 10 days, 4000 draws, seed 0, circular, 365d paths).
- Scoring: `research/parallel/rounds/parallel-20260906-r2/v388/v388_bot_stop_distance.py`
  (`mix`, `hourly`, Y1=2026-09-23, ANCH) + `research/diagnostics/r2_decompose5/reset_metric.py`
  (`year_reset`) — same as oc_chronos/oc_c2bybit/oc_c2frontier/oc_cboostbybit/oc_b7c2.

## Reuse vs new engine (fixed)

REUSED (no rerun; asserted to the digit, else STOP): L00 base+S5, L01 base+S5, L02 base+S5,
L03 base+S5, L10 base (v422), L11 base (oc_c2frontier). Reference REF_S5 equality across the
K2/C2/B7 S5 files asserted element-wise (same engine).
NEW engine rows (ONLY these 6 BOT legs, full-window [DEV0,Y1) base / [2021-11-15+shift,Y1+shift)
S5 like oc_c2frontier/oc_b7c2, sequential shifts 0..3, resume-safe caches
tmp/runs_<CFG>_<FRIC>.pkl, heartbeat 600 s):
L10_S5 (G2K20 on Bybit), L11_S5 (G2K20+C2 on Bybit), L12_base + L12_S5 (G2K20+B7 both venues),
L13_base + L13_S5 (G2K20+B7xC2 both venues).
No other engine; no re-runs after outcomes.

## Windows / metrics (fixed)

- Anchors 2021..2025-09-24; dev4 = years 0..3 ([A,A+365d)); Y4 = 2025-09-24..2026-09-23;
  5y = years 0..4. Engine runs full-window so Y4 is scored in the same single pass.
- Per BOT leg AND per carry leg (f=0.25): per-year 4-phase reset %/mo + DD, dev4 geo mean,
  W (worst-year R), max yearly DD, losing count; 5y geo mean; full-path DD via v388.mix
  equal-1/4 mix from 2021-09-24 (max of marked/close; gate uses max of yearly DDs and
  full-path); worst 1m-marked DD episode per BOT row (peak/trough/depth on
  dd(t)=1-ms(t)/peak(es)(t), verbatim oc_cboostbybit); pooled book/rung/all win rates
  (same collection as oc_cascadeboost run_engine.py).
- Carry legs: ONE-account overlay f=0/0.25 verbatim oc_c2carry (same grid, same carry MtM,
  same UTA compounding, same reset/full-path/DD code); carry marks close-marked (DD lower
  bound); carry leg venue-independent (same MtM on both venues).
- Bootstrap per carry leg AND per BOT leg (descriptive, exactly as oc_c2carry): daily close E
  + daily marked low M from the continuous account (00:00 UTC ffill, causal); stationary
  bootstrap mean block 10 d, 4000 paths x 365 d, seed 0, circular; report median %/mo,
  P(month >= 5%), P(marked DD > 20% in a year), P(losing year). Binance universe
  2021-09-24..2026-09-23; Bybit universe 2021-11-15..2026-09-23 (live only, labelled).
  Assumes ~stationary daily returns, ~10-day dependence only (no annual regime structure).
- Reproduction gates (STOP + report if failed): G2 base == v421 to the digit
  (5.410/W 2.588/DD 16.91/full 16.82); G2K20 base == v422 (5.874/W 2.832/DD 17.79/full 17.69);
  C2 base == oc_chronos C2 (dev 2.711/11.52, 3.460/15.48, 6.250/15.07, 10.721/8.29; Y4
  4.754/12.86; 5y 5.542; full 15.42); B7 base == oc_cascadeboost B7 (dev 2.955/14.67,
  3.264/17.92, 8.537/15.94, 12.486/11.01; Y4 4.88/13.81; 5y 6.364; full 17.75);
  B7C2 base == oc_b7c2 B7C2 (dev 2.922/15.45, 3.573/17.05, 7.795/16.27, 12.598/11.04;
  5y 6.318; full 16.91); G2K20+C2 base == oc_c2frontier (5y 5.983/full 16.24);
  REF_S5/C2_S5/B7_S5/B7C2_S5 == their frozen S5 tables to the digit; f=0 carry
  short-circuit reproduces each BOT leg bit-exact; G2+carry f=0.25 reproduces oc_c2carry
  (Binance 5.634/16.66; Bybit S5 5.111/17.93) to the digit as a method check.
- Selection (fixed): robust pick on dev4 ON BYBIT PRICES WITH CARRY f=0.25 among rows with
  full-path DD (carry-included continuous path) <= 20 AND no losing dev year: prefer dev4
  mean >= 5 %/mo, then the highest dev4 WORST-year monthly return, ties -> higher mean.
  (BOT-only dev4/Bybit ranking disclosed as a side row; it does not change the pick.)
  The assignment question is answered descriptively: which row meets 5y >= 5 %/mo AND
  full-path DD <= 20 on Bybit with carry, and does any row reach >= 5 %/mo in the most
  recent year (labelled, see below).
- Plain table of (5y, full DD) for all 16 carry points (8 x 2 venues, f=0.25) + a side table
  of the 16 BOT f=0 points for the method check.

## Labels / contamination (pre-registered, stated in REPORT)

- C2's dev years nearly clean (Chronos-Bolt 2024-11, mostly non-crypto + synthetic -> LESS
  risk than Kronos, but dev still possibly-contaminated -> UPPER BOUND with a small caveat).
- B7 contaminated (oc_cascadeboost: idea formed after oc_cascadedelay's replica had covered
  all five years incl. the post-release year; oc_cboostctrl: ~70% of B7's gain is plain extra
  exposure, timing keeps ~26-39%).
- The post-release year (2025-09-24..2026-09-23) is a LABELLED DIAGNOSTIC for EVERY row that
  contains C2 or B7 (i.e. all rows except L00/L10, whose Y4 are reproductions of v421/v422 but
  still labelled as a re-score under S5/carry wherever S5 or carry applies). Selection NEVER
  uses Y4. Only prospective paper could confirm C2/B7/stack rows.
- S5 y2021 SHORT (Bybit live from 2021-11-15, labelled everywhere). Carry overlay is post-hoc
  (same five years, needs prospective paper). Carry marks close-marked (DD lower bound).

## Leakage / checks (stated in REPORT)

- Feature timing: C2 forecast for bar open T uses ONLY the 512 closes ending at the bar
  closing at T on that shift's grid (inherited Part A); B7 triggers use closes with
  close_time <= tc only (SIG window excludes the tested bar; boost window strictly after tc
  0 < T-tc <= 7d); stack lookup uses only (sym,shift,T) at the holding bar.
  Truncation test: recompute mults from truncated frozen tables -> identical on kept prefix;
  multiset checks (C2 {0.75,1.0,1.25}, B7 {1.0,1.5}, stack {0.75,1.0,1.125,1.25,1.5,1.875}).
  Engine exact (shift,T) match with causal ffill fallback (latest grid time <= T).
- Label windows: no labels fit anywhere in this study (no harness join).
- Fit windows: no refit; threshold 4.0, windows 540/120, boost 1.5, N=7, kd 1.7/2.0, G 2.0,
  carry threshold 0.04/f 0.25 all frozen ex-ante, never scanned; no statistic from any test
  year feeds any choice (S5 grid change and carry overlay are price-source/account switches,
  not fits). Year y never uses a later anchor's anything (C2 fits shift-0 + 7d embargo
  inherited; B7 triggers strictly causal).
- Fill timing: win_start=5 asserted in test (S5 live0 2021-11-15 + Bybit dir in source);
  engine fills only on 1m trade-through with stop-first (inherited harness); carry MtM uses
  last CLOSED hourly bar strictly before t; bootstrap uses daily causal ffill, no 1m peeking.
- Gate costs inside the engine (maker 0.0002/taker 0.00055/longs pay 0.0001 per 8h; carry
  fees spot 0.001/side + fut 0.00055/0.0002 frozen). Coverage: disclose any skipped anchor
  year (none expected; missing boost -> 1.0, missing ch_q10 -> 1.0, counted).

## Compute plan (heavy_slot, resume-safe)

- `lev_rule.py`: pure helpers (`assign_c2`+`anchor_of` verbatim oc_chronos tilt_rule,
  `b7_for`+stack product verbatim oc_b7c2 stack_rule, BOOST 1.5, B7_DAYS 7, C2 hi/lo
  1.25/0.75) — no data access; unit-tested.
- `compute_levfrontier_engine.py`: NEW engine rows ONLY (L10_S5, L11_S5, L12_base, L12_S5,
  L13_base, L13_S5; kd 1.7/2.0 x overlay, G 2.0, S5 Bybit pattern exactly as
  oc_cboostbybit/oc_b7c2); full-window runs; sequential shifts 0..3 (one heavy process at a
  time), heartbeat every 600 s, caches `tmp/runs_<CFG>_<FRIC>.pkl` (resume-safe: skip cached
  shifts). Invoked as `.venv/Scripts/python.exe scripts/heavy_slot.py run
  --tag oc_levfrontier_eng --min-free-gb 2.0 -- .venv/Scripts/python.exe
  research/tournament/oc_levfrontier/compute_levfrontier_engine.py [--job ...]`.
  Long jobs: nohup + log under tmp/, poll the log. Progress print every 10 minutes.
- `analyze_levfrontier.py`: CPU-only scoring (reset metric + v388.mix + wins + worst marked
  episode for BOT legs; ONE-account carry overlay f=0/0.25 + stationary bootstrap exactly as
  oc_c2carry for all 16 BOT legs) -> `tmp/levfrontier_table.json`; REPORT.md + results.json
  written from that table only (+ quoted/copied rows, labelled). G2 baseline + G2+carry
  method check reproduced exactly before any overlay; else STOP.
- Deliverables: PLAN.md (this file), lev_rule.py, compute_levfrontier_engine.py,
  analyze_levfrontier.py, results.json, REPORT.md, tests/test_oc_levfrontier.py (>=1
  causality/truncation test + >=1 hand-checked synthetic case;
  `.venv/Scripts/python.exe -m pytest tests/test_oc_levfrontier.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the original row stays
  and the change is a disclosed extra row.)
