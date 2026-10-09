# oc_m_btceth REPORT (frozen rows, single heavy pass 2026-10-08)

IDEAS9 #1: BTC+ETH-only bracket focus (liquid-pair concentration) on MANUAL.
Pre-registered rows only: M5_human (deployed MANUAL reference), V1_BTCETH
(book+dip brackets ONLY on BTC+ETH, others flat), V2_BTCETHSOL (ONLY on
BTC+ETH+SOL, BNB/XRP flat). Coin sets frozen ex-ante; no fits/thresholds.
Single 4-phase pass via heavy_slot tag oc_m_btceth; heartbeat every 10 min.

## Baseline reproduction (gate, passed)

- M5_human rerun is BIT-EXACT vs oc_manualcap_runs.pkl (max abs d(eq) =
  0.000e+00) and equals R5 3.728 / W 0.847 / maxDD 17.94 / fullDD 17.79 /
  book_win .6482. Harness copied exactly from oc_k2manual (M5 pipe v367,
  human schedule win_start=15 / sleeve_start=16, night bar skipped, agents
  ON); only the coin universe changed.
- Gate costs maker 0.0002 / taker 0.00055, longs pay 0.0001/8h, shorts
  nothing; limits fill only on 1m trade-through, no fill minutes 0..15,
  stop-first. Bybit: resting GTC limits + attached TP/SL (OCO-like pair),
  reduce-only SL; no re-pegging.

## Results (reset metric %/month geo; DD = max yearly 1m DD; fullDD v388.mix)

| year | M5_human R | V1 R | V2 R | M5 DD | V1 DD | V2 DD |
| --- | --- | --- | --- | --- | --- | --- |
| 2021-09-24 | 0.847 | 0.107 | 1.331 | 16.54 | 9.18 | 8.96 |
| 2022-09-24 | 1.585 | 1.226 | 0.966 | 17.94 | 9.81 | 16.80 |
| 2023-09-24 | 4.413 | 2.486 | 3.302 | 17.36 | 11.60 | 15.43 |
| 2024-09-24 | 7.948 | 2.254 | 3.411 | 8.24 | 3.22 | 3.55 |
| 2025-09-24 (POST-RELEASE, scored once) | 3.994 | 1.418 | 2.145 | 11.69 | 10.06 | 11.61 |

| row | R5 | W | maxDD | fullDD | Rdev4 | Wdev4 | DDdev4 | Rlast |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M5_human | 3.728 | 0.847 | 17.94 | 17.79 | 3.661 | 0.847 | 17.94 | 3.994 |
| V1_BTCETH | 1.495 | 0.107 | 11.60 | 11.42 | 1.514 | 0.107 | 11.60 | 1.418 |
| V2_BTCETHSOL (PICK, dev4 only) | 2.226 | 0.966 | 16.80 | 18.58 | 2.246 | 0.966 | 16.80 | 2.145 |

Trades/wins (pooled 5y): book M5 3744 @.6482, V1 1531 @.6172, V2 2276
@.6428; rung M5 6417 @.7013, V1 2778 @.6757, V2 3886 @.6925; all-trade win
.6817 / .6549 / .6741. Book win by year: M5
.643/.626/.640/.640/.684; V1 .576/.597/.639/.604/.652; V2
.601/.643/.656/.620/.681. No losing dev year on any row; all rows DDdev4
<= 20 (eligible), but neither variant reaches dev4 mean >= 5.

Robust pick (dev4 ONLY, DD <= 20, no losing year, prefer mean >= 5, then
highest WORST, ties -> mean): neither variant hits mean >= 5, so the pool
is both; V2 wins on WORST (0.966 vs 0.107). PICK = V2_BTCETHSOL. The
post-release year was scored once, in the same single pass, for all frozen
rows (oc_k2manual precedent) and labelled POST-RELEASE; it was never used
to choose (V1's last-year row is context only).

MANUAL gap: M5_human R5 3.728 is 1.272 pp short of the 5 %/month floor.
The pick V2 R5 2.226 closes NONE of it - the gap widens to 2.774 pp
(-1.502 pp vs M5; V1 widens it further to 3.505 pp). Return falls on every
dev year for V1 and on 3/4 dev years for V2; the removed SOL/BNB/XRP (V1)
and BNB/XRP (V2) brackets carried P&L that concentration does not replace
(same mechanism as the CLOSED dip-only oc_manual2coin: 3.24/3.39 vs 3.73).
DD improves for V1 (fullDD 11.42) but at an unacceptable return cost; V2
fullDD 18.58 passes < 20 yet R5 fails. MANUAL gate (R5>=5, fullDD<20, book
win>=55%): all rows fail R5.

## Leakage audit

- feature timing: coin allow-lists are frozen string constants (no data);
  book wrapper keys only on (bar index, coin index, position state, night
  hour); dip sleeve_filter keys only on (bar index, coin index, night
  hour); R2 size/TP tables keyed by holding-bar time T (bar-open lookup
  only); no 1m data enters any decision (causality test in
  tests/test_oc_m_btceth.py asserts this and bans fill-minute markers).
- label windows: no new labels; no outcome enters any placement decision.
- fit windows: no fits/thresholds/quantiles of any kind; coin sets frozen
  ex-ante, never picked per-year; sigma/TP distances frozen (M5_human);
  human schedule identical both legs.
- fill timing: no fill minutes 0..15 (win_start=15 books, sleeve_start=16
  dips, stricter than the minute-5 user rule); limits fill only on 1m
  trade-through; stop-first on same-bar SL+TP touch; dip timeout at next
  4h open.

## Verdict

V2 (the dev4 pick) R5 2.226 vs M5 3.728 closes 0.000 pp of the 1.272 pp
MANUAL gap - it widens the gap by 1.502 pp (V1 by 2.233 pp); concentration
cuts DD (V1 fullDD 11.42) but deletes the P&L the dropped coins carried;
close the bracket-focus direction, MANUAL still needs entry edge.

Tap trung BTC+ETH (V1) chi con R5 1,50, them SOL (V2) duoc R5 2,23 so voi san M5 3,73: khong dong duoc chut nao trong 1,27 diem %/thang con thieu, DD co giam nhung gia qua dat: loai.
MANUAL van thieu edge vao lenh chu khong phai tap trung coin: giu M5_human, dong huong bracket-focus.
Can bang chung prospective truoc khi dua bat ky gioi han coin nao vao san xuat MANUAL.
