# oc_b7taper — REPORT (2026-10-08; PLAN frozen before any outcome)

IDEAS7 #1: tapered boost decay. Flat x1.5 overpays the late window (bounce is
front-loaded; days 4-7 keep crash-leg exposure for decayed edge). Cascade
trigger frozen VERBATIM (>4sg 4h close-to-close move, market-wide per shift):
V1 step-taper mult 1.6 d0-2 / 1.3 d3-5 / 1.0 d6-7 (floor-day bins); V2
exp-taper 1+0.5*2^(-d/3) with d = days since the latest union trigger
(continuous; re-fires refresh, never stack). Data: existing 4h closes only.

CONTAMINATION LABEL (pre-registered): anything derived from the cascade
results is contaminated for 2021-2026. PRIMARY clean test = pre-sample replica
2017..2020-09-23 (cascade flags on pre-sample 4h closes, D0+B1 ledger, n=9731).
SECONDARY (2021-2026 replica gate, 4-phase engine, post-release year) is
labelled diagnostic / info-only.

STATUS: DONE — triggers reproduce oc_cboostpre exactly; primary replica +
1000 timing/block perms + stop split complete; secondary replica complete;
engine run for REF+B7+V1+V2 (dev) and REF+dev4 pick B7 (last, once). Tests:
10 pass (`tests/test_oc_b7taper.py`).

## Triggers (frozen, causal, verbatim oc_cascadedelay arithmetic)

- Pre-sample per-(sym,shift) fires reproduce oc_cboostpre exactly: BTC
  57/61/61/66, ETH 55/66/65/64, BNB 52/50/49/54, XRP 55/53/57/50 (915 raw;
  union/shift/year 8/12/9/11, 43/42/47/46, 46/53/49/57, 31/39/31/29).
  `boost_mult_presample_taper.parquet`: 27,383 rows (same grid as cboostpre).
- 2021-2026 grid: 53,877 rows (same grid as cascadeboost); per-sym counts
  BTC 104/122/122/117, ETH 99/105/105/107, SOL 82/85/75/79, BNB
  105/103/115/95, XRP 123/130/127/112 (2,112 raw).
- Taper means on pre-sample time-bars: V1 1.16-1.23/yr/shift (boosted share
  31-48%), V2 1.10-1.15 (boosted share = B7 window 34-54%). V1 day-6/7 bars at
  1.0 count as unboosted (frozen boosted = mult > 1+1e-12).

## PRIMARY — pre-sample replica (clean; base 2.313362/2.678870/0.577643/0.297538, B7 norms 2.359275/2.756956/0.688647/0.228078)

| year x variant | norm | gain vs base | gain vs B7 | timing / block pct | boosted fills% |
|---|---|---|---|---|---|
| Y2017 V1 / V2 | 2.368841 / 2.360455 | +0.055 / +0.047 | +0.0096 / +0.0012 | 100/100, 100/100 | 61.8 / 65.2 |
| Y2018 V1 / V2 | 2.731446 / 2.725068 | +0.053 / +0.046 | -0.0255 / -0.0319 | 100/100, 100/100 | 71.9 / 73.6 |
| Y2019 V1 / V2 | 0.895873 / 0.802891 | +0.318 / +0.225 | +0.2072 / +0.1142 | 100/100, 100/100 | 62.5 / 68.1 |
| Y2020p V1 / V2 | 0.166246 / 0.145495 | -0.131 / -0.152 | -0.0618 / -0.0826 | 27/28, 9/13 | 68.5 / 73.3 |

- Helps vs base: both 3/4 (all but Y2020p). Timing significant: both 3/4
  (Y2020p insignificant). The COVID leg fails for both, worse than B7.
- Beater sums: V1 6.162406 vs B7 6.032956 (+0.12945, BEATS); V2 6.033909 vs
  B7 (+0.000953, BEATS by a hair: +0.016% — mechanically eligible per the
  frozen strict-> rule, economically a tie). Both gated to the engine.
- Realised means: V1 1.324/1.364/1.336/1.345; V2 1.214/1.242/1.232/1.240
  (V2 pays less carry per unit window than flat 1.5 by construction).

## Crash risk (reused `stop_kinds.npz`, no new 1m; base 3.30/3.29/6.69/7.58%, pooled 5.58%)

- V1 boosted stops: 1.78 (-1.52) / 3.63 (+0.34) / 5.15 (-1.54) / 9.66 (+2.08);
  pooled 5.65 (+0.07pp) — no pooled excess, but the COVID leg is elevated.
- V2 boosted set = B7 window exactly, so rates equal B7:
  1.69 (-1.61) / 3.55 (+0.26) / 7.47 (+0.78) / 9.13 (+1.55); pooled 6.20
  (+0.62pp). Same crash-leg mechanism as B7.

## SECONDARY — 2021-2026 replica (CONTAMINATED, info only; base sum5y 7.718304, B7 dSum5y +2.946)

