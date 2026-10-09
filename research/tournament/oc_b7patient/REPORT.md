# oc_b7patient — REPORT (2026-10-08; PLAN frozen before any outcome)

Patient exit for boosted fills only (IDEAS7 #6, rank 6, prior 9%): boosted fills
(B7 7d window, x1.5 sizing, VERBATIM cascade trigger) keep the 4sg stop and get
room for the snapback — V1 TP 1.0sg->1.5sg, V2 timeout clocks x2 (ONE extension
to T+480, maker-first, taker fallback). Spreads recover intraday, depth takes
weeks; boosted fills exited on the normal clock sell into dumping tape. NOT
oc_partialtp (that banked half EARLY and cut mean bps; this EXTENDS winners).
Existing 1m + state only. Costs maker 0.0002/taker 0.00055, longs 0.0001/8h,
strict trade-through, minute-5 ban (replica live 16..238; engine win_start=5),
stop-first.

CONTAMINATION LABEL (pre-registered): anything derived from the cascade results
is contaminated for 2021-2026. The PRIMARY clean test below is the pre-sample
replica 2017..2020-09-23; the 2021-2026 replica and the post-release year are
LABELLED DIAGNOSTICS (not clean evidence); only prospective paper could confirm.

STATUS: DONE — 1m recompute presample (9716/9731 rebuilt, 15 fallback = same 15
as the cboostpre stop recompute) + PRIMARY replica/joint-placebo/exit-split,
SECONDARY 1m recompute (22312/22312 exact) + replica, ENGINE dev (REF+B7+V1) +
last (REF+B7 once). Dev4 robust pick: B7. Tests: 8 pass.

## PRIMARY — pre-sample replica (clean; D0+B1 ledger n=9731, SPOT fills, perp costs)

Base sums reproduce 2.313362/2.678870/0.577643/0.297538. B7 norms
2.359275/2.756956/0.688647/0.228078 (sum4 6.032956; gains +0.046/+0.078/+0.111/
-0.069 — VERBATIM cboostpre).

| year x variant | n | norm | gain_vs_base | gain_vs_B7 | timing pct | block pct |
|---|---|---|---|---|---|---|
| Y2017 V1 / V2 | 909 | 2.775937 / 2.786447 | +0.462575 / +0.473085 | +0.416662 / +0.427172 | 100.00 / 100.00 | 100.00 / 100.00 |
| Y2018 V1 / V2 | 2986 | 3.441702 / 2.718629 | +0.762832 / +0.039759 | +0.684747 / -0.038326 | 100.00 / 98.60 | 100.00 / 96.10 |
| Y2019 V1 / V2 | 3115 | 0.875796 / 0.724053 | +0.298153 / +0.146410 | +0.187148 / +0.035406 | 97.00 / 88.41 | 94.71 / 85.41 |
| Y2020p V1 / V2 | 2721 | 0.224832 / 0.348967 | -0.072706 / +0.051429 | -0.003247 / +0.120889 | 48.85 / 59.94 | 48.05 / 55.54 |

- Sum4 vs B7: V1 +1.285311 (beats B7: TRUE), V2 +0.545140 (beats B7: TRUE).
  Both are PRIMARY beaters by the frozen definition — hence the engine below.
- V1 helps vs base 3/4 (all but COVID leg, flat -0.003 vs B7 there); timing
  significant 3/4 (2017, 2018, 2019 at 97.0). V2 helps vs base 4/4 but beats B7
  only 3/4 (loses 2018 vs B7 -0.038); timing significant 2/4 (2017, 2018).
- The COVID leg splits them: V1 is flat vs B7 there (-0.003, timing lost);
  V2 HELPS the COVID leg (+0.121 vs B7) — the only variant in this program to
  do so — but pays for it in 2018 (-0.038 vs B7).

## PRIMARY exit split (recomputed kinds, known only; base cross-checked)

- V1 (wider TP): boosted TP rate FALLS (0.644/0.431/0.392/0.427 vs base
  0.803/0.558/0.553/0.595) and boosted timeouts JUMP (0.336/0.527/0.526/0.466
  vs base 0.164/0.409/0.380/0.329) — room costs: spikes that clear 1.0sg but
  not 1.5sg become timeouts. Boosted stops: 0.0202 (-0.0128) / 0.0423 (+0.0094)
  / 0.0827 (+0.0158) / 0.1074 (+0.0316); pooled 0.0716 vs base 0.0558 (+0.0158).
- V2 (extension): boosted timeouts COLLAPSE to residual 0.029/0.168/0.157/0.130
  (vs base 0.164/0.409/0.380/0.329) and boosted TP jumps to
  0.944/0.744/0.744/0.752 — the extension converts timeouts to TP/stop.
  Boosted stops RISE everywhere except 2017: 0.0270 (-0.006) / 0.0878 (+0.0549)
  / 0.0988 (+0.0319) / 0.1184 (+0.0426); pooled 0.0948 vs 0.0558 (+0.0390).
  Holding longer through crash legs hits more stops — the crash-leg mechanism.

## SECONDARY — 2021-2026 replica (CONTAMINATED INFO-ONLY; ledger n=22312)

- B7 dSum5y +2.946 (reproduces cascadeboost +2.946 to rounding).
- V1 dSum5y +4.217 (vs B7 +1.271), sum-half 5/5; dev4 replica sum_V 8.142768 vs
  B7 7.315839 (+0.827 — holds the 2021-2024 gains on the replica). Timing
  68.4/48.7/99.8/100.0/93.8.
- V2 dSum5y +4.870 (vs B7 +1.923), sum-half 5/5; dev4 replica 8.732532 vs B7
  7.315839 (+1.417 — holds gains). Timing 99.3/59.1/96.7/100.0/88.9.
- Replica says both hold the 2021-2024 gains. The engine says otherwise for V1.

## ENGINE dev4 (4-phase reset %/mo + DD; selection basis) — REF+B7+V1

| row | 2021 | 2022 | 2023 | 2024 | mean | WORST | DDmax | fullDD |
|---|---|---|---|---|---|---|---|---|
| REF | 2.588/10.86 | 3.282/16.91 | 6.045/15.81 | 10.677/8.27 | 5.601 | 2.588 | 16.91 | 16.82 |
| B7 | 2.955/14.67 | 3.264/17.92 | 8.537/15.94 | 12.486/11.01 | 6.738 | 2.955 | 17.92 | 17.75 |
| V1 | 2.900/15.87 | 1.284/19.88 | 9.175/18.37 | 12.846/11.10 | 6.449 | 1.284 | 19.88 | 23.14 |

- REF reproduces v421 G2 dev years 0..3 R/DD to the digit (gate passed). B7
  reproduces cascadeboost B7 dev4 exactly (6.738/2.955/17.92 — verbatim path).
- V1 LOSES to B7 on dev4 (mean 6.449 < 6.738, WORST 1.284 << 2.955) and
  BREACHES the gate (full-path DD 23.14 > 20; yearly DDmax 19.88). Win rates
  fall (all-trade 0.591/0.623/0.676/0.644 vs B7 0.610/0.651/0.695/0.664).
  The wider TP misses the 2022 rebounds, converts TPs to timeouts/stops, and
  deepens the 2023 leg (DD 18.37 vs B7 15.94). Replica gains do NOT transfer.
- Robust pick on dev4 ONLY among DD <= 20 / no-losing rows: REF + B7 qualify
  (V1 excluded on DD); both have mean >= 5, highest WORST wins: B7. PICK: B7.
- V2 engine: NOT RUN (disclosed limitation, post-hoc log in PLAN.md): the
  pipeline timeout is hardcoded in backend/history_tm.simulate (next-bar open);
  extending boosted timeouts to T+480 with mid+end funding and gross-cap
  interaction requires forking simulate, beyond the kw-only (sleeve_tp)
  override that V1 uses. V2 is replica-only evidence.

## ENGINE 5y + post-release year (scored ONCE, REF + pick B7; Y4 DIAGNOSTIC)

- REF: 5y 5.410, W 2.588, full DD 16.82; Y4 4.648/12.90 (reproduces v421 G2).
- B7: 5y 6.364, W 2.955, full DD 17.75; Y4 diagnostic 4.88/13.81 (contaminated).
- V1 last-year not run (not the pick; dev4 already fails the DD gate).

## Leakage checklist

- Feature timing: triggers use closes with close_time <= tc only; SIG excludes
  the tested bar; boost window strictly after tc; exits use only 1m up to the
  exit minute (V2 second clock 240..479 + o3 uses only second-bar minutes);
  truncation-tested in tests/test_oc_b7patient.py (8 pass).
- Label windows: none fit anywhere. Fit windows: no fits; threshold 4.0,
  windows 540/120, boost 1.5, N=7d, V1 TP 1.5sg, V2 one x2-clock extension,
  seeds 20261007+y/20261008+y, BLOCK 42 all frozen, never scanned.
- Fill timing: replica live 16..238 strict trade-through + stop-first inherited
  (recompute VERBATIM); engine win_start=5 + trade-through + stop-first; perms
  reassign the JOINT (mult, flag) within (year, shift) only.
- Coverage: presample 15 unknown-rebuild fallbacks to ledger y10 (0.15%,
  same 15 as cboostpre); secondary zero fallbacks (exact O/sg); V2 zero
  unknown-extensions on presample (extension data present), secondary zero.
- Gate costs inside recomputed outcomes and engine. Spot-vs-perp caveat on
  every pre-sample number.

## What worked and what did not

- Worked (replica): both patient exits beat plain B7 on the CLEAN pre-sample
  years (V1 +1.285, V2 +0.545 sum4) with significant timing outside the COVID
  leg, and both hold the 2021-2024 replica gains (V1 +0.827, V2 +1.417 dev4).
  V2 is the only variant here to help the COVID leg (+0.121 vs B7).
- Did not (engine): V1's replica gains reverse in the full engine — worst-year
  1.284 vs B7 3.264, full DD 23.14 breach, win rates down. The replica has no
  budget/cap/bear-book interaction; the engine does. V2 has no engine
  validation and carries +3.9pp pooled stop cost.
- Verdict: REJECT both. Neither beats plain B7 where it matters (engine-validated
  dev4 with DD <= 20). V1 is engine-refuted; V2 is replica-only with tail cost.

## Vietnamese verdict

V1 thắng B7 trên pre-sample sạch (+1,29) và replica dev4 (+0,83) nhưng THUA trong
engine (worst-year 1,28 so với 3,26, DD full-path 23,14 vượt 20, win rate giảm) —
bị loại bởi gate DD và robust pick vẫn là B7.
V2 thắng B7 pre-sample (+0,55, giúp cả chân COVID +0,12) và replica dev4 (+1,42)
nhưng stop gộp +3,9pp và KHÔNG có engine (timeout pipeline cứng, ngoài phạm vi
kw-only) nên không đủ bằng chứng adopt.
Kết luận: REJECT cả hai — giữ B7 nguyên, không triển khai exit kiên nhẫn.
