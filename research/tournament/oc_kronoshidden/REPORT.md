# oc_kronoshidden — REPORT (written early 2026-10-07, updated as stages complete)

Clean test of the Kronos dip tilt (research/tournament/kronos V1 rule, risk = -low1)
on post-release data. Dev years are IN Kronos's training data (UPPER BOUND);
the most recent year 2025-09-24 .. 2026-09-23 is AFTER its release (VERDICT).

STATUS: DONE. Part A DONE (features frozen, no rerun). Part-B stage 1 (dev:
REF/K1/K2/CTRL, 16 sims) + stage 2 (most-recent year: K2 + CTRL run full
window, REF from cache; K1's last year NEVER run) complete. pytest 5/5.

## Part A — features (DONE, FROZEN)

- Code: copy of research/tournament/kronos/{model/,kronos_fast.py,build_bars.py,
  run_inference.py} with IDENTICAL settings (Kronos-small + Tokenizer-base,
  ctx 400x4h, pred_len 6, S=64, T=1.0, top_p=0.9, top_k=0, seed 1234, fp32,
  per-window z-norm + clip 5). No inference rerun (continuation note: leader
  resumed the GPU run after the first worker was killed; XRP shifts 2-3 were
  computed in a resumed process with a different RNG stream — sampling noise
  only; shift-0 overlap below shows shift-0 is unaffected).
- Bars: 4h OHLCV, 5 majors, shifts 0..3, from raw Binance USD-M 1m
  (data/raw/btc_intraday_20260924 + data/raw/majors_intraday_20260924).
  Junctions: overlap=0, gap=1min at every year junction, no dups, no gaps
  (research/tournament/oc_kronoshidden/bars_4shift_coverage.txt). Cross-checks:
  BTC hidden duplicate 2025-09-23..2026-09-24 close agreement 1.000000;
  majors_1m_oos_20261006 (2026-09-24..2026-10-05, no quote_volume) extension only.
- Cheap checks by this worker (tmp/check_partA.py, CPU only):
  kronos_features_4shift.parquet = 260,325 rows, 20/20 (sym,shift) groups,
  range 2020-10-06 .. 2026-09-23, cols sym/shift/T/sigma/C0/er1/er6/vol1/vol6/
  rng1/low1/pdrop2/pdrop3, zero NaNs.
  Shift-0 overlap vs research/tournament/kronos/kronos_4h_features.parquet on
  2025-06-01..2025-09-23 (n=3,425 bars):

| feat | Spearman | medabs |
|---|---|---|
| er1 | 0.9628 | 0.08112 |
| er6 | 0.9725 | 0.06774 |
| vol1 | 0.8612 | 0.06117 |
| vol6 | 0.8258 | 0.05195 |
| rng1 | 0.9502 | 0.07830 |
| low1 | 0.9686 | 0.06994 |
| pdrop2 | 0.8933 | 0.01562 |
| pdrop3 | 0.8169 | 0.00000 |

  low1 per coin: BNB 0.9787 / BTC 0.9584 / ETH 0.9672 / SOL 0.9504 / XRP 0.9750.
  low1 rho 0.9686 > 0.9 GATE — PASS (residual = S=64 sampling noise).

## Part-B fits (pre-registered rule, outcomes only from harness training rows)

- Per anchor A in {2021,2022,2023,2024,2025}-09-24: TRAINING = majors rows of
  harness.load() with t_exit < A - 7d AND shift-0 low1 present (join on (sym,T)).
  risk = -low1; direction = sign of Spearman(risk, y_dep) (>0: high-risk
  favourable); edges q20/q80 of risk. K1: 1.5 favourable outer quintile /
  0.5 unfavourable / 1 else; K2: 1.25 / 0.75; missing feature -> 1.
  Fits of anchor A applied to all four shifts in year A. Most-recent-year fits
  use all harness rows with t_exit < 2025-09-17.
- CTRL = exposure-matched control: constant per-year multiplier = K1's mean
  realised multiplier for that year. Pre-registered operationalisation: the
  feature-table DECISION mean of the K1 rule over all (coin, shift, T) rows in
  year y (no outcome data, computable before any engine run); engine-logged
  sized-means reported as diagnostic next to it.

FITS TABLE (tmp/make_fits.py output 2026-10-07; harness majors rows joined to
shift-0 low1 on (sym,T): 9,831/10,100 with feature):

| anchor A | dir | Spearman(risk,y_dep) train | q20 | q80 | n_train_maj | n_train_kron |
|---|---|---|---|---|---|---|
| 2021-09-24 | +1 | 0.0185 | 0.8558 | 2.9066 | 2,338 | 2,069 |
| 2022-09-24 | +1 | 0.0840 | 0.5435 | 2.3280 | 4,147 | 3,878 |
| 2023-09-24 | +1 | 0.0809 | 0.5315 | 2.1136 | 6,002 | 5,733 |
| 2024-09-24 | +1 | 0.0793 | 0.5753 | 2.1936 | 8,345 | 8,076 |
| 2025-09-24 | +1 | 0.0659 | 0.5872 | 2.1828 | 10,056 | 9,787 |

All five anchors: high risk (-low1 deep) favourable, same sign as kronos V1.
CTRL decision-means (K1 rule over all (coin,shift,T) feature rows in year y,
pooled; K2 in brackets): y0 0.774110 (0.887055, n=43,800); y1 0.884498
(0.942249); y2 0.967523 (0.983761); y3 0.916096 (0.958048); y4 0.889174
(0.944587, n=43,785). Below 1.0: test-year risk mass sits below the training
q20 (more 0.5 assignments) — the control matches this exposure year by year.

## Part-B engine (4-phase, heavy_slot; mechanism = copy of v414_dvol_tilt.py)

- G2 reference RUNS entry rule="inv", k=1.0, kd=1.7, bear=True, G=2.0
  (= v421 R2B1D17BFG2). REF row loaded from v421/v421_runs.pkl cache AND
  re-run through this worker's code path; must reproduce 5.41 / 16.91 / 16.82
  else STOP.
- Stage 1 (dev only, live1 = 2025-09-24+sh): REF, K1, K2 per shift; validate
  REF; compute CTRL dev constants; run CTRL dev; score dev4; robust pick K1/K2.
  Stage 2 (ONLY chosen + REF + CTRL touch the most recent year).
- Costs (gate): maker 0.0002, taker 0.00055, longs pay 0.0001/8h, shorts 0.
  Limits fill only on 1m trade-through, nothing in first 5 min after a 4h close
  (win_start=5); stop-first in shared 1m bar (engine handles).
- Leakage checks: feature timing (400 bars closing <= T on that shift's grid;
  tilt uses only (coin, holding-bar T)); label windows (harness t_exit <
  A - 7d); fit windows (shift-0 only + 7d embargo); fill timing (win_start=5,
  trade-through). No statistic from any test year feeds any choice.

## Dev results (CONTAMINATION CAVEAT: dev years likely IN Kronos pretraining -> UPPER BOUND)

REF row re-run through this worker's code path is BIT-IDENTICAL (max abs diff
0.0) to v421_runs.pkl on the dev segment (shift 0 checked point-wise; all
shifts reproduce v421_result G2 years 0..3 R/DD to the digit). Stage-2 dev
segments equal stage-1 (determinism check passed).

