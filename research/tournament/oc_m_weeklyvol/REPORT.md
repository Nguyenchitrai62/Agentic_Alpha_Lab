# oc_m_weeklyvol REPORT (frozen rows, single heavy pass 2026-10-08)

IDEAS9 #5: Weekly-frozen vol distance table (slow-adaptive brackets) on
MANUAL. Pre-registered rows only: M5_human (deployed MANUAL reference),
V1_WEEKLY (every sigma-scaled bracket distance from the Sunday 00 UTC
sigma360 print, frozen all week), V2_WEEKLY5T (V1 + 5-tick grid rounding
of every sigma-derived price). k frozen ex-ante (dip rungs 3.0/4.0, dip
SL 8.0, book SL 5.0/TP 10.0, entry 0.75; R2 TP mults unchanged); ticks
frozen ex-ante (BTC 0.10, ETH/SOL 0.01, BNB 0.10, XRP 0.0001; steps x5).
Single 4-phase pass via heavy_slot tag oc_m_weeklyvol; heartbeat every
10 min; log in tmp/run.log.

## Baseline reproduction (gate, passed)

- M5_human rerun is BIT-EXACT vs oc_manualcap_runs.pkl (max abs d(eq) =
  0.000e+00) and equals R5 3.728 / W 0.847 / maxDD 17.94 / fullDD 17.79 /
  book_win .6482. Harness copied exactly from oc_m_conflict (M5 pipe v367,
  human schedule win_start=15 / sleeve_start=16, night bar skipped, agents
  ON); only the sigma input changed (V1/V2 swap prep sig4 for the weekly
  array; V2 additionally rounds prices via the audited patched simulate).
- Gate costs maker 0.0002 / taker 0.00055, longs pay 0.0001/8h, shorts
  nothing; limits fill only on 1m trade-through, no fill minutes 0..15,
  stop-first. Bybit: GTC limit from the printed table + attached TP/SL
  (OCO-like pair), reduce-only SL; no re-pegging, no intraday recompute.
- Weekly table diagnostics (per phase): 262 Sunday prints, 96.4-98.7% of
  (bar, coin) cells frozen (pooled frozen_frac 0.9816 on V1/V2, 0.0 on
  M5), fallback to per-bar 1.25% (warmup NaN), mean |frozen/per-bar - 1|
  ~3% (0.0285/0.0302/0.0302/0.0298). The freeze is real and material in
  input space; it just does not convert into return.

## Results (reset metric %/month geo; DD = max yearly 1m DD; fullDD v388.mix)

| year | M5 R | V1 R | V2 R | M5 DD | V1 DD | V2 DD |
| --- | --- | --- | --- | --- | --- | --- |
| 2021-09-24 | 0.847 | 0.757 | 0.757 | 16.54 | 16.89 | 16.89 |
| 2022-09-24 | 1.585 | 1.198 | 1.198 | 17.94 | 18.20 | 18.20 |
| 2023-09-24 | 4.413 | 4.538 | 4.538 | 17.36 | 17.57 | 17.57 |
| 2024-09-24 | 7.948 | 8.289 | 8.289 | 8.24 | 7.88 | 7.88 |
| 2025-09-24 (POST-RELEASE, scored once) | 3.994 | 3.734 | 3.734 | 11.69 | 12.59 | 12.59 |

| row | R5 | W | maxDD | fullDD | Rdev4 | Wdev4 | DDdev4 | Rlast |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M5_human | 3.728 | 0.847 | 17.94 | 17.79 | 3.661 | 0.847 | 17.94 | 3.994 |
| V1_WEEKLY (PICK, dev4 only) | 3.668 | 0.757 | 18.20 | 18.03 | 3.652 | 0.757 | 18.20 | 3.734 |
| V2_WEEKLY5T (tie, context) | 3.668 | 0.757 | 18.20 | 18.03 | 3.652 | 0.757 | 18.20 | 3.734 |

