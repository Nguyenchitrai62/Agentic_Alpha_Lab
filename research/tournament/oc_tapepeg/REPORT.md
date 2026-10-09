# oc_tapepeg REPORT (2026-10-08; PLAN frozen before any outcome)

IDEAS6 #4 (rank 4): tape-anchored rung placement — rung = min(frozen sigma price,
trailing-60m 1m LOW - 1tick) at the signal close; rest identical (maker fills, B1 sizes,
TP 1.0sg / 4sg close5 stop / 8sg backstop, stop-first). V1 = 60m low - 1tick; V2 = the
same low rounded DOWN to the 5-tick grid. HOW the rung is placed, not WHEN or how far
apart (CLOSED `oc_rungspace` spacing-MULT, `oc_b1deeper` per-minute corr amendment and
`oc_bookoffset` vol offset kept as distinct).

STATUS: DONE. 4-phase D0+B1 replica exact (base n = 22312, base sum5y = 7.718304,
phase-0 sums and 4-phase means match `oc_dipexit`/`oc_placebo_dip` to 1e-3) — BOTH
variants FAIL the replica + placebo gate -> NO 4-phase engine run (negative result,
valid — the oc_crashgate/oc_rungquality/oc_makerexit path). No post-hoc change (the
full ledger was computed ONCE; PLAN post-hoc log stays empty).

## Replica fidelity (base, not a gate — disclosed)

Phase-0 raw sums 2.388/0.183/3.810/2.579/0.712 = `oc_dipexit` ref to 1e-3; 4-phase-mean
sums 0.911/0.833/2.100/3.197/0.677 and DDs 0.856/0.951/0.800/0.355/0.607 =
`oc_placebo_dip` to 1e-3; base sum5y 7.718304 exact; base n = 22312 exact, win 0.7016,
mean 17.87 bps. Ledger checksum be5f146650879485. Tick proxy per PLAN (conservative,
disclosed): 1tick as 1 bp of LOW60 (peg1 = 0.9999*LOW60), 5-tick grid as 5 bp
(peg2 = 0.9995*LOW60); real ticks are ~0.17-0.33 bps, so the proxy peg sits DEEPER than
a real placement and variant fill rates are LOWER bounds — bias is against the idea.

## Replica + placebo gate (4-phase-mean w*y units; Y4 2025 is post-release research data, labelled)

| year | base S / DD | V1 S / DD (diff) | V2 S / DD (diff) |
|---|---|---|---|
| 2021 dev | 0.911 / 0.856 | 0.933 / 0.863 (+0.022) | 0.927 / 0.869 (+0.016) |
| 2022 dev | 0.833 / 0.951 | 0.826 / 0.905 (-0.006) | 0.827 / 0.905 (-0.005) |
| 2023 dev | 2.100 / 0.800 | 2.082 / 0.806 (-0.017) | 2.097 / 0.806 (-0.003) |
| 2024 dev | 3.197 / 0.355 | 3.262 / 0.305 (+0.064) | 3.259 / 0.305 (+0.062) |
| 2025 post-release | 0.677 / 0.607 | 0.682 / 0.622 (+0.005) | 0.677 / 0.622 (-0.001) |

- dSum5y: V1 +0.067 (need >= +0.273) FAIL; V2 +0.069 FAIL.
- Sum-half (S >= base): V1 3/5 FAIL; V2 2/5 FAIL (need 4/5).
- DD-half (DD <= base + 0.01): V1 4/5 PASS; V2 3/5 FAIL (need 4/5).
- Gate (all three legs): V1 FAIL; V2 FAIL -> engine NOT run per the binding rule.
- Consequently there is no dev4 robust pick, no 5y %/month, no engine full-path DD and no
  engine win rates to report; the G2 reference (v421 R2B1D17BFG2) was not re-run (nothing
  passed to compare against it). Replica fill stats: base 22312 / win 0.7016 / mean
  17.87 bps -> V1 22103 / 0.7024 / 18.55 bps, V2 22097 / 0.7024 / 18.53 bps.

## Tape-leg diagnostics (the only changed leg; fees/funding split)

