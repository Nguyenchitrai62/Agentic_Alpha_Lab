# oc_idea1_kellyrung REPORT — Distributional Kelly rung sizing under budget (BOT return/DD)

## 0. PRE-REGISTRATION (frozen BEFORE any scoring; only these 2 variants; selection on dev4 2021-2024 only)

- Idea (IDEAS_20261007.md §1): mean-var per-rung sizing from the pooled fill distribution with a hard budget cap.
  Not repeat of v392 naive flat x0.9/x0.8 (rejected) nor oc_kellydip diagnostic; this is Kelly-screen-V2-style
  mean/var sizing (+4.720 PROMISING, never engine-tested), now budget-normalised with the B1 1/(1+n) prior and a
  hard gross cap, engine-tested. Rest identical G2 (R2B1D17BFG2: R2 rungs, B1 inv-rule, kd=1.7, bear-book filter,
  risk budget 0.26*1.7, gross cap G=2.0, D17 stops/backstop, deployed TP).
- Data: no new data; existing engine fill ledgers only (research/tournament/ext/fills_U_ext.parquet + v421 runs).
- Variants (exactly 2, no others):
  * K1: dip rung size = budget-normalised 1/(1+n_fill) prior x Kelly-fraction 0.25 x per-rung mean-var tilt.
  * K2: same with Kelly-fraction 0.50.
  * Per-rung tilt: per anchor year Y and rung depth k, pooled train (t_exit < anchor-7d) mu/var of y_dep give
    raw=max(mu,0)/var, budget-normalised to mean 1 on train (clip 0..2); B1 prior normalised to mean 1 on train;
    final absolute scale = kd*mean_dep_train * f_frac (so K1 ~0.25x, K2 ~0.5x deployed exposure before tilt).
  * Hard budget cap: G2 gross cap G=2.0 kept; risk budget unchanged; rest identical G2.
- Costs (gate): maker 0.02%, taker 0.055%, longs pay 0.01%/8h (engine defaults; no extra slippage).
- Selection (AGENTS.md): compare/choose ONLY on dev4 2021-2024, robust criterion (DD<=20, no losing dev year;
  prefer dev4 mean>=5, then highest dev4 WORST; ties→higher mean). Most-recent year 2025-09-24..2026-09-23 scored
  ONCE for the chosen variant only, labelled POST-HOC (years already seen by Kelly screen/ext). Baseline must
  reproduce G2 (5.41/W2.588/DD16.91/full16.82) or G2+carry (5.634/DD16.75/full16.66, oc_carrycompound) exactly first.
- Metric: 4-phase reset (reset_metric.year_reset) + full-path DD like v421/v422. Dip replica + placebo gate
  (+0.273 pooled p95, oc_placebo_dip) reported as screen; final judgement is the 4-phase engine, never a vectorised
  screen alone for the verdict.
- Leak guard: fill distribution fit pre-anchor only + 7d embargo; per-k moments from train only; n_fill is
  fill-time (bot-executable, same as B1); no statistic from any test year feeds any choice.

## 1. Baseline reproduction (asserted in-script, tmp/baseline.json)

- G2 (=v421 R2B1D17BFG2, f=0): 2.588/10.86, 3.282/16.91, 6.045/15.81, 10.677/8.27, 4.648/12.90;
  5y 5.41 / W 2.588 / DD 16.91 / full-path 16.82 (marked 16.82/close 16.05) — matches v421_result.json exactly.
- G2+carry compounding (oc_carrycompound f=0.25): 5.634 / W 2.778 / DD 16.75 / full 16.66 (carry add +0.224pp).
- Status: reproduced TO THE DIGIT; proceed (else stop-and-report rule not triggered).
- Gate costs: maker 0.02%, taker 0.055%, longs pay 0.01%/8h (engine defaults; carry leg fees as in oc_carrycompound).

## 2. Pooled fit + dip replica screen, DEV4 only (harness 4-fold; 2025 never touched here)

- Pooled train (t_exit < anchor-7d, y_dep): mu/var 0.00321/0.00255 (2021), 0.00276/0.00170 (2022),
  0.00165/0.00137 (2023), 0.00160/0.00117 (2024); exact full-Kelly f* 1.03/1.28/1.03/1.15.
  Per-k raw=max(mu,0)/var budget-normalised to mean 1 (clip 0..2); 2021 train has no majors-R2 rows so
  fallback flat Base=1 (documented in fit_tables.json). Kelly fractions 0.25/0.50 are deep fractional
  vs full Kelly ~1.0-1.3. n = distinct other majors, same T, |dt|<=15min (bot-executable B1 proxy).
- Replica (single-grid harness units; equal-exposure rescale like harness.score + raw absolute):

| year | dep S | B1 eqexp gain | K1/K2 eqexp gain | K1 raw gain | K2 raw gain |
|---|---|---|---|---|---|
| 2021 | 4.485 | +0.612 | +0.612 | -2.791 | -1.097 |
| 2022 | 0.924 | +0.792 | +1.096 | +0.212 | +1.347 |
| 2023 | 6.627 | +0.770 | +0.555 | -3.873 | -1.118 |
| 2024 | 4.265 | -0.469 | +0.099 | -2.183 | -0.100 |
| total | — | +1.706 | +2.362 | -8.635 | -0.968 |

