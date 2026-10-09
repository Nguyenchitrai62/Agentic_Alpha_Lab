# oc_kronosbase — REPORT (DONE 2026-10-08; Kaggle inference + engine + placebo)

Question: does Kronos-base (102M) carry the K2 signal more strongly than
Kronos-small with the identical rule? ANSWER: marginally stronger in-sample
and on the clean year, but the clean year still misses the 5%/mo gate — NO
upgrade. A negative result is valid; G2 unchanged.

STATUS: DONE. Part A DONE (base features 260,325 rows via 5 private Kaggle
GPU kernels). Part B DONE (REF+K2 reproduced, KB2/KBK2 dev4, KB2 last year
scored ONCE). pytest 5/5.

## Part A — features (Kaggle, account 1, DEFAULT auth, private only)

- Dataset (ONE, private, public Binance market data only):
  `nguynchtrai/bars-4h-4shift-oc-kronosbase` (bars_4h_4shift.parquet,
  10,648,736 B, from research/tournament/oc_kronoshidden). No other uploads.
- Kernels (all PRIVATE, GPU, single-file bundle — kronos_fast.py + model/
  bit-identical to oc_kronoshidden, weights NeoQuasar/Kronos-base +
  Tokenizer-base from HF hub inside the kernel, one run per clock shift):
  oc-kronosbase-verify50 (v2, COMPLETE), oc-kronosbase-s0/s1/s2/s3 (v1,
  all COMPLETE). No second account; no token read/printed/copied.
- Settings EXACT per PLAN: ctx 400x4h, pred_len 6, S=64, T=1.0, top_p=0.9,
  top_k=0, seed 1234, fp32, per-window z-norm + clip 5, same bars/T range,
  same 8 features + sigma/C0. Forecast for bar open T uses ONLY 400 bars
  closing <= T on that shift's grid.
- verify50 GATE (small, same bundle, 50 first shift-0 rows): max abs diff
  low1 = 0.098944, median abs = 0.029258. Full shift-0 recompute (65,085 rows):
  Spearman 0.9730, median abs 0.0638, mean abs 0.1015 — matches oc_kronoshidden
  overlap (rho 0.9686, medabs 0.0699, S=64 sampling noise). GATE PASS.
- Output: `kronosbase_features_4shift.parquet` (260,325 rows, 20/20
  (sym,shift) groups, 2020-10-06 .. 2026-09-23, cols sym/shift/T/sigma/C0/er1/
  er6/vol1/vol6/rng1/low1/pdrop2/pdrop3, zero NaNs; per-shift 65085/65080/
  65080/65080). Downloaded outputs only.

## Part-B fits (pre-registered rule, harness rows only)

- Per anchor A: TRAINING = majors harness.load() rows with t_exit < A - 7d AND
  shift-0 base low1 present (join on (sym,T)); risk = -low1_base; direction =
  sign of Spearman(risk, y_dep); edges q20/q80. Mult 1.25 fav / 0.75 unfav / 1
  else; missing -> 1. Fits of A applied to all four shifts in year A.

| anchor A | dir | rho | q20 | q80 | n_maj | n_kron |
|---|---|---|---|---|---|---|
| 2021-09-24 | +1 | 0.0024 | 1.0792 | 4.2129 | 2,338 | 2,069 |
| 2022-09-24 | +1 | 0.1034 | 0.6231 | 2.9457 | 4,147 | 3,878 |
| 2023-09-24 | +1 | 0.0959 | 0.5903 | 2.6236 | 6,002 | 5,733 |
| 2024-09-24 | +1 | 0.0891 | 0.6468 | 2.8596 | 8,345 | 8,076 |
| 2025-09-24 | +1 | 0.0737 | 0.6607 | 2.9076 | 10,056 | 9,787 |

All five anchors +1 (same sign as small; small rhos 0.0185/0.0840/0.0809/
0.0793/0.0659). Base-vs-small low1 Spearman (shift-0, join on (sym,T),
n=65,085): pooled 0.8547; BNB 0.8702 / BTC 0.8294 / ETH 0.8373 / SOL 0.8457 /
XRP 0.8843. Same ranking, not identical.

## Part-B engine (G2 path verbatim via run_engine_base.py; heavy_slot)

- Mechanism = oc_kronoshidden run_engine.py verbatim (pipe v321, corr-aware
  inv kd=1.7, bear books, budget 0.26*1*1.7, G=2.0, win_start=5, gate costs
  inside). Reproduction gates PASS: REF bit-identical to v421 G2 years 0..3
  (2.588/3.282/6.045/10.677, DD 10.86/16.91/15.81/8.27); K2 dev R matches
  oc_kronoshidden (2.469/3.478/6.679/10.653) to 0.002; REF last 4.648/12.90/
  16.82 and K2 last 4.801 reproduce exactly.
- Gate costs: maker 0.0002, taker 0.00055, longs pay 0.0001/8h, shorts 0.
  Limits fill only on 1m trade-through, nothing in first 5 min after a 4h
  close; stop-first in shared 1m bar (engine handles).

## Dev results (CONTAMINATION CAVEAT: dev years likely IN Kronos pretraining -> UPPER BOUND)