- V1 dSum5y +2.806 (gate pass, contaminated) but vs B7 -0.141; dev4 years vs
  B7: -0.088/-0.044/+0.082/-0.015 (loses 3/4). V2 dSum5y +1.894, vs B7 -1.052;
  dev4 vs B7: -0.121/-0.038/+0.027/-0.052 (loses 3/4). Timing (info): V1
  89/58/97/100/100, V2 89/59/96/100/100 — significant only where B7 already is.
- Verdict on this leg: tapering LOSES the 2021-2024 gains vs flat B7 on the
  contaminated years (V1 -0.14, V2 -1.05 replica units).

## Engine (conditional on PRIMARY beater — both eligible; dev4 selection, post-release Y4 diagnostic)

| row | 2021 | 2022 | 2023 | 2024 | mean | WORST | DDmax | losing |
|---|---|---|---|---|---|---|---|---|
| REF | 2.588/10.86 | 3.282/16.91 | 6.045/15.81 | 10.677/8.27 | 5.601 | 2.588 | 16.91 | 0 |
| B7 | 2.955/14.67 | 3.264/17.92 | 8.537/15.94 | 12.486/11.01 | 6.738 | 2.955 | 17.92 | 0 |
| V1 | 2.724/15.18 | 3.228/17.81 | 8.195/15.69 | 12.383/10.04 | 6.560 | 2.724 | 17.81 | 0 |
| V2 | 2.720/14.38 | 3.318/17.96 | 7.429/15.76 | 11.939/9.26 | 6.288 | 2.720 | 17.96 | 0 |

- REF reproduces v421 G2 dev years to the digit; B7 reproduces oc_cascadeboost
  to the digit (mechanism check). Robust pick on dev4 ONLY: B7 (all qualify,
  all >= 5, highest worst-year 2.955 > 2.724 > 2.720). V1 keeps 2024 DD lower
  (10.04 vs 11.01) but gives back mean (-0.18) and worst-year (-0.23).
- 5y + Y4 (scored ONCE, REF + pick B7): REF 5y 5.410 / Y4 4.648/12.90; B7 5y
  6.364 / Y4 diagnostic 4.88/13.81; full-path DD 16.82 / 17.75 (same 2023
  crash-leg episode). Win rates unmoved (sizing only).

## Leakage checklist

- Feature timing: triggers use closes with close_time <= tc only; SIG window
  excludes the tested bar; taper uses only triggers with close < T (latest
  prior via searchsorted left-1); truncation-tested on real pre-sample bars
  (triggers + taper mults identical on kept prefix).
- Label windows: none fit anywhere (no harness join, no labels).
- Fit windows: no fits; threshold 4.0, windows 540/120, window 7d, V1
  levels/bins, V2 half-life 3d, seeds 20261007+y/20261008+y, BLOCK 42 all
  frozen ex-ante/inherited; no statistic from any test year feeds any choice.
- Fill timing: replica live 16..238 strict trade-through + stop-first
  inherited; engine win_start=5 + trade-through + stop-first; perms reassign
  mults within (year, shift) only.
- Coverage: no skipped year; all fills joined exactly (0 misses both legs);
  15 unknown kinds inherited, rates over known kinds only.
- Gate costs inside replica outcomes and engine (maker 0.0002, taker 0.00055,
  longs 0.0001/8h, minute-5 ban, stop-first).
- Spot-vs-perp caveat on every pre-sample number (SPOT fills/exits, perp gate
  costs). Post-hoc: `ANCH5` anchor tuple added to `taper_rule.py` before any
  engine outcome (engine year indexing; taper arithmetic untouched).

## What worked and what did not

- Worked mechanically: taper grids reproduce all frozen trigger counts; V1's
  front-loading adds +0.13 normalised units on clean years (2019 drives it:
  +0.21); timing 100 in 2017-2019 both variants; V1 pooled stops flat.
- Did not: V2's clean edge is +0.001 (a tie, not an edge); both deepen the
  COVID-leg loss vs B7 (-0.06/-0.08 with elevated boosted stops); on
  2021-2026 both lose to flat B7 in replica (V1 -0.14, V2 -1.05) and engine
  (V1 -0.18 mean / -0.23 worst-year, V2 -0.45/-0.24). The decay hypothesis is
  not confirmed where it matters: late-window exposure is what pays 2024
  (+12.5 B7 vs +12.4/+11.9 tapered).

## Vietnamese verdict

V1 hơn B7 phẳng ở pre-sample sạch (+0,13 tổng 4 năm, timing 100 ở 3 năm) nhưng
THUA B7 ở cả replica 2021-2026 (-0,14) lẫn engine dev4 (mean 6,56 < 6,74,
worst-year 2,72 < 2,96); V2 hòa pre-sample (+0,001, coi như không hơn) và thua
mạnh 2021-2026 (-1,05 replica, -0,45pp engine). Cả hai đều lỗ sâu hơn B7 ở chân
COVID Y2020p và không cải thiện drawdown.
Kết luận: REJECT cả hai taper — giữ B7 phẳng, không triển khai taper, không cần
paper prospective cho hướng này.
