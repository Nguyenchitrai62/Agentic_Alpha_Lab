# oc_b7frontier — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_b7frontier.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, docs/opencode/OPENCODE_VF_COMMON.md read in full).
Write ONLY `research/tournament/oc_b7frontier/` + `tests/test_oc_b7frontier.py`. Scratch only under
`research/tournament/oc_b7frontier/tmp/`, never the system temp folder; do not inspect /proc.
GIT IS READ-ONLY FOR WORKERS: never stash/reset/checkout/restore/clean/rm/commit/switch/rebase/merge.
Engine / heavy 1m work via `scripts/heavy_slot.py` (RAM tight: one engine job at a time, sequential
shifts, one heavy process; never `--leader`). Long jobs: nohup + log file under tmp/, poll the log.
Heartbeat print every 600 s in long jobs. Progress print every 10 minutes.

## Question

B7 on the lower-risk D13BF base: >= 5 %/month with full-path DD <= 20 on BYBIT prices?

Context (given, not recomputed): `research/tournament/oc_cboostbybit`: G2 + B7 on Bybit prices
5y 5.906 (G2 4.883) but full-path DD 20.31 > 20. `research/tournament/oc_c2frontier` built D13BF
(dip-mult 1.3, v424, Bybit S5 5y 4.482 / full DD 15.95). B7 on that base may keep >= 5 %/month
with DD well under 20.

CONTAMINATION LABEL (pre-registered here, before any outcome): B7 is contaminated
(`research/tournament/oc_cascadeboost` — idea formed after oc_cascadedelay's replica had covered
all five years incl. the post-release year). Every post-release number below (anchor 2025-09-24
year), including base/D13BF re-scores, is a LABELLED DIAGNOSTIC, never a selection input; only
prospective paper could confirm B7. Repeated in REPORT.md / results.json.

## Variants (ONLY these; no tuning, no extra knob, no ensemble)

BOT legs (6 engine configs; book byte-identical everywhere):

- D13BF_base  = kd 1.3, bear True, NO gross cap (pipe default None, as v424 R2B1D13BF), tilt 1.
- D13BF_S5    = same on Bybit S5 prices.
- D13B7_base  = kd 1.3, bear True, NO gross cap + B7 boost (frozen mult_B7, 1.5 in 7d window else 1.0).
- D13B7_S5    = same on Bybit S5 prices.
- G2B7_base   = kd 1.7, bear True, G=2.0 + B7 boost — COPY `oc_cboostbybit` B7_base (no rerun here).
- G2B7_S5     = same on Bybit S5 — COPY `oc_cboostbybit` B7_S5 (no rerun here).
- Reference D13BF/G2 rows are COPY `oc_c2frontier` D13BF_base/D13BF_S5 and `oc_cboostbybit`
  REF_base/REF_S5 (no rerun; reproduction gates below prove the harness is identical).

Carry overlay (6 account rows, exactly like `research/tournament/oc_c2carry`):
each BOT leg above + quarterly carry f 0.25 as a ONE-account overlay
(A(t) = A(t-1)*(1+r_bot(t)) + dU(t), UTA sizing, same frozen 33 trades, same fees/marks).
Labels: `D13BFc_base`, `D13BFc_S5`, `D13B7c_base`, `D13B7c_S5`, `G2B7c_base`, `G2B7c_S5`
(`c` = +carry f 0.25). Carry leg is venue-independent (same MtM on both venues).

If anything changes after seeing an outcome, the original row stays and the change is added as a
disclosed extra row (none planned).

## Frozen inputs (read-only, never edited, never refit)

- `research/tournament/oc_cascadeboost/boost_mult_4shift.parquet` (shift, T, mult_B7; closes-only
  |r|>4*SIG(540,min120) triggers, union over 5 majors per shift — reused VERBATIM for D13B7;
  missing mult -> 1.0, counted).
- `research/tournament/oc_cascadeboost/boost_rule.py` (pure arithmetic copied verbatim here as
  `boost_rule.py`; BOOST 1.5, B7_DAYS 7, THRESH 4.0, WINDOW 540, MIN_PERIODS 120).
- `research/tournament/oc_cascadeboost/run_engine.py` + `research/tournament/oc_cboostbybit/`
  `compute_cboostbybit_engine.py` + `research/tournament/oc_c2frontier/compute_frontier_engine.py`
  (mechanism + S5 harness copied; only kd/G/tilt parameterised — no behaviour change at
  kd=1.7/G=2.0/tilt1 vs oc_cboostbybit, at kd=1.3/no-G/tilt1 vs oc_c2frontier D13BF).
