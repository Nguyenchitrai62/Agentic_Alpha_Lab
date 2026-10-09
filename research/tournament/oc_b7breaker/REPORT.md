# oc_b7breaker — REPORT (2026-10-08; PLAN frozen before any outcome)

IDEAS7 #4: cascade-count circuit breaker (COVID guard, known at the time). Base = B7 of
oc_cascadeboost (dip budget x1.5 for 7 days after a > 4 sigma 4h close-to-close move,
oc_cascadedelay definition, closes-only, union over majors per shift). Breaker rule
(frozen reading): at decision T on shift s, if >= K union cascades have tc in [T-Md, T]
(count <= close only, inclusive, contemporaneous gate — not latching), suspend ALL boost
(base sizes, mult 1.0); else B7 mult. V1 K=2/M=14; V2 K=3/M=21 (frozen integers).
Book untouched. Existing 4h closes only (no new data).

CONTAMINATION LABEL (pre-registered): anything derived from the cascade results is
contaminated for 2021-2026. The PRIMARY, clean test is the pre-sample replica
2017 .. 2020-09-23 (oc_presampletilt + oc_cboostpre machinery: cascade flags on pre-sample
4h closes, D0+B1 ledger, n = 9731). SECONDARY (contaminated): 2021-2026 replica gate;
4-phase engine ONLY for variants beating B7 on the pre-sample test.

STATUS: DONE — pre-sample grids built (915 raw fires; union/shift/year matches oc_cboostpre
exactly; B7 mults identical; B7 gains reproduce +0.046/+0.078/+0.111/-0.069), replica +
1000 timing/block perms per variant/year complete, stop-kind recompute complete
(kinds TP 5729 / time 3445 / stop 480 / backstop 62 / unknown 15 — identical totals to
oc_cboostpre, verbatim recompute confirmed), secondary 2021-2026 grids + replica complete
(B7 dSum5y +2.946 reproduced, in-anchor unions 264/266/263/255 exact). NO ENGINE:
neither variant beats B7 on the clean test (frozen rule), so per PLAN no engine is the
valid negative result. Tests: 13 pass (`tests/test_oc_b7breaker.py`).

## PRIMARY — pre-sample replica (clean; 4-phase-mean w*y units, SPOT fills, perp gate costs)

| year x variant | n | base | variant | norm | gain vs base | delta vs B7 | timing pct | block pct | boosted fills% |
|---|---|---|---|---|---|---|---|---|---|
| Y2017 B7 / V1 / V2 | 909 | 2.313362 | 3.128830 / 2.476629 / 2.514132 | 2.359275 / 2.342618 / 2.340344 | +0.046 / +0.029 / +0.027 | — / -0.017 / -0.019 | 100 / 56.9 / 76.5 | 100 / 57.9 / 68.5 | 65.2 / 11.4 / 14.9 |
| Y2018 B7 / V1 / V2 | 2986 | 2.678870 | 3.772117 / 2.793683 / 2.765877 | 2.756956 / 2.561626 / 2.449261 | +0.078 / -0.117 / -0.230 | — / -0.195 / -0.308 | 100 / 14.2 / 2.7 | 100 / 23.9 / 7.9 | 73.6 / 18.1 / 25.9 |
| Y2019 B7 / V1 / V2 | 3115 | 0.577643 | 0.923097 / 0.381041 / 0.539793 | 0.688647 / 0.354682 / 0.486392 | +0.111 / -0.223 / -0.091 | — / -0.334 / -0.202 | 92.3 / 1.5 / 19.7 | 89.5 / 1.2 / 19.5 | 68.1 / 14.9 / 22.0 |
| Y2020p B7 / V1 / V2 | 2721 | 0.297538 | 0.311690 / 0.438531 / 0.335988 | 0.228078 / 0.414177 / 0.310327 | -0.069 / +0.117 / +0.013 | — / +0.186 / +0.082 | 45.4 / 87.7 / 56.2 | 45.1 / 91.3 / 52.4 | 73.3 / 11.8 / 16.5 |

- Beats-B7 rule (frozen, binding): sum_4y delta > 0 AND Y2020p delta > 0.
  V1: sum -0.360, Y2020p +0.186 -> FAIL. V2: sum -0.447, Y2020p +0.082 -> FAIL.
- The breaker does what it says on the COVID leg: V1 turns Y2020p from -0.069 to +0.117
  (timing 87.7/91.3); V2 to +0.013 (timing insignificant). But it pays with the good years:
  V1 loses -0.20 (2018) and -0.33 (2019) vs B7 with timing at the BOTTOM (1.5/1.2 in 2019 —
  significantly WORSE than random reassignment); V2 loses -0.31 (2018) and -0.20 (2019).
  The breaker suspends ~80% of B7 boosted fills (V1 14.7% / V2 21.0% boosted vs B7 71.0%)
  because K=2/14d fires most of the time — it keeps only isolated-cascade boosts, and in
  2018-2019 the isolated-cascade dips are the ones that do not pay.
- Helps vs no boost: B7 3/4, V1 2/4 (2017 + COVID leg), V2 2/4 (same). Timing significant
  (>= 95): B7 2/4, V1 0/4, V2 0/4.

## Crash risk (stop-hit share of boosted fills vs base rate; kinds recomputed verbatim mu=1.0)

