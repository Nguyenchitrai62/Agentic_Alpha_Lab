# oc_recycle REPORT (2026-10-08; PLAN frozen before any outcome)

IDEAS6 #8 (rank 8): winner-recycled dip capital — early TPs leave capital idle till the next 4h open
while fresh rungs print unfilled (budget already committed). Freed TP notional (<=95% phase budget,
here G=2.0 identically both arms) may fill the NEXT frozen rung signal same window at frozen
price/size (maker, minute-5 inherited via the 16..238 live window). V1 = same coin pool;
V2 = any-coin pool. One recycle per unit (pool-depleting), no compounding (recycled fills never
free further capital); stops market taker (D0 machine unchanged). Opposite of `oc_rearm` (which
re-fills the SAME rung after a fill); FIXED exits of `oc_bidttl`/`oc_fillttl` kept as distinct.

STATUS: DONE. 4-phase D0+B1 replica exact (pool n = 22312 = `oc_placebo_dip` ledger; uncapped
4-phase-mean sums 0.911/0.833/2.100/3.197/0.677 = placebo ref to 1e-3; checksum 9f2a1933e3430735)
— BOTH variants FAIL the replica + placebo gate decisively -> NO 4-phase engine run (negative
result, valid — the oc_crashgate/oc_rungquality/oc_makerexit path). No post-hoc change (the full
ledger was computed ONCE; numbers below are reads of the frozen `results.json` + saved ledger).

## Replica fidelity (base, not a gate — disclosed)

- Candidate pool (no budget): 22312 signals, 0 non-finite drops (BTC 4420 / ETH 4592 / SOL 3901 /
  BNB 4772 / XRP 4627); uncapped 4-phase-mean sums match `oc_placebo_dip` [0.911, 0.833, 2.100,
  3.197, 0.677] to 1e-3 — the D0+B1 machine is tick-identical, so the base-vs-rule delta below
  isolates the recycle.