- `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl` + `v421_result.json` row
  R2B1D17BFG2 (G2 baseline: dev years [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27)],
  Y4 (4.648/12.90), 5y 5.410, max yearly DD 16.91, full-path DD 16.82).
- `research/parallel/rounds/parallel-20260906-r2/v424/v424_result.json` row R2B1D13BF
  (D13BF: 5y 4.971, years 2.485/10.21, 3.286/14.98, 4.975/14.76, 9.526/7.33, 4.723/10.97,
  full-path DD 14.86).
- `research/tournament/oc_c2frontier/tmp/runs_D13BF_base.pkl` + `runs_D13BF_S5.pkl`
  (D13BF legs copied; must equal v424 / oc_c2frontier table to the digit).
- `research/tournament/oc_cboostbybit/tmp/runs_base.pkl` (REF=G2, B7=G2B7) +
  `tmp/runs_S5.pkl` (REF_S5, B7_S5=G2B7_S5) + `tmp/cboostbybit_table.json`
  (expected G2B7 numbers: base 5y 6.364/full 17.75; S5 5y 5.906/full 20.31; D13BF_S5 expected
  from oc_c2frontier: 5y 4.482/full 15.95).
- `research/tournament/oc_c2bybit/compute_c2bybit_engine.py` + `robust_v421.py` S5 Bybit pattern
  (`bybit_minutes()` from `data/raw/bybit_linear_1m_20261004/<SYM>_1m.parquet`, live0 2021-11-15
  + shift, win_start=5; y2021 SHORT labelled).
- Carry overlay: `research/tournament/oc_carrycompound/analyze_carrycompound.py` +
  `research/tournament/oc_c2carry/analyze_c2carry.py` (f=0.25 compounding method copied exactly) +
  `research/tournament/oc_cashcarry/results.json` (33 entered frozen, threshold 0.04, 13 skipped,
  2 incomplete) + `data/raw/qbasis_20261003`, `data/raw/spot_majors_20260925`,
  `research/tournament/ext/hourly_ext.parquet`.
- Bootstrap model: `research/tournament/oc_mcdd/mcdd_bootstrap.py` stationary Politis-Romano;
  here mean block 10 days, 4000 draws, seed 0 (exactly as oc_c2carry).
- Scoring: `research/parallel/rounds/parallel-20260906-r2/v388/v388_bot_stop_distance.py`
  (`mix`, `hourly`, Y1=2026-09-23, ANCH) + `research/diagnostics/r2_decompose5/reset_metric.py`
  (`year_reset`) — same as oc_chronos/oc_c2bybit/oc_c2frontier/oc_cboostbybit.

## Mechanism (exact copy; only kd/G/tilt vary)

- 4 phases (shifts 0..3, 4h grid opens at s, s+4, ... UTC); pipe v321 via
  phase_offset_full.pipe_setup; corr-aware dip sizes 1/(1+n)*kd*boost*base
  (n = coins with C<=O*(1-2.5*sig)); risk_mult 1.0; sleeve_risk_budget 0.26*1*kd;
  sleeve_gross_cap G=2.0 for G2B7 rows, None (pipe default) for D13BF/D13B7 rows;
  bear books (BTC 4h open < 1200-bar mean halves LONG targets; standard rows, before
  shifted-clock ffill).
- B7 tilt: dip rung size x mult_B7(T, shift) (1.5 in the 7d window after any >4sg 4h bar,
  else 1.0; market-wide per shift, same for all 5 coins at (shift, T); book byte-identical).
  Engine lookup: exact (shift, T) match with causal ffill fallback (latest grid time <= T),
  missing -> 1.0.
- Gate costs (inside engine): maker 0.0002, taker 0.00055 (stops/market taker),
  longs pay 0.0001/8h, shorts 0. Limits fill only on 1m trade-through, nothing in the first
  5 min after a 4h close (win_start=5); stop-first in a shared 1m bar (engine handles).
- S5 Bybit: `bybit_minutes()` from the Bybit dir instead of `pod.minutes()`; live0 =
  2021-11-15 + shift; standard index filtered to >= 2021-11-15 before shift; win_start=5.
  Year 2021 on S5 is a SHORT window (labelled everywhere). If Bybit files are
  missing/unreadable, report S5 as not reproducible (no silent fallback).