| year | base stop% | B7 boosted (delta) | V1 boosted (delta) | V2 boosted (delta) |
|---|---|---|---|---|
| Y2017 | 3.30 | 1.69 (-1.61) | 0.00 (-3.30) | 0.00 (-3.30) |
| Y2018 | 3.29 | 3.55 (+0.26) | 2.40 (-0.89) | 4.40 (+1.11) |
| Y2019 | 6.69 | 7.47 (+0.78) | 16.05 (+9.36) | 12.17 (+5.48) |
| Y2020p | 7.58 | 9.13 (+1.55) | 3.45 (-4.13) | 6.68 (-0.90) |
| pooled | 5.58 | 6.20 (+0.62) | 6.88 (+1.30) | 7.21 (+1.63) |

- IDEAS7 safety condition (frozen): pooled boosted-stop delta must not exceed +1pp.
  V1 +1.30pp FAIL, V2 +1.63pp FAIL (B7 +0.62pp passes). The breaker cuts stops on the
  COVID leg (V1 -4.1pp) but keeps a far more stop-prone subset in 2019 (+9.4/+5.5pp on
  ~15-22% of fills): isolated-cascade boosts stop out hardest exactly where the replica
  gains collapse. Both variants fail the safety flag independently of the gains rule.

## SECONDARY — 2021-2026 replica (CONTAMINATED; labelled diagnostic, no clean evidence)

| variant | dSum5y vs base | sum-half | gate (4/5 + 0.273) | dev4 (2021-24) vs B7 | timing pct y0..y4 |
|---|---|---|---|---|---|
| B7 (reproduced) | +2.946 | 5/5 | PASS | — | 96.6 / 67.7 / 85.4 / 100 / 98.1 |
| V1 | +0.596 | 4/5 | PASS (contam.) | -2.16 replica units | 98.4 / 13.0 / 20.2 / 73.1 / 98.7 |
| V2 | +0.461 | 3/5 | FAIL | -2.25 replica units | 99.1 / 7.2 / 1.0 / 89.8 / 89.8 |

- V1 passes the contaminated gate vs base mechanically but keeps only ~20% of B7's gain
  (+0.60 vs +2.95) and loses every dev year vs B7 in normalised terms
  (norm deltas: +0.015 / -0.105 / -0.077 / -0.114). V2 fails the gate outright (3/5).
  "Without losing the 2021-2024 gains": both LOSE them — no variant to take to the engine.
- No 4-phase engine ran (frozen consequence of the primary outcome). Post-release-year
  engine numbers do not exist for these variants; nothing to label.

## Leakage checklist

- Feature timing: triggers use closes with close_time <= tc only; SIG window excludes the
  tested bar; B7 window strictly after tc; breaker count tc <= T only (count<=close);
  truncation-tested on real pre-sample bars (triggers AND breaker counts identical on kept
  prefix; 13 tests pass).
- Label windows: none fit anywhere (no harness join, no labels).
- Fit windows: no fits; threshold 4.0, windows 540/120, boost 1.5, N=7, K/M=(2,14)/(3,21),
  seeds 20261007+y/20261008+y, BLOCK 42 all frozen ex-ante/inherited, never scanned; no
  statistic from any test year feeds any choice. Pre-sample years never used for any fit.
- Fill timing: replica fills inherited (live 16..238 strict trade-through, stop-first);
  kind recompute same window + stop-first ordering; perms reassign mults within (year,shift)
  only. Gate costs inside reused replica outcomes.
- Coverage: no skipped year; all 9,731 pre-sample + 22,312 2021-2026 fills joined exactly
  (0 misses); 15 unknown kinds (0.15%) excluded from rates only.
- Spot-vs-perp caveat on every pre-sample number (SPOT fills/exits, perp gate costs).
- Post-hoc log: one entry (build_breaker_4shift union assertion counts anchor-only years per
  the REPORT convention; no result row changed).

## What worked and what did not

- Worked as a guard, failed as a rule: the breaker attenuates the COVID leg (V1 Y2020p gain
  +0.117 vs B7 -0.069, stops -4.1pp) — clustering does mark the crash leg. But K=2/14d is
  far too trigger-happy (breaker active ~85% of B7 window time-bars): it suspends the
  ordinary post-cascade bounce that pays in 2017-2019, keeps a stop-prone isolated subset
  (2019 boosted stops 16%/12%), and ends -0.36/-0.45 normalised units below plain B7 over
  the clean years. No K/M tuning is allowed (frozen integers); the direction is closed with
  this result.
- Not shown: there is no engine table because the frozen beats-B7 rule stopped it — that
  IS the result (negative, valid). The contaminated secondary confirms the same ranking.

## Vietnamese verdict

Cả hai breaker đều cứu được chân COVID (V1 Y2020p +0,19, stop -4,1pp so với B7) nhưng phá
nát các năm tốt 2018-2019 (-0,20/-0,33 mỗi năm so với B7, timing chạm đáy 1-2%) và rớt cờ
an toàn stop gộp (+1,3/+1,6pp vượt ngưỡng +1pp), tổng 4 năm sạch thua B7 -0,36/-0,45.
Máy phụ nhiễm 2021-2026 cũng thua B7 (-2,2 đơn vị dev4) nên không có engine.
Kết luận: REJECT cả V1 lẫn V2 — giữ nguyên B7 trần, đóng hướng breaker count, không triển khai thật.
