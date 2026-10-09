# oc_spillgate REPORT — IDEAS5 §4 cross-asset vol-spillover book gate (2026-10-08; pytest 7/7)

Rule (frozen PLAN.md): market-wide trailing-24h mean pairwise 4h-return correlation
c(T) over the 5 majors (6x4h returns ending <= T, hourly_ext 4h closes only; pair NaN
if <5 overlapping obs or zero variance; c NaN if <8/10 pairs valid). S1: c(T) >
trailing-1y p90 -> whole book row x0.5 that bar. S2: 24h change d(T)=c(T)-c(T-24h) >
trailing-1y p95 -> whole book row x0.5. Thresholds per anchor from [A-372d, A-7d)
(7d embargo, frozen per year; all norm windows >=1000 samples, no skip). Gate applied
after the exact v421 bear filter, before the shifted-clock ffill (causal asof); dip
untouched. C1/C2 = exposure-matched constant controls (DIAGNOSTIC, in-year): per-year
constant book mult m=1-0.5*gate_share (S1: 0.898/0.982/0.951/0.947/0.864;
S2: 0.986/0.962/0.967/0.977/0.989). Claim rule: S beats its control only if dev4 mean
higher AND DDmax no worse. CLOSED row read: `oc_corrbudget` (continuous 30d DIP
scaling, CLOSED) — different leg/timescale/form + control, so kept.

STATUS: DONE. G2 reproduced to the digit (dev + Y4 + 5.41/16.82, asserted in-script).
Stage dev (20 sims) + stage last (12 sims: REF+S2+C2 ONCE) complete.

## Gates (causal; rows < 2021-09-24 never gated)

q90 per anchor (2021..2025): 0.913/0.942/0.901/0.898/0.902 (6-obs 4h windows run hot);
q95 of 24h change: 0.511/0.419/0.488/0.529/0.503. S1 share of book bars per year:
20.5/3.6/9.7/10.5/27.2% (2025 clean year most gated — trailing-1y norms still let the
level drift through, same non-stationarity family as `oc_corrbudget`). S2 share:
2.8/7.5/6.5/4.7/2.1% (near the 5% design rate).

## Dev results (2021–2024; %/mo geometric reset + DD; wins pooled 4-phase)

| row | y0 R/DD | y1 R/DD | y2 R/DD | y3 R/DD | mean | WORST | DDmax | fullDD |
|---|---|---|---|---|---|---|---|---|
| REF | 2.588/10.86 | 3.282/16.91 | 6.045/15.81 | 10.677/8.27 | 5.601 | 2.588 | 16.91 | 16.82 |
| S1 | 2.302/10.75 | 3.043/17.35 | 5.923/16.34 | 10.297/8.10 | 5.345 | 2.302 | 17.35 | 17.30 |
| S2 | 2.471/11.42 | 3.254/16.82 | 6.067/16.07 | 10.479/8.26 | 5.522 | 2.471 | 16.82 | 16.81 |
| C1 | 2.688/10.51 | 3.342/16.89 | 6.677/15.82 | 10.814/8.60 | 5.832 | 2.688 | 16.89 | 16.86 |
| C2 | 2.662/10.78 | 3.243/16.88 | 6.431/15.80 | 10.683/8.41 | 5.707 | 2.662 | 16.88 | 16.84 |

Book win (dev): REF .503/.516/.519/.508; S1 .504/.509/.522/.500; S2 .488/.506/.512/.493;
C1 .506/.509/.525/.518; C2 .508/.511/.515/.515. All-win: REF .613/.658/.697/.671;
S1 .607/.655/.695/.663; S2 .606/.652/.686/.663; C1 .614/.657/.695/.673; C2 .614/.657/.696/.672.
Beats-control: S1 vs C1 NO (5.345 < 5.832); S2 vs C2 NO (5.522 < 5.707, DD tie).
Both gates trail REF on mean AND trail their exposure-matched constants — the gated
spike bars are above-average bars (cutting them hurts; uniform exposure trim helps).

Robust pick on dev4 ONLY among S1/S2 (DD <= 20, no losing, prefer mean >= 5, highest
WORST): S2 (2.471 > 2.302). S1 is worse on every dev metric (mean -0.26, WORST -0.29,
DD +0.53 vs REF).

## Most-recent-year verdict (clean; scored ONCE for the dev4 pick S2 + C2 + REF, labelled)

| row | %/mo | DD | full-path DD | 5y geo | book win | all win |
|---|---|---|---|---|---|---|
| REF | 4.648 | 12.90 | 16.82 | 5.410 | 0.5365 | 0.6267 |
| S2 (pick) | 4.341 (-0.307) | 12.39 | 16.81 | 5.285 | 0.5365 | 0.6254 |
| C2 (control) | 4.528 (-0.120) | 12.88 | 16.84 | 5.470 | 0.5375 | 0.6268 |

S2 trails REF by -0.31 in the clean year and trails its control on 5y (5.285 < 5.470);
DD is flat (16.81 vs 16.82, -0.01). No losing year anywhere; DD <= 20 everywhere;
nothing near the 5.0 gate. S1 unscored in the clean year per protocol (only pick + REF
+ matched control).

## Leakage statement

Feature timing: 4h closes <= T only (C4(T) = hourly bar ending <= T; c/d from returns
ending <= T; gate-bar's own future flow never used; truncation-tested in
tests/test_oc_spillgate.py). Label windows: none (unsupervised quantiles only). Fit
windows: q90/q95 from [A-372d, A-7d) per anchor, frozen per year, 7d embargo;
real-data norm test asserts stored thresholds equal the embargoed-window quantiles; no
statistic from any test year feeds any choice. Fill timing: win_start=5 + 1m
trade-through + stop-first inside the engine. Gate costs inside the engine
(maker 0.0002 / taker 0.00055 / longs 0.0001 per 8h).

## Caveats / post-hoc log

1. One code-only plumbing fix before any outcome: `pre.to_numpy()` -> np.asarray (the
   first dev launch died at shift 0 before any variant; no outcome seen; relaunched).
2. No post-hoc change to definitions, thresholds, variants, or the decision rule.
3. 6-observation correlation windows are noisy by construction (q90 ~0.90); a longer
   window would be a different, unregistered variant.
4. All five years were available when scored; findings need prospective validation.

## Vietnamese verdict

REJECT cả S1 và S2 — dev4 đều thua REF về mean (S1 −0,26, S2 −0,08) và thua cả control
khớp-exposure (S1 thua C1 −0,49, S2 thua C2 −0,19): thanh spillover bị gate là thanh
tốt hơn trung bình, cắt chúng chỉ hại return mà DD gần như đứng yên (−0,01).
Năm sạch S2 −0,31 so với REF (4,34% so với 4,65%), 5y −0,13, nên hướng này đóng lại,
không adopt; giữ S2/C2 làm bằng chứng prospective nếu cần.
