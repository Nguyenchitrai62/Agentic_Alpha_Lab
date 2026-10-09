# audit_c2 — REPORT (blind replication of the Chronos C2 dip tilt on G2)

## What was done
Independent blind implementation of C2 (risk=-ch_q10, direction=sign
Spearman, q20/q80 edges, mult 1.25/0.75/1, missing->1) on G2 (v421 rule inv
k1.0 kd1.7 bear G2.0, per-(coin,holding-bar) tilt copied from v414, budget
unchanged), 4-phase engine via heavy_slot. REF from v421_runs.pkl bit-exact
(reproduced 5.41/16.91/16.82). replication.json saved BEFORE opening any
oc_chronos output; comparison after. PLAN.md pre-registered before any outcome.

## Results (4-phase reset %/mo, yearly DD in brackets; contamination: dev = UPPER BOUND)

| row | 2021 | 2022 | 2023 | 2024 | dev4 | 2025-09-24..2026-09-23 (clean, ONCE) | 5y | full-path DD |
|---|---|---|---|---|---|---|---|---|
| REF (G2) | 2.588 (10.86) | 3.282 (16.91) | 6.045 (15.81) | 10.677 (8.27) | 5.601, W 2.588, DD 16.91 | 4.648 (12.90) | 5.410, W 2.588 | 16.82 |
| C2 (blind) | 2.711 (11.52) | 3.460 (15.48) | 6.250 (15.07) | 10.721 (8.29) | 5.739, W 2.711, DD 15.48 | 4.754 (12.86) | 5.542, W 2.711 | 15.42 |

No losing year in dev4 or 5y for either row; DD <= 20 everywhere.
C2 vs REF: dev4 +0.138 pp/mo, clean year +0.106 pp/mo, full-path DD -1.40 pp.
C2 clean year 4.754 < 5.0 gate (b) — fails the gate despite beating REF.

## Comparison to oc_chronos
Fits bit-identical (all 16 digits, all 5 anchors dir +1); engine R/DD
identical to the digit in all 5 years; multiplier vectors 2000/2000 agree;
full-path DD identical. Verdict: PASS-WITH-NOTES (see COMPARISON.md; only
note is the unused anchor_of() helper).

## What failed / why
Nothing failed in the replication itself. The C2 tilt replicates exactly but
does not pass the user gate on the clean year (4.754 < 5.0), agreeing with
oc_chronos's own REJECT. No prospective evidence is created by this audit.

## Leakage checks
- Feature timing: forecast for bar open T uses ONLY the 512 closes of bars
  closing <= T on that shift's grid (oc_chronos/run_chronos_4shift.py:95) and
  sigma from opens <= T only (loc. cit.:84-85); 200 random ch_q10 rows
  recomputed from bars truncated at T match stored values (max diff 4.2e-05;
  research/tournament/audit_c2/check_truncation.py + tmp/truncation_check.json).
- Label windows: harness t_exit < A-7d only (test asserts truncation per anchor).
- Fit windows: shift-0 join only; 2025 fit uses rows t_exit < 2025-09-17; no
  test-year statistic feeds any fit.
- Fill timing: engine win_start=5, 1m trade-through only, stop-first
  (inherited from v421/v414 path; asserted in source).
- Costs: gate maker 0.0002 / taker 0.00055, longs 0.0001/8h, shorts 0.

## Contamination (Chronos-Bolt pretraining vs dev4 years 2021-2024)
- Model card (HF amazon/chronos-bolt-small): T5-based, trained on ~100B
  time-series observations; zero-shot benchmark over 27 datasets (Chronos
  paper arXiv:2403.07815). Released 2024-11-26 on HF (chronos-forecasting
  news). Package chronos-forecasting 2.3.2 (pylib METADATA cites the same paper).
- Training-corpus list (public HF dataset autogluon/chronos_datasets, 67
  subsets incl. training_corpus_tsmixup_10m + training_corpus_kernel_synth_1m):
  energy/weather/retail/traffic/M4-M5/Monash/Wikipedia/synthetic — contains NO
  crypto or crypto-exchange price series. The only exchange-rate data is the
  `exchange_rate` subset (8 daily TradFi FX series) plus pre-2016 traditional
  M4 finance series.
- Meaning for dev4: the model cannot have memorised 2021-2024 crypto 4h bars
  (never seen any crypto); dev numbers are an UPPER BOUND only in the weak
  sense that generic financial dynamics (FX/M4) may transfer. The
  post-release year (2025-09-24..2026-09-23, after the 2024-11 release) is clean.

## Vietnamese verdict (3 lines)
C2 tái tạo khớp hoàn toàn, năm sạch chỉ 4,75%/tháng nên không qua cổng 5%/tháng.
Dev là cận trên do model từng thấy động lực tài chính chung, nhưng không có crypto trong pretraining.
Kết luận: REJECT — cần bằng chứng prospective, đồng ý với oc_chronos.
