# oc_c2carry — PLAN (pre-registered 2026-10-07, BEFORE any outcome)

Assignment: `docs/opencode/OPENCODE_W_oc_c2carry.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md read). Write ONLY `research/tournament/oc_c2carry/`
+ `tests/test_oc_c2carry.py`. Descriptive (decision support), NO selection.
Scratch only under `research/tournament/oc_c2carry/tmp/`. No engine reruns
(all runs cached; only if a C2 path is missing, rerun that single row via heavy_slot).
CPU-only hourly analysis, no 1m reads. Heartbeat print every 10 min.

## Question (descriptive only)

Account-realistic profile of the three live candidates G2+carry vs K2+carry
vs C2+carry (C2 = Chronos-Bolt-small tilt, risk = -ch_q10, the dev4 robust pick
of oc_chronos), on Binance prices and on Bybit prices (S5): what does each print
per year, 5y, full-path DD, worst year, most-recent year, plus a bootstrap expectation.

## Frozen inputs (read-only, never edited)

- `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl` strat
  `R2B1D17BFG2` = G2 on Binance (4-phase hourly `t/eq/eq_min`).
- `research/parallel/rounds/parallel-20260906-r2/v421/v421_result.json` row
  R2B1D17BFG2 (gate: 5.41 / W 2.588 / DD 16.91 / full 16.82).
- K2 on Binance: `research/tournament/oc_kronoshidden/tmp/runs_last.pkl`
  K2 (full 2021-09-24..2026-09-23, 4 phases; prefix == `runs_dev.pkl` K2;
  == `oc_k2bybit/tmp/runs_base.pkl` K2). Cross-check vs
  `oc_kronoshidden/results.json` dev r + last-year r and
  `oc_k2bybit/tmp/k2bybit_table.json` K2_base.
- C2 on Binance: `research/tournament/oc_chronos/tmp/runs_last.pkl`
  C2 (full 2021-09-24..2026-09-23, 4 phases; == oc_c2bybit `runs_base.pkl` C2).
  Cross-check vs `oc_chronos/tmp/dev_table.json` C2 dev R/DD +
  `tmp/last_table.json` C2 last-year R + `oc_c2bybit/tmp/c2bybit_table.json` C2_base.
- S5 Bybit prices: `research/tournament/oc_k2bybit/tmp/runs_S5.pkl`
  REF (= G2 on Bybit) and K2 (= K2 on Bybit), 4 phases each, live from
  2021-11-15 (y2021 is a SHORT window, labelled everywhere); and
  `research/tournament/oc_c2bybit/tmp/runs_S5.pkl` REF (= G2 on Bybit, same
  engine, must equal the K2 file's REF to the digit) and C2 (= C2 on Bybit).
- Carry overlay: `research/tournament/oc_carrycompound/analyze_carrycompound.py`
  (f = 0.25, compounding on TOTAL equity; verbatim method copied from
  `research/tournament/oc_k2carry/analyze_k2carry.py`, not re-derived) +
  `research/tournament/oc_cashcarry/results.json`
  (33 entered frozen, threshold 0.04, 13 skipped, 2 incomplete) +
  `data/raw/qbasis_20261003`, `data/raw/spot_majors_20260925`,
  `research/tournament/ext/hourly_ext.parquet`.
- Bootstrap model: `research/tournament/oc_mcdd/mcdd_bootstrap.py`
  (stationary Politis-Romano; here mean block 10 days, 4000 draws, seed 0).
- Method source of truth: `research/tournament/oc_k2carry/analyze_k2carry.py`
  copied exactly (same grid, same carry MtM, same ONE-account compounding,
  same reset/full-path/DD/bootstrap code); only the BOT-leg dict is extended
  with the two C2 legs. First gate reproduces the 8 oc_k2carry numbers.

## Rows (ONLY these 12; no tuning, no extra knob, no selection)

BOT legs (6): G2-Binance, K2-Binance, C2-Binance, G2-Bybit(S5), K2-Bybit(S5), C2-Bybit(S5).
Each with carry f = 0.0 (BOT alone) and f = 0.25 (BOT + carry, compounding).
Labels: `G2_bin`, `G2c_bin`, `K2_bin`, `K2c_bin`, `C2_bin`, `C2c_bin`,
`G2_by`, `G2c_by`, `K2_by`, `K2c_by`, `C2_by`, `C2c_by` (`c` = +carry f 0.25).
Result keys (oc_k2carry convention): `G2_binance`, `G2_carry_binance`,
`K2_binance`, `K2_carry_binance`, `C2_binance`, `C2_carry_binance`,
`G2_bybit_S5`, `G2_carry_bybit_S5`, `K2_bybit_S5`, `K2_carry_bybit_S5`,
`C2_bybit_S5`, `C2_carry_bybit_S5`.

## Method (fixed, verbatim oc_k2carry)

- Hourly grid 2021-09-24 04:00 .. 2026-09-23 12:00 UTC (same as carrycompound).
  Per BOT leg: per-phase hourly Es/Ms via `v388.hourly` (ffill causal,
  `eq_min` shifted -4h, `min(lo,e)`), 4-phase means Etot/Mtot.
- Carry MtM per pair (alloc units) on the grid: causal last-CLOSED-hourly
  S/F strictly before t, 0 before entry-close, frozen `ret_alloc` from
  settlement; entry-paid fee 0.001+0.00055 while open (same as carrycompound).
- Compounding account (ONE account, UTA assumption):
  `A(t) = A(t-1)*(1+r_bot(t)) + dU(t)`, `r_bot` from the stored 4-phase mix
  of THAT BOT leg (sizes on TOTAL equity), `dU` = carry MtM change on
  notionals N = f x A at each entry (spanning positions at a reset use f x 1.0).
  Marked path `M(t) = A(t-1)*(ms_base(t)/es_base(t-1)) + dU(t)`.
  f = 0 short-circuits to base bit-exact (no cumprod drift).
- Per-year reset to 1.0 (`reset_metric.year_reset` arithmetic; spanning carry
  rebased to 0 at each anchor). Full-path DD continuous from grid start,
  v421 formula (max of marked/close DD on the segment > 2021-09-24).
- Metrics per row: 5 yearly R %/mo + DD %, 5y geo mean R, W (worst of the 5),
  max yearly DD, losing count, full-path DD (marked/close/full), most-recent
  year 2025-09-24..2026-09-23 labelled (diagnostic re-score everywhere here:
  K2's and C2's last year were already scored once by oc_kronoshidden /
  oc_chronos for base — every Y4 number here is a labelled re-score, never a
  selection input).
- Reproduction gates (STOP + report if failed):
  G2_bin f=0 == v421 G2 to the digit; G2_bin f=0.25 == carrycompound
  (5.634 / 16.75 / 16.66); K2_bin f=0 == oc_kronoshidden/base-K2 to the digit;
  G2_by f=0 == oc_k2bybit REF_S5 and K2_by f=0 == K2_S5 to the digit (the 8
  oc_k2carry numbers); C2_bin f=0 == oc_chronos C2
  (dev 2.711/11.52, 3.460/15.48, 6.250/15.07, 10.721/8.29; Y4 4.754/12.86;
  full-path 15.42) to the digit; C2_by f=0 == oc_c2bybit C2_S5
  (years 2.213/12.21 SHORT, 3.062/16.50, 5.415/16.65, 10.527/9.27, 4.558/12.22;
  5y 5.115; full 16.50) to the digit; REF_S5 in the C2 file == REF_S5 in the
  K2 file to the digit (same engine).
- Bootstrap per row (descriptive): daily close E + daily marked low M from
  the continuous account (00:00 UTC ffill, causal); daily r + low-ratio l;
  stationary bootstrap mean block 10 d, 4000 paths x 365 d, seed 0, circular;
  report median %/mo, P(month >= 5%), P(marked DD > 20% in a year),
  P(losing year). Binance universe 2021-09-24..2026-09-23; Bybit universe
  2021-11-15..2026-09-23 (live only, labelled). Carry marks are close-marked
  (DD lower bound); bootstrap assumes ~stationary daily returns, ~10-day
  dependence only (no annual regime structure).

## Costs / execution (fixed, gate)

maker 0.0002, taker 0.00055 (stops/market taker), longs pay 0.0001/8h,
shorts 0. Inside the stored engine paths; carry fees as frozen
(spot 0.001/side + fut 0.00055/0.0002). Limits fill only on 1m
trade-through (inherited); carry leg close-marked (DD lower bound).

## Selection

NONE. Descriptive only: no pick, no adopt/reject of C2/K2/carry.
REPORT ends with a 3-line Vietnamese verdict + a <= 15-line Vietnamese
summary of what the owner should expect on Bybit with G2, with K2 and with
C2 (all + carry, as ordered), plus `results.json` and pytest
(`tests/test_oc_c2carry.py`: causality/truncation + hand-checked synthetic).

## Leakage / contamination (pre-registered, stated in REPORT)

- Feature timing: BOT tilts use only bars closing <= T (inherited Part A);
  carry MtM uses last CLOSED hourly bar strictly before t; no 1m peeking.
- Label/fit windows: no refit here; K2/C2 fits frozen (harness t_exit < A - 7d,
  shift-0 only); carry rule frozen (threshold 0.04 from oc_cashcarry);
  year y uses anchor-y fit only. S5 is a price-source switch, not a fit.
- Fill timing: inherited engine (win_start=5, trade-through, stop-first).
- Contamination caveat next to EVERY Binance+Bybit dev number:
  Kronos pretraining likely saw dev years -> K2 dev edge is an UPPER BOUND;
  Chronos-Bolt (2024-11, mostly non-crypto + synthetic) has LESS risk but dev
  is still labelled possibly-contaminated -> C2 dev edge is an UPPER BOUND too
  (smaller caveat); the most-recent year is the only clean year (but already
  scored once for base K2 and base C2 -> labelled re-score here). Carry overlay
  is post-hoc (needs prospective paper).

## Post-hoc log

- (pre-outcome entries only below this line go here as they happen)
