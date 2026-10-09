# oc_volvolbrake REPORT — IDEAS8 §8 vol-of-vol fragility brake (2026-10-08; pytest 8/8)

Rule (frozen PLAN.md): BTC 4h closes from `hourly_ext` only, C4(T) = hourly bar
ending <= T; r(T) = log(C4(T)/C4(T-4h)); RV6(T) = std of 6 returns ending <= T;
D(d) = RV6(d 00:00); f(T) = std of 30 D on days strictly before date(T)
(daily-constant, causal). Per-anchor q90/q85 over f in [A-372d, A-7d) (7d embargo,
>=1000 samples, frozen per year). V1: f(T) > q90 -> whole book row x0.5 that bar;
V2: f(T) > q85 -> x0.5. Applied after the exact v421 bear filter, before the
shifted-clock ffill (causal asof); dip untouched (tilt 1). C1/C2 = exposure-matched
constant controls (DIAGNOSTIC, in-year): per-year constant m = 1-0.5*share
(V1 shares: 0.000/0.063/0.162/0.060/0.000; V2: 0.000/0.068/0.162/0.077/0.000;
m_C1: 1.0/0.968/0.919/0.970/1.0; m_C2: 1.0/0.966/0.919/0.962/1.0).
Claim rule: V beats its control only if dev4 mean higher AND DDmax no worse.
CLOSED rows read: `oc_bookvol` (vol-LEVEL scaling, NOT PROMISING), `oc_spillgate`
(CORR-level/change gate, both trail REF and trail controls), `oc_fundclock`
(funding-CLOCK gate, FAILS gate (b)) — this gates on vol-OF-vol (BTC second moment),
a distinct axis, with the same control lesson.

STATUS: DONE. G2 reproduced to the digit (dev + Y4 + 5.41/16.82, asserted in-script).
Stage dev (20 sims) + stage last (12 sims: REF+V2+C2 ONCE) complete.

## Gates (causal; rows < 2021-09-24 never gated)

q90 per anchor (2021..2025): 0.01192/0.00823/0.00750/0.00783/0.00698;
q85: 0.01135/0.00801/0.00737/0.00756/0.00675 (all norm windows n=2190, no skip).
V1 share of standard-grid book bars per year: 0.0/6.3/16.2/6.0/0.0%;
V2: 0.0/6.8/16.2/7.7/0.0% (overall 4.64%/5.00%; 2021 and 2025 gates fully off —
trailing-1y norms let the level drift through, same non-stationarity family as
`oc_spillgate`/`oc_fundclock`). Engine gated book-row counts (dev, all phases):
624/672 of 10950 standard rows; decision-bar gated shares (4-phase mean):
2021 0.0%, 2022 ~3.6%, 2023 ~12.2-12.4%, 2024 ~2.9-3.4%.

## Dev results (2021–2024; %/mo geometric reset + DD; wins pooled 4-phase)

| row | y0 R/DD | y1 R/DD | y2 R/DD | y3 R/DD | mean | WORST | DDmax | fullDD |
|---|---|---|---|---|---|---|---|---|
| REF | 2.588/10.86 | 3.282/16.91 | 6.045/15.81 | 10.677/8.27 | 5.601 | 2.588 | 16.91 | 16.82 |
| V1 | 2.588/10.86 | 2.980/17.01 | 5.834/15.79 | 10.526/8.27 | 5.435 | 2.588 | 17.01 | 16.99 |
| V2 | 2.588/10.86 | 3.048/16.87 | 5.831/15.84 | 10.606/8.27 | 5.471 | 2.588 | 16.87 | 16.82 |
| C1 | 2.588/10.86 | 3.313/16.87 | 6.953/15.81 | 10.662/8.45 | 5.830 | 2.588 | 16.87 | 16.83 |
| C2 | 2.588/10.86 | 3.273/16.86 | 6.952/15.81 | 10.666/8.50 | 5.821 | 2.588 | 16.86 | 16.83 |

