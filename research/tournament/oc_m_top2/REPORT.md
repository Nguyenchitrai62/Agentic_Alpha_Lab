# oc_m_top2 REPORT (frozen rows, single heavy pass 2026-10-08)

IDEAS9 #4: Max-2 bracket priority (attention cap by conviction) on MANUAL.
Pre-registered rows only: M5_human (deployed MANUAL reference), V1_TOP2
(book+dip brackets ONLY on top-2 coins by close-known |w| each bar), V2_TOP3
(same, top-3). Kept coins unchanged M5_human (all depths/SL/TP, size x1.0,
no rescale); skipped coins wait/hold + no dip, resting SL/TP stay. K = 2/3
frozen; ties BTC>ETH>SOL>BNB>XRP; night skip first. Single 4-phase pass via
heavy_slot tag oc_m_top2; heartbeat every 10 min; nohup + log under tmp/.

## Baseline reproduction (gate, passed)

- M5_human rerun is BIT-EXACT vs oc_manualcap_runs.pkl (max abs d(eq) =
  0.000e+00) and equals R5 3.728 / W 0.847 / maxDD 17.94 / fullDD 17.79 /
  book_win .6482. Harness copied exactly from oc_m_btceth (M5 pipe v367,
  human schedule win_start=15 / sleeve_start=16, night bar skipped, agents
  ON); only the per-bar coin gate changed (frozen allow-list -> top-K).
- Gate costs maker 0.0002 / taker 0.00055, longs pay 0.0001/8h, shorts
  nothing; limits fill only on 1m trade-through, no fill minutes 0..15,
  stop-first. Bybit: resting GTC limits + attached TP/SL (OCO-like pair),
  reduce-only SL; GTC limits only for ranked coins; no re-pegging.
- Realised-exposure control: non-night skip rates 60% (V1) / 40% (V2) of
  (bar, coin) slots every year; kept |w| 2.5-4.3x skipped |w| (V1 kept
  .081-.157 vs skipped .033-.048; V2 kept .069-.124 vs skipped .025-.036),
  so the gate bound as coded and separated conviction as intended.

## Results (reset metric %/month geo; DD = max yearly 1m DD; fullDD v388.mix)

| year | M5_human R | V1 R | V2 R | M5 DD | V1 DD | V2 DD |
| --- | --- | --- | --- | --- | --- | --- |
| 2021-09-24 | 0.847 | -0.887 | -0.674 | 16.54 | 17.16 | 14.90 |
| 2022-09-24 | 1.585 | 1.664 | 1.149 | 17.94 | 15.91 | 19.46 |
| 2023-09-24 | 4.413 | 1.869 | 3.353 | 17.36 | 16.06 | 17.38 |
| 2024-09-24 | 7.948 | 3.135 | 6.582 | 8.24 | 10.40 | 9.04 |
| 2025-09-24 (POST-RELEASE, scored once) | 3.994 | 3.031 | 3.327 | 11.69 | 8.54 | 9.91 |

| row | R5 | W | maxDD | fullDD | Rdev4 | Wdev4 | DDdev4 | Rlast |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M5_human | 3.728 | 0.847 | 17.94 | 17.79 | 3.661 | 0.847 | 17.94 | 3.994 |
| V1_TOP2 | 1.752 | -0.887 | 17.16 | 19.92 | 1.435 | -0.887 | 17.16 | 3.031 |
| V2_TOP3 | 2.719 | -0.674 | 19.46 | 24.50 | 2.567 | -0.674 | 19.46 | 3.327 |

Trades/wins (pooled 5y): book M5 3744 @.6482, V1 2053 @.5991, V2 2853
@.6334; rung M5 6417 @.7013, V1 2700 @.6970, V2 4061 @.6998; all-trade win
.6817 / .6547 / .6724. Book win by year: M5
.643/.626/.640/.640/.684; V1 .595/.548/.631/.577/.624; V2
.612/.620/.619/.657/.654. Rung win by year: M5
.632/.690/.768/.737/.670; V1 .614/.683/.757/.744/.671; V2
.603/.688/.776/.748/.674.

Robust pick (dev4 ONLY, DD <= 20, no losing year, prefer mean >= 5, then
highest WORST, ties -> mean): V1 has a losing dev year (2021 -0.887) and
V2 has a losing dev year (2021 -0.674) -> both ineligible. PICK =
none-eligible. The post-release year was scored once, in the same single
pass, for all frozen rows (oc_k2manual / oc_m_btceth precedent) and
labelled POST-RELEASE; it was never used to choose (V1/V2 last-year rows
are context only; with no pick there is nothing to confirm).

MANUAL gap: M5_human R5 3.728 is 1.272 pp short of the 5 %/month floor.
The cap closes NONE of it: V1 R5 1.752 widens the gap by 1.976 pp (gap
3.248 pp), V2 R5 2.719 widens it by 1.009 pp (gap 2.281 pp). Return falls
on 3/4 dev years for V1 and 3/4 for V2; 2021 turns losing on both; V2
full-path DD breaches 20 (24.50). The dropped coins' brackets carried P&L
the kept coins do not replace (same mechanism as the CLOSED static-cut
oc_m_btceth: concentration deletes return). MANUAL gate (R5>=5,
fullDD<20, book win>=55%): all rows fail R5.

## Leakage audit

- feature timing: rank key is the close-known book target w[i,a] =
  ffill'd research book at idx[i] only (oc_m_conflict precedent); kept set
  cached per bar, no intraday re-rank; R2 size/TP tables keyed by
  holding-bar time T (bar-open lookup only); no 1m data enters any decision
  (causality test in tests/test_oc_m_top2.py asserts the bar-open key and
  bans fill-minute markers).
- label windows: no new labels; no outcome enters any placement decision.
- fit windows: no fits/thresholds/quantiles of any kind; K = 2 / 3 frozen
  integers ex-ante, never picked per-year; sigma/TP distances frozen
  (M5_human); human schedule identical both legs.
- fill timing: no fill minutes 0..15 (win_start=15 books, sleeve_start=16
  dips, stricter than the minute-5 user rule); limits fill only on 1m
  trade-through; stop-first on same-bar SL+TP touch; dip timeout at next
  4h open.

## Verdict

Neither variant is eligible on dev4 (both lose money in 2021) and neither
closes any of the 1.272 pp MANUAL gap - V1 widens it by 1.976 pp, V2 by
1.009 pp with full-path DD 24.50 breaching 20; close the attention-cap
direction, MANUAL still needs entry edge.
Cat bot top-2 (V1) chi con R5 1,75 va top-3 (V2) R5 2,72 so voi san M5 3,73: khong dong duoc chut nao trong 1,27 diem %/thang con thieu, ca hai deu lo nam 2021, V2 con vo DD 24,5: loai.
Giu M5_human, dong huong gioi han so coin theo conviction; can edge vao lenh chu khong phai cat bot co hoi.