4-phase reset %/mo (yearly DD in brackets) per dev year [2021, 2022, 2023, 2024]:

| row | y0 | y1 | y2 | y3 | dev4 mean | dev4 WORST | max yearly DD | full-path DD dev |
|---|---|---|---|---|---|---|---|---|
| REF (G2, UPPER BOUND) | 2.588 (10.86) | 3.282 (16.91) | 6.045 (15.81) | 10.677 (8.27) | 5.601 | 2.588 | 16.91 | 16.82 |
| K2 small (UPPER BOUND) | 2.469 (11.78) | 3.478 (16.20) | 6.679 (15.69) | 10.653 (8.54) | 5.772 | 2.469 | 16.20 | 16.09 |
| KB2 base (UPPER BOUND) | 2.524 (10.92) | 3.479 (16.23) | 6.844 (15.73) | 10.683 (8.42) | 5.834 | 2.524 | 16.23 | 16.12 |
| KBK2 avg (UPPER BOUND) | 2.519 (11.30) | 3.472 (16.20) | 6.753 (15.68) | 10.658 (8.46) | 5.803 | 2.519 | 16.20 | 16.08 |

All-trade win / rung fills / book trades per dev year:
KB2 0.6136/4083/943, 0.6574/3944/854, 0.6971/4931/1031, 0.6711/3831/1161;
KBK2 0.6137/4081/941, 0.6573/3940/848, 0.6972/4932/993, 0.6707/3833/1162
(K2/REF in tmp/dev_table_base.json).
Mean multiplier (engine-sized): KB2 0.849/0.946/1.022/1.003;
KBK2 0.868/0.949/1.023/1.004.
Robust pick on dev4 ONLY (both DD <= 20, no losing year, both mean >= 5;
highest WORST-year): KB2 (W 2.524 > KBK2 2.519). KBK2's last year never run.

## Most-recent-year verdict (clean test; scored ONCE for KB2 + REF + K2)

| row | %/mo | yearly DD | full-path DD | 5y mean | book win | rung win | all win |
|---|---|---|---|---|---|---|---|
| REF (G2) | 4.648 | 12.90 | 16.82 | 5.410 | 0.5365 (1096) | 0.6478 (4671) | 0.6267 |
| K2 (ref) | 4.801 (+0.153) | 12.10 | 16.09 | 5.577 | 0.5344 (1104) | 0.6480 (4665) | 0.6263 |
| KB2 chosen | 4.826 (+0.178 vs REF, +0.025 vs K2) | 11.86 | 16.12 | 5.632 | 0.5383 (1109) | 0.6474 (4665) | 0.6264 |

Gate for KB2: (a) 5y 5.632 >= 5 PASS; (b) last year 4.826 >= 5 FAIL;
(c) no losing year PASS; DD 16.12 <= 20 PASS. Overall FAIL on (b) — same as
K2 (4.801). The +0.06 dev edge shrank to +0.025 out-of-pretraining.
Post-2026-09-23 window: NOT runnable — 1m ends 2026-09-23 23:59, research
books end 2026-09-23 20:00, no dip-agent tables beyond Y1 (same as
oc_kronoshidden).

## Placebo (D0 replica, EXACTLY like oc_k2placebo; seeds 20261007+y / 20261008+y)

KB2 per-year norm + pct (signif iff >= 95); dev years = UPPER BOUND context:

| year | KB2 norm | timing pct | block pct | K2 ref timing/block |
|---|---|---|---|---|
| 2021 (UB) | 0.9875 | 86.91 | 74.13 | 46.85 / 38.06 |
| 2022 (UB) | 1.0327 | 100.00 | 100.00 | 100.0 / 100.0 |
| 2023 (UB) | 2.3263 | 100.00 | 100.00 | 100.0 / 100.0 |
| 2024 (UB) | 3.1658 | 100.00 | 100.00 | 99.9 / 100.0 |
| 2025 clean | 0.7797 | 99.20 | 99.90 | 97.2 / 98.7 |

KB2 timing skill survives both placebos on the clean year (like K2), but the
economic magnitude (+0.025/mo over K2, +0.178 over REF) still misses the gate.

## Leakage statement (checked)

- Feature timing: forecast for bar open T uses ONLY 400 bars closing <= T on
  that shift's grid (kernel_inference.py preserves oc_kronoshidden indexing;
  bundle bit-identical except model weights).
- Label/fit windows: per-anchor harness rows t_exit < A - 7d, shift-0 join on
  (sym,T), direction = sign of Spearman, q20/q80 (tmp/make_fits_base.py;
  tests pin truncation + shift-0-only join). Fits of A applied to year A.
- Fill timing: engine reuse (win_start=5, 1m trade-through, stop-first).
- No test-year statistic fed any choice: KB2 vs KBK2 picked on dev4 only;
  last year scored once. Contamination caveat on every dev number.

## Vietnamese verdict

Kronos-base chỉ hơn Kronos-small +0,03%/tháng ở năm sạch (4,83 so với 4,80) và vẫn DƯỚI cổng 5%/tháng.
Không adopt base — “more model” không phải edge, chênh lệch dev cũng co lại ngoài pretraining.
Kết luận: REJECT — giữ nguyên G2, cần bằng chứng prospective, không đưa tilt base vào.