- Carry overlay (verbatim oc_c2carry/oc_carrycompound): hourly grid 2021-09-24 04:00 ..
  2026-09-23 12:00 UTC; per BOT leg per-phase hourly Es/Ms via `v388.hourly` (ffill causal,
  `eq_min` shifted -4h, `min(lo,e)`), 4-phase means Etot/Mtot; carry MtM per pair (alloc units)
  on the grid with causal last-CLOSED-hourly S/F strictly before t, 0 before entry-close,
  frozen `ret_alloc` from settlement; entry-paid fee 0.001+0.00055 while open; compounding
  ONE account (UTA): A(t)=A(t-1)*(1+r_bot(t))+dU(t), r_bot from the stored 4-phase mix of THAT
  BOT leg (sizes on TOTAL equity), dU = carry MtM change on notionals N = f x A at each entry
  (spanning positions at a reset use f x 1.0); marked path M(t)=A(t-1)*(ms_base(t)/es_base(t-1))
  +dU(t); f=0 short-circuits to base bit-exact. Per-year reset to 1.0 (spanning carry rebased
  to 0 at each anchor). Full-path DD continuous from grid start, v421 formula (max of
  marked/close DD on the segment > 2021-09-24). Carry marks are close-marked (DD lower bound).
- Bootstrap per row (descriptive, exactly as oc_c2carry): daily close E + daily marked low M
  from the continuous account (00:00 UTC ffill, causal); daily r + low-ratio l; stationary
  bootstrap mean block 10 d, 4000 paths x 365 d, seed 0, circular; report median %/mo,
  P(month >= 5 %), P(marked DD > 20 % in a year), P(losing year). Binance universe
  2021-09-24..2026-09-23; Bybit universe 2021-11-15..2026-09-23 (live only, labelled).
  Assumes ~stationary daily returns, ~10-day dependence only (no annual regime structure).

## Windows / metrics (fixed)

- Anchors 2021..2025-09-24; dev4 = years 0..3 ([A,A+365d)); Y4 = 2025-09-24..2026-09-23
  (CONTAMINATED for every B7 row: B7 idea formed after seeing this year via the delay replica —
  every Y4 number here is a LABELLED DIAGNOSTIC re-score, never a selection input); 5y =
  years 0..4. Engine runs full-window [DEV0,Y1) like oc_c2frontier/oc_cboostbybit, so Y4 is
  scored in the same single pass and reported for all pre-registered rows (labelled); selection
  uses dev4 ONLY (see verdict rule).
- Per-year 4-phase reset %/mo + DD via `reset_metric.year_reset`; dev4/5y geo mean, W (worst-year
  R), max yearly DD, losing count; full-path DD via `v388.mix` equal-1/4 mix from 2021-09-24
  (max of reset DDs and full-path for the gate); worst 1m-marked DD episode per BOT row
  (peak/trough/depth on dd(t) = 1 - ms(t)/peak(es)(t), verbatim oc_cboostbybit); pooled
  book/rung/all win rates (same collection as oc_cascadeboost run_engine.py).
- Reproduction gates (STOP + report if failed): (1) G2 reproduced from stored `v421_runs.pkl`
  scoring (CPU) == v421_result.json to the digit (5.410/W 2.588/DD 16.91/full 16.82);
  (2) copied D13BF_base == v424 R2B1D13BF to the digit; (3) copied G2B7_base == oc_cascadeboost
  B7 == oc_cboostbybit B7_base to the digit (dev 2.955/14.67, 3.264/17.92, 8.537/15.94,
  12.486/11.01; Y4-diagnostic 4.88/13.81; 5y 6.364; full 17.75); (4) copied G2B7_S5 ==
  oc_cboostbybit B7_S5 to the digit (dev4 6.217/W 2.200; 5y 5.906; full 20.31);
  (5) copied D13BF_S5 == oc_c2frontier D13BF_S5 to the digit (5y 4.482/full 15.95);
  (6) f=0 carry short-circuit reproduces each BOT leg bit-exact; G2+carry f=0.25 reproduces
  oc_c2carry G2_carry_binance (5.634/16.75/16.66) and G2_carry_bybit_S5 (5.111/17.93) to the
  digit as a method check.
