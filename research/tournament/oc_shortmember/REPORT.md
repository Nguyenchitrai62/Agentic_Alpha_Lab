# oc_shortmember REPORT (2026-10-07 wave; PLAN.md frozen pre-registration)

## Question
Retrain whale-flow member A/Aq (trained on 7-day h=42) directly on a SHORT label
(h=6 = 1d, h=18 = 3d)? Rows: G2 (deployed), AS6 (h=6), AS18 (h=18).

## Gates first
- Builder check: PASS. Spearman(repro, cache) = 1.000000 in EACH of 5 anchor
  years for A and for Aq (>= 0.999 required). `tmp/check.log` 19:47-19:57 UTC.
- G2 reproduction: EXACT. FULL == v421_result[R2B1D17BFG2] to the digit:
  R5 5.41, max-yearly DD 16.91, full-path DD 16.82. Engine replica confirmed.
- Costs (gate): maker 0.0002, taker 0.00055, longs pay 0.0001/8h, shorts zero;
  no fill minutes 0-4 after 4h close; stop-first. Engine v421 R2B1D17BFG2
  (inv, k 1.0, kd 1.7, bear True, G 2.0, agents ON, win_start 5, shifts 0-3).

## Engine per-year (R = %/month geometric, reset metric; DD yearly; win = all trades)
G2/FULL:  2021 2.588 / 10.86 (5001, .613) | 2022 3.282 / 16.91 (4802, .657)
  | 2023 6.045 / 15.81 (5979, .696) | 2024 10.677 / 8.27 (5010, .670)
  | 2025 4.648 / 12.90 (5783, .627) [labelled, scored once]
  dev4 mean 5.601, W 2.588, DD 16.91, losing 0; R5 5.41, full-path DD 16.82.
  Book-episode win .503-.538/yr (G2 books alone ~51%, as known).
AS18 (CHOSEN, dev4 only for selection): 2021 2.704 / 11.45 | 2022 3.042 / 18.02
  | 2023 6.174 / 15.55 | 2024 10.488 / 8.42
  | 2025 4.628 / 12.72 (5809, .625) [labelled, scored once]
  dev4 mean 5.556, W 2.704, DD 18.02, losing 0; R5 5.37, full-path DD 18.05.
AS6 (NON-CHOSEN, dev4 only; 2025 redacted): 2021 2.237 / 13.38
  | 2022 3.323 / 17.11 | 2023 6.530 / 15.78 | 2024 10.602 / 9.10
  dev4 mean 5.623, W 2.237, DD 17.11, losing 0.
Selection (dev4 ONLY, robust): all pass DD<=20 + no losing + mean>=5;
  highest dev4 WORST-year R: AS18 2.704 > G2 2.588 > AS6 2.237 -> choose AS18.
  Engine deltas are noise-scale (dev4 means within 0.07 pp).

## Member IC (pooled Spearman/yr, annual members; descriptive, no selection)
h=1:  A .0131/.0172/.0248/.0234 (+2025 .0316); AS6 .0055/.0239/.0212/.0273 (+2025 .0142); AS18 .0156/.0207/.0229/.0233 (+2025 .0330).
h=6:  A .0293/.0097/.0518/.0303 (+2025 .0577); AS6 .0022/.0162/.0349/.0361 (+2025 .0119); AS18 .0381/.0162/.0444/.0287 (+2025 .0491).
h=18: A .0355/.0206/.0795/.0412 (+2025 .0841); AS6 .0047/.0070/.0447/.0515 (+2025 .0419); AS18 .0497/.0364/.0698/.0385 (+2025 .0732).
h=42: A .1092/-.0423/.0741/.1041 (+2025 .0845); AS6 .0623/-.0753/.0273/.0802 (+2025 .0798); AS18 .1050/-.0144/.0610/.0934 (+2025 .0759).
Read: short-label training did NOT consistently sharpen short-horizon IC
(AS18 best at h=18 only in 2021-2022; A best at h=18 in 2023, at h=6 in 2023;
AS6 best at h=6 only in 2024); at h=42 deployed A stays best (3/4 dev yrs).
2025 column labelled (not used for selection).

## What failed / did not transfer
- Hypothesis rejected at engine level: AS6/AS18 dev4 means (5.623/5.556)
  bracket G2 (5.601); worst-year gain of AS18 (+0.12 pp over G2) is within
  run noise; R5 AS18 5.37 < G2 5.41; recent year AS18 4.628 < G2 4.648,
  both < 5 alone. No row meets gate (a)+(b)+no-losing (recent < 5 for all).
- Book-episode win unchanged (~.47-.53 all rows/years): short labels did not
  fix the MANUAL book win-rate problem either.

## Leakage checklist
- Feature timing: builders reused unchanged (TV/flow merge on (t,sym), rows
  from bars <= t close); audited v240/v144 path; tests assert truncation
  invariance for realised labels.
- Label windows: y_hnew realised at t+1+hnew; trained only where realised
  before native cutoff (t+(h_orig+1)*4h < cutoff, cutoffs 102/144/78 bars =
  17d/24d/13d >= 7d embargo). Conservative subset of before-anchor-7d.
- Fit windows: all fits end before anchor-embargo; fresh models per year train
  only before Y-embargo; Aq same per quarter. No test-year statistic in any fit.
- Fill timing: inherited replica (minute-5+ trade-through, SL market/TP limit,
  stop-first). Tests: `tests/test_oc_shortmember.py` 5 passed (relabel
  hand-check, truncation causality, filter-requires-realised, bear, bins).

## Verdict (Vietnamese, 3 lines)
- Tu choi gia thuyet: huan luyen A/Aq tren nhan ngan (h=6/18) khong cai thien G2 (dev4 ~5.56-5.62 vs 5.60, R5 thap hon, win book khong doi).
- Chon AS18 theo tieu chi robust dev4 (W cao nhat 2.70) nhung day la nhieu hon tin hieu; nam gan nhat ca G2 va AS18 deu < 5%/thang.
- Khong ap dung; huong short-label dong lai, khong can bang chung prospective them.
