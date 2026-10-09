# oc_cboostmanual REPORT (frozen rows, single heavy pass 2026-10-08)

Can the MANUAL product use the cascade boost (a human scales bracket sizes
x1.5 for 7 days after a cascade)? Pre-registered rows only: M5_human
(deployed MANUAL reference), KM_B7 (dip rungs x1.5 inside the 7-day
post-cascade window), KM_B3 (dip rungs x1.5 inside the 3-day window).
Cascade definition frozen VERBATIM oc_cascadedelay (closes-only
|r| > 4*SIG(540,min120), tc = T+4h, union over 5 majors per shift, window
(tc, tc+Nd] market-wide; human acts from the NEXT bar after the cascade
close). LABEL: new product variant; CONTAMINATED like oc_cascadeboost (the
idea was formed after a replica that covered all five years) - the
post-release year 2025-09-24..2026-09-23 is a LABELLED DIAGNOSTIC, scored
once, never used to choose. Selection on dev4 ONLY.

## Baseline reproduction (gate, passed)

- M5_human rerun is BIT-EXACT vs oc_manualcap_runs.pkl (max abs d(eq) =
  0.000e+00) and equals R5 3.728 / W 0.847 / maxDD 17.94 / fullDD 17.79 /
  book_win .6482. Harness copied exactly from oc_k2manual/oc_c2manual
  (M5 pipe v367, human schedule win_start=15 / sleeve_start=16, night bar
  skipped, agents ON); only the multiplier table swapped (frozen
  oc_cascadeboost boost_mult_4shift.parquet, 53,877 rows, market-wide per
  shift, joined on bar-open T with exact match; 0 misses on all 4 phases,
  no ffill fallback used, nothing imputed).
- Parquet time-bar means (pre-registered, no outcomes): B7
  1.199/1.254/1.258/1.205/1.233, B3 1.107/1.144/1.152/1.115/1.131.
  Engine-sized means run above them (B7 1.26-1.36, B3 1.19-1.25) because
  the engine skips night bars while the parquet means include them (same
  pattern as oc_c2manual); dip fills cluster in volatile windows so the
  boost binds where it is active. The rule applied as coded.
- Gate costs maker 0.0002 / taker 0.00055, longs pay 0.0001/8h, shorts
  nothing; limits fill only on 1m trade-through, no fill minutes 0..15,
  stop-first. Single heavy_slot pass (tag oc_cboostmanual), heartbeat
  every 600 s.

## Results (reset metric %/month geo; DD = max yearly 1m DD; fullDD v388.mix)

| year | M5_human R | KM_B7 R | KM_B3 R | M5 DD | B7 DD | B3 DD |
| --- | --- | --- | --- | --- | --- | --- |
| 2021-09-24 | 0.847 | 0.342 | 0.201 | 16.54 | 18.56 | 19.38 |
| 2022-09-24 | 1.585 | 1.016 | 1.129 | 17.94 | 20.04 | 20.03 |
| 2023-09-24 | 4.413 | 4.970 | 5.105 | 17.36 | 18.75 | 16.67 |
| 2024-09-24 | 7.948 | 8.612 | 8.444 | 8.24 | 8.13 | 8.14 |
| 2025-09-24 (CONTAMINATED diagnostic) | 3.994 | 4.359 | 4.345 | 11.69 | 12.98 | 12.51 |

| row | R5 | W | maxDD | fullDD | Rdev4 | Wdev4 | DDdev4 | Rlast |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M5_human | 3.728 | 0.847 | 17.94 | 17.79 | 3.661 | 0.847 | 17.94 | 3.994 |
| KM_B7 | 3.817 | 0.342 | 20.04 | 22.99 | 3.682 | 0.342 | 20.04 | 4.359 |
| KM_B3 | 3.803 | 0.201 | 20.03 | 24.47 | 3.668 | 0.201 | 20.03 | 4.345 |

