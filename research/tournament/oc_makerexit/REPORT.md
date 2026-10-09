# oc_makerexit REPORT (2026-10-08; PLAN frozen before any outcome)

IDEAS6 #1 (rank 1): maker-only timeout exit — at each 4h timeout place a reduce-only SELL limit
at close-mid+1tick for 60 min (trade-through maker, minute-5 ban), remainder taker. V1 = 100% at
+1tick; V2 = 50% +1tick / 50% +3ticks. HOW-only change: entries, sizes (B1), TP (1.0sg),
stops (4sg close5 / 8sg backstop, stop-first) unchanged; only the timeout leg's execution changes
(CLOSED WHEN-holds `oc_holdext`/`oc_condhold` and TP-level `oc_dipexit` kept as distinct).

STATUS: DONE. 4-phase D0+B1 replica exact (n = 22312, base sum5y = 7.718304, phase-0 sums and
4-phase means match `oc_dipexit`/`oc_placebo_dip` to 1e-3) — BOTH variants FAIL the replica +
placebo gate decisively -> NO 4-phase engine run (negative result, valid — the
oc_crashgate/oc_rungquality path). No post-hoc change (smoke-flag wiring fixes all pre-outcome;
the full ledger was computed ONCE).

## Replica fidelity (base, not a gate — disclosed)

Phase-0 raw sums 2.388/0.183/3.810/2.579/0.712 = `oc_dipexit` ref to 1e-3; 4-phase-mean sums
0.911/0.833/2.100/3.197/0.677 and DDs 0.856/0.951/0.800/0.355/0.607 = `oc_placebo_dip` exactly;
base sum5y 7.718304 exact; n = 22312 exact; timeouts 9160/22312 = 41.1% (cf. `oc_condhold`
41.0%). Ledger checksum de87c0f0122ee26e. Tick proxy per PLAN (conservative, disclosed): +1tick
as +1 bps, +3ticks as +3 bps above the timeout-open mid (real ticks ~0.17-0.33 bps, so the proxy
fill rate is a LOWER bound — bias is against the idea, yet it still fails).

## Replica + placebo gate (4-phase-mean w*y units; Y4 2025 is post-release research data, labelled)

| year | base S / DD | V1 S / DD (diff) | V2 S / DD (diff) |
|---|---|---|---|
| 2021 dev | 0.911 / 0.856 | 0.469 / 1.010 (-0.442) | 0.483 / 1.009 (-0.428) |
| 2022 dev | 0.833 / 0.951 | 0.568 / 0.990 (-0.265) | 0.581 / 0.988 (-0.251) |
| 2023 dev | 2.100 / 0.800 | 1.665 / 0.848 (-0.434) | 1.681 / 0.848 (-0.419) |
| 2024 dev | 3.197 / 0.355 | 3.074 / 0.361 (-0.124) | 3.076 / 0.360 (-0.122) |
| 2025 post-release | 0.677 / 0.607 | 0.541 / 0.653 (-0.136) | 0.556 / 0.648 (-0.121) |

- dSum5y: V1 -1.401 (need >= +0.273) FAIL; V2 -1.341 FAIL.
- Sum-half (S >= base): V1 0/5 FAIL; V2 0/5 FAIL (loses EVERY year, worst 2021).
- DD-half (DD <= base + 0.01): V1 1/5 FAIL (only 2024 within tolerance); V2 1/5 FAIL.
- Gate (all three legs): V1 FAIL; V2 FAIL -> engine NOT run per the binding rule.
- Consequently there is no dev4 robust pick, no 5y %/month, no engine full-path DD and no engine
  win rates to report; the G2 reference (v421 R2B1D17BFG2) was not re-run (nothing passed to
  compare against it). Replica win rates (fill-level): base 0.7016 -> V1 0.6969 / V2 0.6977;
  replica mean 17.87 bps -> 13.45 / 13.62 bps.

## Timeout-leg diagnostics (the only changed leg; fees/funding split)