4-phase reset %/mo (yearly DD in brackets) per dev year [2021, 2022, 2023, 2024]:

| row | y0 | y1 | y2 | y3 | dev4 mean | dev4 WORST | max yearly DD | full-path DD dev |
|---|---|---|---|---|---|---|---|---|
| REF (G2, UPPER BOUND) | 2.588 (10.86) | 3.282 (16.91) | 6.045 (15.81) | 10.677 (8.27) | 5.601 | 2.588 | 16.91 | 16.82 |
| K1 1.5/0.5 (UPPER BOUND) | 2.232 (12.44) | 3.666 (15.30) | 7.126 (15.70) | 10.411 (8.80) | 5.811 | 2.232 | 15.70 | 15.06 |
| K2 1.25/0.75 (UPPER BOUND) | 2.469 (11.78) | 3.478 (16.20) | 6.679 (15.69) | 10.653 (8.54) | 5.772 | 2.469 | 16.20 | 16.09 |
| CTRL exposure const (UPPER BOUND) | 2.354 (9.73) | 3.252 (16.26) | 5.987 (15.78) | 10.206 (7.85) | 5.406 | 2.354 | 16.26 | 16.17 |

All-trade win rate / rung fills / book trades per dev year:
REF 0.6130/4077/926, 0.6582/3940/855, 0.6966/4979/994, 0.6711/3857/1159;
K1 0.6141/4084/941, 0.6574/3925/841, 0.6953/4882/983, 0.6700/3798/1159;
K2 0.6129/4080/939, 0.6581/3936/852, 0.6956/4933/1004, 0.6705/3831/1162;
CTRL 0.6139/4089/944, 0.6592/3987/857, 0.6969/5001/997, 0.6723/3887/1163.
Mean multiplier (decision | engine-sized): K1 0.774|0.773, 0.884|0.906,
0.968|1.046, 0.916|1.010; K2 0.887|0.886, 0.942|0.953, 0.984|1.023,
0.958|1.005 (fills skew to high-mult bars in y2 — disclosed).
K2 beats CTRL in 4/4 dev years; K1 beats CTRL in 3/4 (loses y0 by 0.12).
Robust pick on dev4 ONLY (both DD <= 20, no losing year, both mean >= 5;
highest WORST-year): K2 (W 2.469 > K1 2.232). K1's last year is never scored.

## Most-recent-year verdict (clean test; scored ONCE for chosen + REF + CTRL)

| row | %/mo | yearly DD | full-path DD | book win | rung win | all win |
|---|---|---|---|---|---|---|
| REF (G2) | 4.648 | 12.90 | 16.82 | - | - | - |
| K2 chosen | 4.801 (+0.153) | 12.10 | 16.09 | 0.5344 (1104) | 0.6480 (4665) | 0.6263 |
| CTRL | 4.648 (+0.000) | 11.84 | 16.17 | 0.5405 (1110) | 0.6496 (4694) | 0.6287 |

K2 beats REF and CTRL by +0.15 %/mo on the clean year with lower DD — but
4.801 < 5.0: the gate (b) FAILS. The dev edge (+0.17..+0.21) was measured
in-pretraining and shrank out-of-pretraining, as the contamination caveat
warned. Timing skill over exposure is marginal (K2 == CTRL to 3 digits for
CTRL vs REF; K2 - CTRL = +0.15).
Post-2026-09-23 window: NOT runnable — 1m ends 2026-09-23 23:59; the OOS
2026-09-24..2026-10-05 1m has no quote_volume (no amount -> no 4h bars);
research books end 2026-09-23 20:00; no dip-agent tables beyond Y1.

## Vietnamese verdict

K2 đạt 4,80%/tháng ở năm sạch, hơn G2 và CTRL +0,15 nhưng KHÔNG qua cổng 5%/tháng.
Dev chỉ là cận trên (Kronos đã thấy dữ liệu này lúc pretrain) nên không adopt.
Kết luận: REJECT — cần bằng chứng prospective, không đưa Kronos tilt vào G2.
