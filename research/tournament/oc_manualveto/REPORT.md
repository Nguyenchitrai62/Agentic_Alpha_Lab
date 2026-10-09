# oc_manualveto REPORT (frozen rows, single heavy pass 2026-10-08)

IDEAS5 #8: MANUAL volatility veto of new bracket placement (skip-only,
holds/exits unchanged). Pre-registered rows only: M5_human (deployed
MANUAL reference), VETO_V1 (per-coin 4h sigma360 > trailing-90d p80),
VETO_V2 (V1 OR BTC 24h range > 2x trailing-30d median, global).
CLOSED rows read first: oc_manualcap/shallow/split/rest/K2, oc_k2manual
(+0.112 of 1.272 gap), oc_ladderfill. TP/stop distances frozen.

## Baseline reproduction (gate, passed)

- M5_human rerun is BIT-EXACT vs oc_manualcap_runs.pkl (max abs d(eq) =
  0.000e+00) and equals R5 3.728 / W 0.847 / maxDD 17.94 / fullDD 17.79 /
  book_win .6482. Veto gate: no veto fires on the reference row.
- Harness: MANUAL 4-phase (M5 pipe v367, human schedule win_start=15 /
  sleeve_start=16, night bar skipped, agents ON); gate costs maker
  0.0002 / taker 0.00055, longs pay 0.0001/8h, shorts nothing; limits
  fill only on 1m trade-through, no fill minutes 0..15, stop-first.
- Data: existing 1m klines only (BTC 8 files 2019..2026, ETH 8 files
  2019..2026, SOL/BNB/XRP 7 files 2020..2026); full anchor coverage,
  zero skipped years (never imputed). Veto warmup from 2020-08-01.

## Results (reset metric %/month geo; DD = max yearly 1m DD; fullDD v388.mix)

| year | M5_human R | VETO_V1 R | VETO_V2 R | M5 DD | V1 DD | V2 DD |
| --- | --- | --- | --- | --- | --- | --- |
| 2021-09-24 | 0.847 | 0.659 | 1.043 | 16.54 | 15.67 | 13.27 |
| 2022-09-24 | 1.585 | -0.389 | 1.053 | 17.94 | 19.50 | 18.09 |
| 2023-09-24 | 4.413 | 1.667 | 2.666 | 17.36 | 19.28 | 10.89 |
| 2024-09-24 | 7.948 | 6.108 | 4.900 | 8.24 | 6.57 | 6.72 |
| 2025-09-24 (POST-HOC, pick+ref) | 3.994 | (3.815 ctx) | 2.764 | 11.69 | (12.12 ctx) | 14.03 |

| row | R5 | W | maxDD | fullDD | Rdev4 | Wdev4 | DDdev4 | Rlast |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M5_human | 3.728 | 0.847 | 17.94 | 17.79 | 3.661 | 0.847 | 17.94 | 3.994 |
| VETO_V1 | 2.346 | -0.389 | 19.50 | 20.51 | 1.982 | -0.389 | 19.50 | (3.815) |
| VETO_V2 (dev4 pick) | 2.475 | 1.043 | 18.09 | 17.97 | 2.403 | 1.043 | 18.09 | 2.764 |

Trades/wins: book M5 3744 @.6482, V1 2841 @.6572, V2 2743 @.6482;
rung M5 6417 @.7013, V1 4892 @.6938, V2 3511 @.6839;
all-trade win .6817 / .6803 / .6682. Veto rates (share of coin-bars
skipped): V1 .238/.201/.414/.231/.258, V2 .304/.305/.472/.298/.316
per year. V1 cuts 24% of book trades for +0.9pp book win but -1.38pp
R5; V2 cuts 27% for flat book win and -1.25pp R5. The veto skips
winners, not just stop-clusters: every dev year R falls vs M5 on both
variants (V1 2022 goes losing, V1 fullDD 20.51 breaches 20).
Dev4 robust pick: VETO_V1 ineligible (losing dev year 2022, -0.389);
VETO_V2 eligible (DDdev4 18.09, no losing year) and is the pick by
default (single eligible candidate; mean 2.403 < 5 floor either way).
Last year 2025-09-24..2026-09-23 POST-HOC, scored once, never used to
choose: pick V2 2.764 vs ref 3.994 (-1.230pp). V1's last-year 3.815 is
same-pass context only, not scored for selection. MANUAL gate
(R5>=5, fullDD<20, book win>=55%): all rows fail R5.

## Leakage audit

- feature timing: sigma360 (pct_change of 4h opens, rolling 360/min120,
  shift 1) and 24h range (6-bar high-low/close) from 1m bars closing
  <= decision-bar close idx[i] only; p80/median from bars strictly < i
  via merge_asof backward; veto[i,a] joined by (idx[i], coin) bar-open
  only; R2 size/TP tables bar-open keyed; no 1m/minute/fill data enters
  any decision (causality test bans fill-minute markers).
- label windows: no new labels; no outcome enters any veto or sizing.
- fit windows: nothing fitted; thresholds frozen round numbers
  (p80, 2.0x, 90d/540b, 30d/180b, 24h/6b, 360/min120); rolling windows
  past-only; no test-year statistic feeds any choice.
- fill timing: no fill minutes 0..15 (win_start=15, sleeve_start=16,
  stricter than minute-5); limits fill only on 1m trade-through;
  stop-first on same-bar SL+TP touch; dip timeout at next 4h open.

## Verdict

VETO_V2 (dev4 pick) closes -1.258pp of the 1.272pp MANUAL gap to 5
%/month (R5 2.475 vs M5 3.728, gap 2.525pp; Rdev4 -1.258pp) with flat
book win (.6482) and lower rung win (.6839 vs .7013): the veto buys
nothing and sells the trend; close the volatility-veto direction,
MANUAL still needs entry edge, not placement skipping.
VETO_V1 is worse (losing dev year 2022, fullDD 20.51): rejected outright.

Veto bien do bien dong loai bo nguoi chien thang chu khong chi cum stop: V2 mat ~1,26 diem %/thang so voi M5, nam sach cung kem 1,23 diem: loai.
MANUAL van thieu ~2,53 diem %/thang toi san 5 %, can edge vao lenh chu khong phai bo qua vi tri.
Tu choi dua veto bien dong vao san xuat MANUAL: giu M5_human, dong huong veto dat bien dong.
