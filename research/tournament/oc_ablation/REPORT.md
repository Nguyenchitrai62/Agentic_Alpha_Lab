# oc_ablation REPORT — leave-one-layer-out ablation of G2's risk layers

Method (PLAN pre-registered, one fix before any outcome): v421 worker replica
per shift (v321 pipe + agents, bear x0.5, corr inv/kd 1.7, budget 0.442,
G 2.0, trade mode, win_start 5, default gov/vol-target/close5+8 stop).
G2 reproduced EXACTLY (5.41 / 16.91 / 16.82; years match v421_result to the
digit; per-shift eq_ends 55.993/17.031/26.262/6.264 match v421 run.log).
Patch proof: G2 via engine_patch.py (vol_fixed=None) matches the original
engine to 0.0 on all 4 shifts. NO_VT uses vol_fixed = per-shift G2 scale
median (s0 2.0, s1 1.9664, s2 1.9537, s3 2.0). Scripts: run_shift.py (heavy),
analyze_ablation.py, compute_gap.py. Repro:
`.venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_ablation --min-free-gb 2.0 -- ... run_shift.py <s>`.

## Per-year 4-phase reset R (%/mo) / DD (%), dev4 + most-recent labelled

| row | 2021 | 2022 | 2023 | 2024 | 2025-recent | dev4 mean | 5y mean | maxDD | full | worst-phase |
|---|---|---|---|---|---|---|---|---|---|---|
| G2 | 2.588/10.86 | 3.282/16.91 | 6.045/15.81 | 10.677/8.27 | 4.648/12.90 | 5.601 | 5.410 | 16.91 | 16.82 | 43.55 |
| NO_GOV | 2.830/10.52 | 3.600/20.04 | 7.756/16.07 | 10.724/8.26 | 4.824/13.07 | 6.180 | 5.907 | 20.04 | 19.60 | 26.37 |
| NO_BEAR | 2.119/15.38 | 3.636/16.91 | 6.182/15.75 | 10.648/8.22 | 4.689/12.90 | 5.597 | 5.415 | 16.91 | 16.81 | 43.08 |
| NO_CAP | 2.831/12.42 | 3.505/16.23 | 4.669/18.33 | 11.270/8.26 | 5.060/12.81 | 5.517 | 5.425 | 18.33 | 16.90 | 44.19 |
| NO_B1 | 1.804/17.13 | 1.571/18.92 | 6.213/19.58 | 12.513/11.71 | 3.986/23.65 | 5.434 | 5.142 | 23.65 | 20.20 | 45.85 |
| TOUCH | 2.796/11.25 | 2.356/18.62 | 5.647/14.50 | 10.266/8.37 | 4.519/10.10 | 5.220 | 5.079 | 18.62 | 18.56 | 30.51 |
| NO_VT | 2.393/15.66 | 2.976/17.85 | 8.232/17.93 | 12.555/13.46 | 4.772/17.56 | 6.459 | 6.119 | 17.93 | 18.39 | 45.62 |

NO_CAP years equal the stored uncapped R2B1D17BF (2.831/3.505/4.669/11.27/5.06) —
sanity check that the cap hook is the only difference. No losing year in any row.

## Return bought / DD bought per layer (row minus G2; +R = row has more)

| removed layer | dR dev4 | dR recent | dMaxDD | dFull | dGap(-10%) |
|---|---|---|---|---|---|
| GOV (off) | +0.579 | +0.176 | +3.13 | +2.78 | -0.22 |
| BEAR (off) | -0.004 | +0.041 | 0.00 | -0.01 | -0.26 |
| CAP (off) | -0.084 | +0.412 | +1.42 | +0.08 | +28.00 |
| B1 (off) | -0.167 | -0.662 | +6.74 | +3.38 | +1.91 |
| close5->touch | -0.381 | -0.129 | +1.71 | +1.74 | +0.04 |
| VT (fixed median) | +0.858 | +0.124 | +1.02 | +1.57 | +1.62 |

Gap test (-10% all-coin, mix worst minute): G2 32.86% at 2025-09-25 17:57
(gross 3.269, dip 1.771, book 1.499); NO_GOV 32.64; NO_BEAR 32.60; NO_CAP
60.86% at 2025-08-14 12:34 (gross 6.056, dip 5.566 — the oc_gapstress uncapped
worst minute, reproduced); NO_B1 34.77; TOUCH 32.90; NO_VT 34.48.
Engine totals (4 phases): G2 fills 5082, rungs 21513 (stops 926, TPs 10760),
book stops 773/TPs 184; TOUCH rung stops rise to 1527 (earlier exits).

## Reading: which layers earn their keep

- B1 corr sizing earns most: removal loses return two years running and
  breaches the gate (maxDD 23.65, full 20.20). Keep.
- Close5 dip stop earns keep vs touch: +0.38 dev4 and -1.7 DD. Keep.
- Gross cap G=2.0 is cheap tail insurance: -0.08 dev4, but without it the
  -10% gap loss nearly doubles (32.9 -> 60.9%) and maxDD +1.4. Keep.
- Governor buys DD (max -3.1, full -2.8) for ~0.5-0.6 return; without it the
  account breaches 20% (20.04/19.60). Keep as the gatekeeper.
- Vol target buys DD (-1.0/-1.6) but costs ~0.86 dev4 return; account still
  passes without it, so it is a return/DD dial, not a gatekeeper. Keep for
  now; any loosening must be pre-registered.
- Bear x0.5 filter is ~zero (dev4 -0.004, DD 0.00, gap -0.26): pure
  complexity, no return and no protection in the 4-phase account. Candidate
  for a later pre-registered simplification (do NOT cut on this diagnostic).

## Limits / leakage statement

Diagnostic only, no selection; recent year labelled and never used to choose.
Features at t use only data at close of t (books ffill latest standard row <=
t_s; sigma/vol/governor/agents causal per v421; agent size/TP keyed by holding
bar); fills win_start 5 + trade-through + stop-first; costs gate-exact.
NO_VT median is an in-window per-shift constant (disclosed, not pre-anchor).
Gap rebuild uses hourly marks ffill (last closed bar) and event times only.
Single-phase DDs (up to ~45%) show phases alone are far more violent than the
4-phase mix — the mix, not any single clock, is the product.

## Verdict (tiếng Việt, kết luận chính)

B1, stop close5, cap G=2.0 và governor đều đáng giữ (bỏ B1 vỡ DD trên 20%, bỏ cap gap -10% gấp đôi lên 60.9%, bỏ governor cũng vỡ 20%, touch kém hơn close5 cả lợi nhuận lẫn DD).
Bear-filter x0.5 không mua được gì (lợi nhuận/DD/gap gần như bằng 0) nên là ứng viên cắt duy nhất, nhưng phải đăng ký hướng mới chứ không cắt theo chẩn đoán này.
Vol-target là núm return/DD (bỏ thì +0.86%/tháng nhưng +1.6 DD), giữ nguyên cho tới khi có biến thể nới lỏng được đăng ký trước.