Book win (dev): REF .503/.516/.519/.508; V1 .503/.508/.526/.504; V2 .503/.502/.526/.503;
C1 .503/.512/.525/.514; C2 .503/.509/.525/.513. All-win: REF .613/.658/.697/.671;
V1 .613/.657/.696/.671; V2 .613/.655/.696/.671; C1 .613/.658/.696/.672; C2 .613/.657/.696/.672.
Beats-control: V1 vs C1 NO (5.435 < 5.830); V2 vs C2 NO (5.471 < 5.821, DD worse 16.87 > 16.86).
Both brakes trail REF on mean (-0.17/-0.13) AND trail their exposure-matched constants
(-0.40/-0.35) — the gated fragile bars are above-average bars (cutting them hurts;
uniform exposure trim helps). V1 also worsens DDmax (+0.10 vs REF).

Robust pick on dev4 ONLY among V1/V2 (DD <= 20, no losing, prefer mean >= 5, highest
WORST): V2 (both mean >= 5; WORST tie 2.588, mean 5.471 > 5.435).
V1 is worse on mean (-0.04), WORST tie, DD (+0.14 vs V2).

## Most-recent-year verdict (clean; scored ONCE for the dev4 pick V2 + C2 + REF, labelled)

| row | %/mo | DD | full-path DD | 5y geo | book win | all win |
|---|---|---|---|---|---|---|
| REF | 4.648 | 12.90 | 16.82 | 5.410 | 0.5365 | 0.6267 |
| V2 (pick) | 4.648 (+0.000) | 12.90 | 16.82 | 5.306 | 0.5365 | 0.6267 |
| C2 (control) | 4.670 (+0.022) | 12.46 | 16.83 | 5.590 | 0.5366 | 0.6267 |

V2 gate is fully OFF in the clean year (share 0.0%), so Y4 is bit-identical to REF
(+0.000, same DD/wins); 5y trails REF by -0.104 (5.306 < 5.410) and trails its control
on 5y (5.306 < 5.590); DD is flat (16.82 vs 16.82, +0.00). No losing year anywhere;
DD <= 20 everywhere; nothing near the 5.0 gate on the dev leg (V2 dev4 5.471 < REF
5.601). V1 unscored in the clean year per protocol (only pick + REF + matched control).

## Fee split / costs

Gate costs inside the engine (maker 0.0002, taker 0.00055, longs pay 0.0001/8h,
shorts 0; limit fill only on 1m trade-through; nothing in first 5 min after a 4h
close; stop-first in shared 1m bar). No separate fee/funding split was collected
(disclosed; same as oc_spillgate) — the reset %/mo numbers above are NET of all
fees and gate funding, so the RELATIVE ranking (variant vs REF vs control) is the
object of study, not the absolute level.

## Leakage statement

Feature timing: BTC 4h closes <= T only (C4(T) = hourly bar ending <= T; r/RV6 from
returns ending <= T; f(T) from daily D on days strictly before T's day; gate-bar's
own future flow never used; truncation-tested in tests/test_oc_volvolbrake.py).
Label windows: none (unsupervised quantiles only). Fit windows: q90/q85 from
[A-372d,A-7d) per anchor, frozen per year, 7d embargo; real-data norm test asserts
stored thresholds equal the embargoed-window quantiles; no statistic from any test
year feeds any choice. Fill timing: win_start=5 + 1m trade-through + stop-first
inside the engine. Gate costs inside the engine (maker 0.0002 / taker 0.00055 /
longs 0.0001 per 8h).

## Caveats / post-hoc log

1. One pre-outcome unit-test fix only: flat-panel `f` is 0.0 (not NaN) since RV6 of
   zeros is 0; the no-future-hour test now asserts finite pre-spike f == 0.0.
   No threshold/variant/decision change.
2. No post-hoc change to definitions, thresholds, variants, or the decision rule.
3. 2021/2025 gate-off years make C1/C2 == REF there (m=1.0); the control comparison
   is driven by 2022-2024, disclosed.
4. All five years were available when scored; findings need prospective validation.

## Vietnamese verdict

REJECT cả V1 và V2 — dev4 đều thua REF về mean (V1 −0,17, V2 −0,13) và thua cả control
khớp-exposure (V1 thua C1 −0,40, V2 thua C2 −0,35): thanh fragile bị gate là thanh
tốt hơn trung bình, cắt chúng chỉ hại return mà DD đứng yên (V2 16,87 so với 16,91).
Năm sạch V2 trùng REF (gate tắt, 4,65%) nên hướng này đóng lại, không adopt.