9160 base timeouts: V1 maker-fills 8308 (90.7%), remainder taker 766 (8.4%), window stop 68,
window backstop 18. Fee split per filled leg: +3.5 bps fee save (taker 0.055% -> maker 0.02%)
plus +1 bp price (limit above mid) = +4.5 bps vs the taker timeout — the expected saving IS
realised on 9 of 10 timeouts. Funding is identical both arms (mid-settlement fund paid once
either way; the 60-min window never crosses a second settlement). Yet the variant loses -1.40:
the 8.4% unfilled remainders sell 60 min later into still-falling tape and the 86 kept-stop
legs fire deep (frozen -4sg/-8sg), each contributing roughly -100 to -200 bps vs the o2 exit —
swamping the +4.5 bps saved on the filled legs. Textbook Maker's Dilemma (IDEAS6 lit:
fill-prob vs post-fill return, adverse fills): the limit fills on the +1 bp bounce and goes
unfilled precisely when the tape keeps dumping, so the remainder taker eats the full drift.

## Leakage checklist

- Feature timing: sigma from 4h opens <= T-1 bar; n from 1m closes at T+m-1; limit P from the
  timeout open o2 only (known at T+240); truncation-tested in tests/test_oc_makerexit.py (later
  minutes and banned-prefix minutes cannot move the outcome).
- Label windows: no labels fit anywhere (replica exits are mechanical stop/TP/timeout/maker legs).
- Fit windows: no fits, no thresholds, no quantiles anywhere (deltas 1/3 bps frozen ex-ante in
  PLAN); no test-year statistic feeds any choice.
- Fill timing: entry live 16..238 strict low<lv; maker live 245..299 strict high>P with 240..244
  ban; taker remainder; stop-first in the shared minute (backstop > stop > maker); NaN minutes
  never fill/trigger. Gate costs inside every leg (maker 0.0002 / taker 0.00055 / longs 0.0001
  per settling 8h, shorts n/a).
- Coverage: all 5 anchor years fully covered (paired keep base+V1+V2 finite; drop_nf = 0,
  drop_end = 0 — no timeout near the data end lacked its window).
- 5-year screen convention: same as `oc_placebo_dip`/`oc_dipexit`/`oc_rungquality` (replica gate
  on 5 years incl. post-release Y4 as research data); the engine "scored ONCE" rule never
  triggered (no engine run). Any engine revival would need prospective validation.

## What failed and why

Both pre-registered variants fail at the screen with margin (V1 dSum -1.401 / 0-of-5; V2 dSum
-1.341 / 0-of-5; need +0.273 and 4-of-5): the 60-minute maker extension does not harvest a fee
saving — it converts a clean next-open cut into (a) 8.4% late-taker remainders sold an hour
deeper into weak tape and (b) ~1% deep stop/backstop outs at frozen -4sg/-8sg, while the 90.7%
maker fills each save only ~4.5 bps. DD is worse in 4/5 years (only 2024 within the 1 pp
tolerance). Direction closed: maker-only timeout execution carries no dip edge in this family
at +1/+3 bps offsets — the timeout tape is too adversely selected for passive exits, consistent
with the cited MM lit. A tighter (real-tick) offset would fill MORE often but at a SMALLER price
edge with the same adverse remainder tail, so no disclosed extra row is warranted.

## Repro

`research/tournament/oc_makerexit/{PLAN.md,makerexit.py,run.py,results.json,tmp/ledger.npz,
tmp/run.log,tmp/smoke.json}` + `tests/test_oc_makerexit.py` (13 pass, 1 schema test now live).
Heavy via heavy_slot (tag oc_makerexit, slot_1, one process, one coin at a time, float32 1m;
full 4-phase run ~57 s after the BTC-only smoke wiring check). results.json = replica gate
output (no engine rows exist).

## Vietnamese verdict

V1 rớt ngay từ screen (dSum -1,401, thua cả 5 năm dù khớp maker 90,7%; cần +0,273 và 4/5),
V2 cũng rớt (-1,341, 0/5) vì 8,4% lệnh tồn bán trễ vào giá đổ sâu và stop -4sg nuốt hết phí tiết kiệm.
Kết luận: REJECT cả hai biến thể maker-timeout ở dạng đăng ký trước, không chạy engine,
đóng hướng này (bẫy adverse-selection của exit thụ động).