- Committed-budget BASE (the idea's "idle capital" baseline, G=2.0, nothing freed early): 7098
  kept (15214 skipped, 259 cut to room — the cap binds on the median crowded bar by construction).
  V1 keeps 7616 (+518, 534 recycled), V2 keeps 7849 (+751, 778 recycled).

## Replica + placebo gate (4-phase-mean w*y units; Y4 2025 is post-release research data, labelled)

| year | base S / DD | V1 S / DD (diff) | V2 S / DD (diff) |
|---|---|---|---|
| 2021 dev | 0.585 / 0.285 | 0.581 / 0.294 (-0.004) | 0.529 / 0.310 (-0.056) |
| 2022 dev | 0.448 / 0.409 | 0.343 / 0.438 (-0.105) | 0.302 / 0.462 (-0.146) |
| 2023 dev | 1.190 / 0.230 | 1.176 / 0.245 (-0.014) | 1.281 / 0.245 (+0.091) |
| 2024 dev | 1.008 / 0.170 | 1.088 / 0.169 (+0.080) | 1.123 / 0.205 (+0.115) |
| 2025 post-release | 0.032 / 0.324 | 0.050 / 0.314 (+0.019) | 0.020 / 0.308 (-0.011) |

- dSum5y: V1 -0.024 (need >= +0.273) FAIL; V2 -0.007 FAIL.
- Sum-half (S >= base): V1 2/5 FAIL; V2 2/5 FAIL.
- DD-half (DD <= base + 0.01): V1 3/5 FAIL; V2 1/5 FAIL.
- Gate (all three legs): V1 FAIL; V2 FAIL -> engine NOT run per the binding rule.
- Consequently there is no dev4 robust pick, no 5y %/month, no engine full-path DD and no engine
  win rates to report; the G2 reference (v421 R2B1D17BFG2) was not re-run (nothing passed to
  compare against it).

## Diagnostics (frozen ledger reads; why the recycle adds nothing)

- Recycled fills win 70.4% (V1, 534 fills) / 69.5% (V2, 778 fills) yet LOSE money: recycled w*y =
  -0.135 (V1) / -0.165 (V2). Same short-gamma profile as `oc_rearm` (re-armed fills won 62-74%
  yet lost in 2/5 years): a ~+1sg maker TP (~+96 bps minus 4 bps fees) against full -4sg/-8sg
  stop tails and taker timeouts — refilling into a level that just printed within the same
  4h window re-buys adversely-selected tape.
- Full-path replica DD (pooled 5y exit-date path, w*y units): base 1.039 -> V1 1.183 / V2 1.355
  (worse both variants); worst day identical -0.730 (the extra fills never help the tail).
- Pooled win rates: base 0.670 -> V1 0.673 / V2 0.673 (flat; the extra winners are small TPs).
- Fee / funding split (leg counts; nets already include gate costs): base TP 3375 / timeout 3539 /
  stop 145 / backstop 39; V1 TP 3680 / timeout 3714 / stop 172 / backstop 50; V2 TP 3779 /
  timeout 3839 / stop 182 / backstop 49. Every fill pays maker 0.0002 on entry; TP legs maker
  (4 bps round trip), stop/backstop/timeout legs taker (7.5 bps); funding 0.0001 applies only to
  exits at x==240 on settling bars (base 3543 / V1 3718 / V2 3844 such exits, settling subset
  identical machine both arms). The extra recycled fills pay full entry fees for negative net.

## Leakage checklist

- Feature timing: sigma from 4h opens <= T-1 bar; n from 1m closes at T+m-1; freed pool from TP
  exits with x <= f only (fully closed before the fill minute — realised cash); truncation-tested
  in tests/test_oc_recycle.py (post-bar minutes cannot move the outcome).
- Label windows: no labels fit anywhere (replica exits are mechanical D0 legs).
- Fit windows: no fits, no thresholds, no quantiles anywhere (G=2.0 and V1/V2 grouping frozen
  ex-ante in PLAN; no test-year statistic feeds any choice).
- Fill timing: entry live 16..238 strict low<lv (minute-5 ban inherited via window start);
  recycled fills reuse the signal's own f >= 16 at frozen lv/w; stop-first in the shared minute
  (backstop > TP > stop > timeout); NaN minutes never fill/trigger. Gate costs inside every leg
  (maker 0.0002 / taker 0.00055 / longs 0.0001 per settling 8h, shorts n/a).
- Coverage: all 5 anchor years fully covered (paired candidate generation; drop_nonfinite = 0).
- 5-year screen convention: same as `oc_placebo_dip`/`oc_dipexit`/`oc_rungquality`/`oc_makerexit`
  (replica gate on 5 years incl. post-release Y4 as research data); the engine "scored ONCE" rule
  never triggered (no engine run). Any engine revival would need prospective validation.

## What failed and why

Both pre-registered variants fail at the screen with margin (V1 dSum -0.024, 2/5 sums, 3/5 DD;
V2 dSum -0.007, 2/5 sums, 1/5 DD; need +0.273 and 4/5 + 4/5): the committed budget binds hard
(68% of signals skipped), yet the winners' freed notionals buy the NEXT frozen signal in the same
window — tape that is adversely selected by construction (the window already printed one winner
and keeps dumping into the remaining rungs). Recycled fills win ~70% of the time at ~+1sg each
but their stop/backstop/timeout tails (-4sg/-8sg/taker) erase the edge, and DD rises in 4-5/5
years. Direction closed: winner-recycling to the next same-window signal carries no dip edge in
this family — the velocity loss is real but unharvestable at frozen prices, consistent with the
`oc_rearm` rejection (same-window refills lose) and the IDEAS6 Maker's-Dilemma lit. No disclosed
extra row is warranted (any tighter pool/looser cap would be post-hoc fitting against the gate).

## Repro

`research/tournament/oc_recycle/{PLAN.md,recycle.py,run.py,results.json,tmp/ledger.npz,
tmp/run.log}` + `tests/test_oc_recycle.py` (12 pass). Heavy via heavy_slot (tag oc_recycle, slot_0,
one process, one coin at a time, float32 1m; full 4-phase run ~95 s after slot wait).
results.json = replica gate output (no engine rows exist).

## Vietnamese verdict

V1 rớt ngay từ screen (dSum -0,024, thắng 2/5 năm dù lệnh tái chế thắng 70,4%; cần +0,273 và 4/5),
V2 cũng rớt (dSum -0,007, 2/5, DD tệ hơn 4/5) vì vốn thắng tái mua ngay phải vùng tape xấu trong cùng
cửa sổ 4h, đuôi stop -4sg nuốt hết lãi TP nhỏ.
Kết luận: REJECT cả hai biến thể winner-recycle ở dạng đăng ký trước, không chạy engine,
đóng hướng này (tái chế vốn thắng cùng-window không có edge, khớp với kết quả oc_rearm).