- Eqexp graduates (harness >=3/4 + total>0 + worst-day): B1 true (3/4), K1/K2 true (4/4 gains>0; worst
  overall -1.07 vs dep -1.91). Per-k tilt beats flat B1 at equal exposure (+2.36 vs +1.71). K1=K2 at eqexp
  (global f rescales out) — f differentiates only absolute exposure (raw) and engine DD.
- Placebo side row (unit caveat: +0.273 is 4-phase-mean w*y; replica is single-grid harness units):
  raw dSum K1 -8.635 (fail), K2 -0.968 (fail) — expected: 0.25x/0.5x exposure cuts absolute sums while
  worst days improve every year (e.g. 2022 -0.60/-1.20 vs -1.91). Screen verdict: selection edge real at
  equal exposure; absolute cut must be judged in the engine (next).

## 3. 4-phase engine DEV4 (v421-identical; only sleeve_fill_size=B1*Base*f*C0; tmp/engine_dev.pkl)

| year | K1 R/DD | K2 R/DD | G2 ref R/DD |
|---|---|---|---|
| 2021-09-24 | 0.984 / 13.78 | 2.028 / 14.78 | 2.588 / 10.86 |
| 2022-09-24 | 3.135 / 15.58 | 2.103 / 19.12 | 3.282 / 16.91 |
| 2023-09-24 | 3.938 / 13.89 | 7.192 / 15.20 | 6.045 / 15.81 |
| 2024-09-24 | 7.642 / 7.07 | 11.073 / 9.27 | 10.677 / 8.27 |
| dev4 geo / W / maxDD / losing | 3.89 / 0.984 / 15.58 / 0 | 5.54 / 2.028 / 19.12 / 0 | 5.60 / 2.588 / 16.91 / 0 |

- Robust choice (dev4 only): both DD<=20 and no losing year; mean>=5 filter leaves K2 (5.54) over K1 (3.89);
  highest dev4 WORST also K2 (2.028 > 0.984). WINNER = K2. (K2 trails G2 dev4 on all three: -0.06pp mean,
  -0.56pp worst, +2.2pp DD.)
- Engine trade counts (4-phase pooled; book n/win + rung n/win from events):
  K2 dev: book 3903 n / ~0.49 win (505+464+497+448 wins), rungs 16260 n / ~0.70 win; K1 similar counts,
  smaller sizes. Full per-shift counts in results.json/tmp.

## 4. Most-recent year, WINNER ONLY, POST-HOC (2025-09-24..2026-09-23; Kelly screen saw 2025 -> labelled)

- Engine (full-period runs, tmp/engine_last.pkl, K2 only): 2025 R 4.641 / DD 14.69 (G2 ref 4.648/12.90).
- Replica 2025 (harness5, K2 only): eqexp gain +0.706 (IC +0.08), raw gain +0.042, worst -0.55 vs -0.50;
  raw vs placebo +0.273: FAIL (0.042 < 0.273; unit caveat as above).
- K2 five-year roll-up: 2.028/2.103/7.192/11.073/4.641 → geo 5.353 / W 2.028 / maxDD 19.12 / losing 0;
  full-path DD (continuous 4-phase mix, v421 formula) marked 21.79 / close 19.64 / full 21.79.
- References: G2 5.41/W2.588/DD16.91/full16.82; G2+carry 5.634/W2.778/DD16.75/full16.66.
  K2 deltas: -0.06pp vs G2 (-0.28pp vs G2+carry); DD +2.2pp yearly, +5.0pp full-path.
- Gate: (a) 5y>=5 TRUE (5.353); (b) last>=5 FALSE (4.641); (c) no losing TRUE; (d) fullDD<=20 FALSE (21.79).

## 5. Verdict + repro

- REJECT distributional-Kelly rung sizing in this form (K1 f=0.25 / K2 f=0.50, B1-prior, G2-identical engine):
  the equal-exposure tilt is real (+2.36 harness, 4/4 years) but fractional exposure buys no return
  (+0.1-0.3pp expected; got -0.06pp vs G2, -0.28pp vs G2+carry) and no DD cut (yearly +2.2pp, full-path
  21.79 > 20 gate; last year 4.64 < 5). Failure mode as pre-registered: tail mis-estimation/over-conservatism
  (2021 fallback-flat; 2022 Kelly overweights the crash year). Close the direction per the 2-variant limit;
  no prospective paper can fix a gate DD/return gap of this size — grow paper evidence on G2+carry instead.
- Repro: research/tournament/oc_idea1_kellyrung/{REPORT.md (prereg §0 frozen first), run_kellyrung.py,
  engine_kelly.py, results.json, tmp/{baseline,fit_tables,replica_dev4,replica_last,engine_dev,engine_last,
  engine_dev_choice}.json|pkl} + tests/test_oc_idea1_kellyrung.py. Scratch only under tmp/; git read-only
  (no stash/commit); heavy engine via scripts/heavy_slot.py (slot waits are normal).

## Verdict tieng Viet (3 dong)
- K2 thang: dev4 5,54%/thang, 5 nam 5,35%/thang nhung DD full-path 21,79 (>20) va nam gan nhat 4,64 (<5).
- Kelly phan doan + triet khau B1 that bai: kem G2/G2+carry ca return (-0,06/-0,28 diem) va DD (+2-5 diem).
- Khong ap dung (reject); dong huong Kelly-rung dang nay, khong can them bang chung prospective.
