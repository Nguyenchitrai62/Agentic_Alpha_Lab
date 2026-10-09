# oc_cascadedelay — REPORT (2026-10-08; PLAN frozen before any outcome)

Post-cascade depth-recovery dip delay (IDEAS5 #10, rank 10): after any 4h bar with
|close-to-close log move| > 4 x trailing-90d sigma (closes-only cascade proxy; (H-L)
range rejected per the assignment's twice-stated "from closes only"), dip budget
0.26 -> 0.13 (rung mult x0.5, market-wide per shift) for N days. V1 N = 7; V2 N = 3
(both frozen). Book untouched. Existing 4h closes only (no new data).

STATUS: DONE — gate FAIL for both variants, NO engine run (negative result, valid per
IDEAS5: "several will fail at the screen/gate").

## Triggers (frozen, causal)

- 4h closes (`oc_kronoshidden/bars_4h_4shift.parquet`), per (sym, shift): r[i] =
  ln(C[i]/C[i-1]); SIG[i] = std of r[i-540..i-1] (min_periods 120, tested bar excluded);
  fire iff |r[i]| > 4.0*SIG[i]; tc = T[i]+4h. Union over 5 majors per shift.
  (`delay_mult_4shift.parquet`, 53,877 rows = same grid size as crashgate depth file.)
- Union triggers per shift over the 5 anchor years: s0 264, s1 266, s2 263, s3 255
  (~52/yr/shift). Per-sym-shift fire rate 75-130 / ~13.4k bars (0.6-1.0%).
- Cooled time-bar share: V1 38-55 %/yr/shift, V2 20-33 %/yr/shift — the 7d/3d windows
  after union triggers cover a large fraction of time, not a rare tail. Cooled FILL
  share is even higher (V1 52-72 %, V2 37-52 %): dip fills cluster in volatile
  downdrafts that follow big bars, so the halving binds exactly where the sleeve
  earns. Full 540-return windows for all of 2021-09-24.. — no skipped year, nothing
  imputed; NaN-sigma bars never fire (counted in build log).

## Replica + placebo gate (reused D0+B1 ledger, n = 22312, base sum5y = 7.718304 exact)

| year x variant | n | base | delayed | norm | timing pct | block pct | cooled fills% |
|---|---|---|---|---|---|---|---|
| 2021 V1 / V2 | 4171 | 0.911273 | 0.472715 / 0.716256 | 0.6379 / 0.8789 | 3.5 / 22.4 | 3.1 / 20.9 | 51.8 / 37.0 |
| 2022 V1 / V2 | 4059 | 0.832599 | 0.537141 / 0.726641 | 0.8113 / 0.9456 | 32.4 / 57.6 | 30.2 / 62.5 | 67.6 / 46.3 |
| 2023 V1 / V2 | 5352 | 2.099814 | 1.372266 / 1.478029 | 2.1519 / 1.9908 | 14.7 / 1.2 | 12.6 / 1.1 | 72.5 / 51.5 |
| 2024 V1 / V2 | 3958 | 3.197390 | 2.064170 / 2.411393 | 2.9591 / 3.0689 | 0.1 / 0.1 | 0.1 / 0.1 | 60.5 / 42.9 |
| 2025 clean V1 / V2 | 4772 | 0.677229 | 0.325583 / 0.367716 | 0.4989 / 0.4857 | 2.0 / 0.1 | 1.9 / 0.2 | 69.5 / 48.6 |

- dSum5y (4-phase-mean w*y): V1 -2.946, V2 -2.018 — BOTH far below +0.273.
  Sum-half: 0/5 each (delayed < base every year). Gate needs BOTH legs:
  V1 FAIL, V2 FAIL.
- Timing percentiles are mostly LOW (0.1-32 for V1, 0.1-63 for V2): the delay is
  significantly WORSE than random time-bar reassignment — halving mechanically removes
  winners because every base year is profitable and cooled fills are the majority.
- The screen-level 2025 row above is the replica screen (same ledger years as the
  tilt studies), NOT a scored-once engine year: no engine was run, so no post-release
  engine Y4, 5y, DD, or win-rate numbers exist for either variant.

## Engine (not run — gate rule)

Per the assignment ("run the 4-phase engine only for variants that pass the gate") and
the frozen PLAN, NO engine rows were run: REF was not re-reproduced here (v421 G2
5.41 / 16.91 / 16.82 stands from oc_voltilt/oc_downshare reproductions to the digit),
and no V1/V2 engine DD, win-rate, 5y or full-path numbers exist. Dev4 robust pick:
none-eligible (no engine rows; replica gate failed both).

## Leakage checklist

- Feature timing: triggers use closes with close_time <= tc only; SIG window excludes
  the tested bar (no self-inclusion); cooldown strictly after tc (0 < T-tc <= Nd];
  truncation-tested in tests/test_oc_cascadedelay.py (dropping later bars cannot change
  triggers at kept times); exact (shift, T) match with causal ffill fallback (0 misses
  on the ledger join — all 22,312 fills matched exactly).
- Label windows: none fit anywhere in this study (no harness join, no labels).
- Fit windows: no fits; threshold 4.0, windows 540/120, half 0.5, N = 7/3 all frozen
  ex-ante round numbers, never scanned; no statistic from any test year feeds any choice.
- Fill timing: replica fills inherited (live 16..238 strict trade-through, stop-first);
  perms reassign mults within (year, shift) only (seeds 20261007+y / 20261008+y).
- Coverage: 4h closes cover every anchor year — no skipped year, nothing imputed.
- DISCLOSED (pre-registered in PLAN): the k2placebo ledger carries no exit-date/daily
  path, so the replica DD-half (DD <= base + 0.01 in >= 4/5) cannot be scored at the
  replica stage; the binding DD check would have been the 4-phase engine (not reached).
- Gate costs: inside the replica outcomes (maker 0.0002 / taker 0.00055, v293 settle
  funding); engine costs never invoked (no engine).

## What failed and why

The rule fails arithmetically, not marginally: with union triggers cooling 38-55 % of
time-bars (V1) and 52-72 % of fills, a 0.5x budget cut on a sleeve whose base yearly
sums are ALL positive removes ~2-3 w*y units over 5y (dSum -2.9/-2.0 vs gate +0.273)
and loses every single year 0/5. The Nguyen depth-recovery story (stand down until
makers recommit) assumes the avoided fills are net losers; the replica shows cooled
fills carry the sleeve's profit (timing 0.1 in 2024 = significantly worse than random
halving). A rarer trigger (higher sigma multiple) or per-coin cooldown would be a
DIFFERENT pre-registration, not a fix — disclosed, not run.

## Vietnamese verdict

Cả hai biến thể đều RỚT thảm ở cửa replica+placebo (V1 dSum5y -2,95, V2 -2,02, thua cả 5/5
năm vì budget-halving đánh trúng 52-72% fills đang có lãi; timing 0,1 ở 2024 = tệ hơn
ngẫu nhiên có ý nghĩa) nên KHÔNG chạy engine 4-phase theo đúng quy tắc; không có dev4
robust pick nào đủ điều kiện.
Kết luận: REJECT ý tưởng cascade-delay ở dạng đăng ký trước; không chọn biến thể nào,
không cần bằng chứng prospective.