Peg binds on 2369/1095500 rungs (V1, 0.22%) and 2456 (V2, 0.22%): the trailing-60m low
sits below the 2.5-5.0sg sigma price only after a dump straight into the bar open, so
the idea fires ~2 times per 1000 rungs. On those rungs the per-fill mean improves
+0.68 bps (17.87 -> 18.55 bps) with 209 fewer fills (-0.9%) and win rate flat 0.7016 ->
0.7024 — the expected sign (less mid-sweep pick-off) at the expected rarity. Fees are
identical by construction (fill maker 0.0002 + TP maker / stop taker legs from the
variant px); funding is identical (timeout settlement flag unchanged, exits measured
from px). Full-path replica DD improves -0.11 (3.127 -> 3.015) via the 2024 tail
(0.355 -> 0.305), but the 5y sum delta +0.067 is 4x below the pooled placebo p95
(+0.273, ~3.5% of base) — indistinguishable from size-tilt luck (shape-A p95 +0.342).

## Leakage checklist

- Feature timing: sigma from 4h opens <= T-1 bar; LOW60 from 1m lows in [T-60m, T-1m]
  only (slice [base-60, base), minute T excluded; all-NaN -> sigma fallback);
  n from 1m closes at T+m-1; truncation-tested in tests/test_oc_tapepeg.py (placement
  window cannot move the peg; post-exit minutes cannot move the outcome).
- Label windows: no labels fit anywhere (replica exits are mechanical stop/TP/timeout legs).
- Fit windows: no fits, no thresholds, no quantiles anywhere (tick 1bp / grid 5bp frozen
  ex-ante in PLAN); no test-year statistic feeds any choice.
- Fill timing: entry live 16..238 strict low<px; taker/timeout legs unchanged; stop-first
  in the shared minute (backstop > stop > TP); NaN minutes never fill/trigger. Gate costs
  inside every leg (maker 0.0002 / taker 0.00055 / longs 0.0001 per settling 8h, shorts n/a).
- Coverage: all 5 anchor years fully covered (independent per-arm keep on finite exit net;
  base n exact). No post-hoc row.
- 5-year screen convention: same as `oc_placebo_dip`/`oc_dipexit`/`oc_makerexit` (replica
  gate on 5 years incl. post-release Y4 as research data); the engine "scored ONCE" rule
  never triggered (no engine run). Any engine revival would need prospective validation.

## What failed and why

Both pre-registered variants fail at the screen with margin on the sum legs (V1 dSum
+0.067 / 3-of-5; V2 +0.069 / 2-of-5; need +0.273 and 4-of-5): the tape peg is directionally
right (+0.7 bps per fill, DD -0.11 full-path) but fires on only 0.22% of rungs, so the
yearly sum cannot separate from placebo noise — the Maker's-Dilemma saving exists but is
too rare at 2.5-5.0sg depths with a 60m lookback to move the book. V2's 5-tick rounding
adds nothing over V1 (dSum +0.002 apart, one fewer sum-half). Direction closed in this
form: anchoring R2-depth rungs to the 60m printed low carries no selectable dip edge;
a longer lookback or shallower-rung application would be a NEW idea, not a disclosed
extra row, and is not warranted here.

## Repro

`research/tournament/oc_tapepeg/{PLAN.md,tapepeg.py,run.py,results.json,tmp/ledger.npz,
tmp/smoke.json}` + `tests/test_oc_tapepeg.py` (11 pass, 1 schema test now live).
Heavy via heavy_slot (tag oc_tapepeg, slot_0, one process, one coin at a time, float32
1m; full 4-phase run ~130 s). results.json = replica gate output (no engine rows exist).

## Vietnamese verdict

V1 rớt screen (dSum +0,067, chỉ thắng 3/5 năm; cần +0,273 và 4/5) vì neo tape chỉ khớp
0,22% rung dù mỗi fill tốt hơn +0,7 bps, V2 cũng rớt (+0,069, 2/5; làm tròn 5-tick không thêm gì).
Kết luận: REJECT cả hai biến thể tape-peg ở dạng đăng ký trước, không chạy engine,
đóng hướng này ở độ sâu R2 + lookback 60m.