- Verdict rule (fixed): selection on dev4 ONLY per the robust criterion (DD <= 20 and no losing
  dev year; prefer dev4 mean >= 5 %/mo, then the highest dev4 WORST-year monthly return,
  ties -> higher mean). The assignment question is answered descriptively: which row meets
  5y >= 5 %/mo AND full-path DD <= 20 on Bybit prices with carry (f=0.25)? 3-line Vietnamese
  verdict in REPORT.md (adopt / reject / needs prospective evidence).

## Leakage / contamination (pre-registered checks, stated in REPORT)

- Feature timing: cascade triggers use closes with close_time <= tc only (SIG window excludes
  the tested bar; boost window strictly after tc 0 < T-tc <= 7d). Truncation test: recompute
  triggers from truncated bars -> identical on kept prefix; multiset subset of {1.0, 1.5}.
  Engine uses exact (shift, T) match with causal ffill fallback (latest grid time <= T).
- Label windows: no labels fit anywhere in this study (no harness join).
- Fit windows: no fits; threshold 4.0, windows 540/120, boost 1.5, N=7, kd 1.3/1.7, G 2.0/None,
  carry threshold 0.04/f 0.25 all frozen ex-ante, never scanned; no statistic from any test
  year feeds any choice (S5 grid change and carry overlay are price-source/account switches,
  not fits). Year y never uses a later anchor's anything.
- Fill timing: win_start=5 asserted in test (S5 live0 2021-11-15 + Bybit dir in source);
  engine fills only on 1m trade-through with stop-first (inherited harness); carry MtM uses
  last CLOSED hourly bar strictly before t; no 1m peeking in carry/bootstrap (hourly only).
- Contamination caveat next to EVERY Y4/post-release number: B7 idea formed AFTER
  oc_cascadedelay replica covered all five years incl. the post-release year -> Y4 is a
  LABELLED DIAGNOSTIC (not clean evidence); new evidence here comes from the D13BF base,
  Bybit prices, carry overlay and bootstrap only; only prospective paper could confirm B7.
- Gate costs inside the engine (maker 0.0002 / taker 0.00055 / longs pay 0.0001 per 8h;
  carry fees spot 0.001/side + fut 0.00055/0.0002 frozen).

## Compute plan (heavy_slot, resume-safe)

- `boost_rule.py`: pure helpers copied VERBATIM from oc_cascadeboost (`close_returns`,
  `trailing_sigma`, `triggers_of`, `boosted_mask`, `anchor_of`; BOOST 1.5, B7_DAYS 7) — no data
  access; unit-tested.
- `compute_b7frontier_engine.py`: NEW engine rows D13B7_base + D13B7_S5 only
  (kd 1.3, no G cap, B7 tilt; S5 Bybit pattern exactly as oc_cboostbybit/oc_c2frontier);
  full-window runs [DEV0,Y1); sequential shifts 0..3 (one heavy process at a time), heartbeat
  print every 600 s, caches `tmp/runs_D13B7_base.pkl` / `tmp/runs_D13B7_S5.pkl`
  (resume-safe: skip cached shifts). Invoked as `.venv/Scripts/python.exe
  scripts/heavy_slot.py run --tag oc_b7frontier_eng --min-free-gb 2.0 -- .venv/Scripts/python.exe
  research/tournament/oc_b7frontier/compute_b7frontier_engine.py [--job ...]`. Long jobs: nohup
  + log under tmp/, poll the log. Progress print every 10 minutes.
- `analyze_b7frontier.py`: CPU-only scoring (reset metric + v388.mix + wins + worst marked
  episode for BOT legs; ONE-account carry overlay f=0/0.25 + stationary bootstrap exactly as
  oc_c2carry for all 6 BOT legs) -> `tmp/b7frontier_table.json`; REPORT.md + results.json
  written from that table only (+ quoted/copied rows, labelled). G2 baseline reproduced exactly
  before any overlay; else STOP.
- Deliverables: PLAN.md (this file), boost_rule.py, compute_b7frontier_engine.py,
  analyze_b7frontier.py, results.json, REPORT.md, tests/test_oc_b7frontier.py (>=1
  causality/truncation test + >=1 hand-checked synthetic case;
  `.venv/Scripts/python.exe -m pytest tests/test_oc_b7frontier.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the original row stays
  and the change is a disclosed extra row.)