Trades/wins (pooled 5y): book M5 3744 @.6482, V1 3771 @.6497, V2 3784
@.6498; rung M5 6417 @.7013, V1 6754 @.7020, V2 6755 @.7019; all-trade win
.6817 / .6832 / .6832. Book win by year: M5
.643/.626/.640/.640/.684; V1 .635/.631/.636/.644/.692; V2
.634/.632/.639/.643/.691. No losing dev year on any row; all rows DDdev4
<= 20 (eligible), but no variant reaches dev4 mean >= 5.

Robust pick (dev4 ONLY, DD <= 20, no losing year, prefer mean >= 5, then
highest WORST, ties -> mean): neither variant hits mean >= 5, so the pool
is both; WORST ties 0.757 to 0.757, mean ties 3.652 to 3.652 (V2's 5-tick
rounding moves only a handful of fills: +13 book / +1 rung trades vs V1,
return/DD identical to 3 decimals), so PICK = V1_WEEKLY by the
first-maximum tiebreak, disclosed. The post-release year was scored once,
in the same single pass, for all frozen rows (oc_k2manual precedent) and
labelled POST-RELEASE; it was never used to choose (V2's last-year row is
context only).

MANUAL gap: M5_human R5 3.728 is 1.272 pp short of the 5 %/month floor.
The pick V1 R5 3.668 closes NONE of it - the gap widens by 0.060 pp to
1.332 pp (V2 identical). Weekly freezing loses on 2/4 dev years (2021:
-0.090, 2022: -0.387) and wins small on 2/4 (2023: +0.125, 2024:
+0.341); DD is flat-to-worse (fullDD 18.03 vs 17.79). The ~3% mean sigma
deviation washes out: per-bar sigma noise is not what misprices the
brackets (same lesson as oc_bookoffset: rescaling distances does not buy
edge). MANUAL gate (R5>=5, fullDD<20, book win>=55%): all rows fail R5.

## Leakage audit

- feature timing: weekly sigma for week [Sun, Sun+7d) is sig4[jw] with
  T_jw <= Sunday 00 UTC (opens with index <= jw, i.e. closes <= Sunday
  close minus 4h, strictly causal; no jw / NaN -> per-bar fallback, same
  as M5 there); R2 size/TP tables keyed by holding-bar time T (bar-open
  lookup only); V2 rounding uses only the computed price + frozen tick;
  no 1m data enters any placement decision (causality tests in
  tests/test_oc_m_weeklyvol.py ban fill-minute markers and assert the
  rounding helper closes over price + tick only; synthetic tests check
  Sunday-boundary freezing, warmup fallback and no-lookahead first week).
- label windows: no new labels; no outcome enters any distance/table rule.
- fit windows: no fits/thresholds/quantiles of any kind; k frozen ex-ante
  (3.0/4.0, 8.0, 5.0/10.0, 0.75), ticks frozen ex-ante, Sundays are the
  public calendar; human schedule identical on all rows; no statistic from
  any test year feeds any choice.
- fill timing: no fill minutes 0..15 (win_start=15 books, sleeve_start=16
  dips, stricter than the minute-5 user rule); limits fill only on 1m
  trade-through; stop-first on same-bar SL+TP touch; dip timeout at next
  4h open; the weekly table is never recomputed intraday.

## Verdict

V1 (the dev4 pick) R5 3.668 vs M5 3.728 closes 0.000 pp of the 1.272 pp
MANUAL gap - it widens the gap by 0.060 pp (V2 identical to 3 decimals);
weekly freezing adds rungs (+337) but no edge, DD flat-to-worse
(fullDD 18.03 vs 17.79); close the slow-adaptive-table direction.
Bang tuan sigma (V1) chi duoc R5 3,67 so voi san M5 3,73: khong dong duoc chut nao trong 1,27 diem %/thang con thieu, V2 lam tron 5-tick khong doi duoc gi: loai.
MANUAL khong thieu bang vol tuan ma thieu edge vao lenh: giu M5_human, dong huong weeklyvol.
Can bang chung prospective chi khi co bang moi voi k hoc walk-forward, khong phai sigma tuan co dinh.