Trades/wins (pooled 5y): book M5 3744 @.6482, B7 3658 @.6498, B3 3708
@.6475; rung M5 6417 @.7013, B7 6018 @.6951, B3 6070 @.6959; all-trade win
.6817 / .6780 / .6775. Book win clears the 55% MANUAL floor on every row;
R5 fails the 5%/month floor on every row and fullDD fails on both boost
rows. Per-year book wins move little (B7 .629-.681, B3 .627-.681 vs M5
.626-.684); rung wins slip ~0.6pp (bigger sizes meet the same exits).
Book trade counts differ slightly from M5 (shared equity path / risk
budget contention under 1.5x dip sizes; same effect, smaller, seen in
oc_k2manual/oc_c2manual).

## Selection (dev4 ONLY) - robust pick: none-eligible

- Eligible = DDdev4 <= 20 and no losing dev year: M5_human True (17.94),
  KM_B7 False (20.04 > 20), KM_B3 False (20.03 > 20). No losing dev year on
  any row, but BOTH candidates breach the DD gate on dev4 alone, so the
  robust pick is none-eligible. (For reference B7 beats B3 on dev4 mean
  3.682 vs 3.668 and worst 0.342 vs 0.201, but neither is pickable.)
- The BOT result does NOT transfer: on the BOT, B7 lifted dev4 mean
  5.60 -> 6.74 AND the worst year 2.59 -> 2.96; on MANUAL, B7 adds
  +0.021pp dev4 mean (+0.089pp R5) while HALVING the worst dev year
  (0.847 -> 0.342, B3 -> 0.201) and pushing DD over the gate (full-path
  17.79 -> 22.99/24.47, +5-7pp). The 2021 collapse (0.847 -> 0.342/0.201)
  and the 2022 DD breach (17.94 -> 20.04/20.03) are where the extra post-
  cascade size meets the legs the MANUAL book cannot offset. The
  contaminated last-year diagnostic (+0.365pp B7, +0.351pp B3) proves
  nothing by construction.
- MANUAL gate (R5 >= 5, fullDD < 20, book win >= 55%): all rows fail R5;
  both boost rows additionally fail fullDD.

## Leakage audit

- feature timing: trigger at tc uses only 4h closes with close_time <= tc;
  SIG window excludes the tested bar (no self-inclusion); boost window
  strictly after tc (0 < T-tc <= Nd, k >= 1: the human acts from the next
  bar, never the cascade bar itself); the engine joins the frozen parquet
  on (shift, T = idx[i]+4h) only - exact grid match (0 misses), causal
  ffill fallback never triggered; R2 size/TP tables keyed by bar-open T
  only; no 1m data enters any decision (causality test in
  tests/test_oc_cboostmanual.py asserts the bar-open key and bans
  fill-minute markers; truncation test: dropping later bars cannot change
  triggers at kept times).
- label windows: no new labels; no outcome enters any sizing decision.
- fit windows: no fits; threshold 4.0, windows 540/120, boost 1.5, N = 7/3
  all frozen ex-ante, never scanned; no statistic from any test year feeds
  any choice (parquet year means use feature rows only).
- fill timing: no fill minutes 0..15 (win_start=15 books,
  sleeve_start=16 dips, stricter than the minute-5 user rule); limits fill
  only on 1m trade-through; stop-first on same-bar SL+TP touch; dip timeout
  at next 4h open.
- coverage: 4h closes cover every anchor year - no skipped year, nothing
  imputed (missing join -> mult 1, counted; count = 0).

## Verdict

KM_B7 closes 0.089pp of the 1.272pp MANUAL gap to 5 %/month (R5 3.817 vs
M5 3.728, gap left 1.183pp; Rdev4 +0.021pp) while halving the worst dev
year (0.342 vs 0.847) and breaching the DD gate (DDdev4 20.04, full-path
22.99); KM_B3 is weaker on every dev4 headline (R5 +0.075pp, W 0.201,
DDdev4 20.03, fullDD 24.47). The BOT cascade boost does not transfer to
MANUAL - close this direction, keep M5_human.

Cascade boost chi cong them ~0,09 diem %/thang vao khoang cach MANUAL den 5 % (R5 3,82, con thieu ~1,18) nhung pha vo tran DD (20,04/22,99) va cat doi nam te nhat: loai ca B7 va B3.
MANUAL khong ke thua duoc edge textbook BOT, van thieu ~1,2 diem %/thang: giu M5_human, dong huong cascade-boost tren bracket.
Ket luan: REJECT - khong dua cascade boost vao san xuat MANUAL, khong can bang chung prospective cho huong nay.
