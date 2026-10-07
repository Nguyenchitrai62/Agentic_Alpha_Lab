# oc_contrib REPORT — where the R2B1D17BF return and drawdown sit (2026-10-06; PLAN pre-registered)

DIAGNOSTIC (no rule, no selection, no PROMISING verdict). Deployment pick R2B1D17BF
(registry v411) from `oc_kpi` s=0..3 engine replicas (4 phase sub-accounts, live
2021-09-24..2026-09-23+shift, 26,344 trades: 4,955 book episodes + 21,389 dip rungs).
Method: FIFO rung pairing + v213 book episodes; year = ENTRY in anchor year
`[A_k,A_k+365d)`; `pnl` = fraction of sub-account equity at trade time (rung
`weight*ret` net of rung fees; book `side*(proceeds-cost)-fees`, funding excluded);
`pnl_mix = pnl_sub/4` (1/4 capital per phase, ADDITIVE approximation — see caveats);
`win` = pooled trade win rate; `per_gross` = `sum(pnl)/sum(gross)`. DD = 5 union windows
from `oc_ddanat4p/mix_episodes.json` (full+reset deduped), exit-time realized only
(`exit_t in (peak,trough]`, no open marks, no funding); share = bucket window pnl /
total window pnl. Dip `rung_sl` merges close-stop+backstop (engine logs one kind).
TP choice via R2 table `(T<=fill_t, sym, depth->idx)`, 0 unmatched. Full numbers:
`research/tournament/oc_contrib/results.json`. All five years are research data;
findings need prospective validation.

## (a) Sleeve per anchor year (n | mix% | win | per_gross)

| year | book long | book short | dip |
|---|---|---|---|
| 2021 | 421 \| -5.32 \| 0.423 \| -0.0061 | 513 \| +10.80 \| 0.563 \| +0.0104 | 4109 \| +27.91 \| 0.640 \| +0.0027 |
| 2022 | 452 \| +22.71 \| 0.518 \| +0.0134 | 418 \| -1.76 \| 0.514 \| -0.0015 | 4060 \| +20.05 \| 0.691 \| +0.0017 |
| 2023 | 491 \| +30.73 \| 0.583 \| +0.0209 | 389 \| -12.35 \| 0.422 \| -0.0119 | 4545 \| +28.82 \| 0.729 \| +0.0022 |
| 2024 | 622 \| +37.79 \| 0.547 \| +0.0198 | 553 \| -0.01 \| 0.465 \| -0.0000 | 3946 \| +80.51 \| 0.725 \| +0.0055 |
| 2025 | 396 \| +15.42 \| 0.515 \| +0.0136 | 700 \| +12.62 \| 0.550 \| +0.0098 | 4729 \| +19.36 \| 0.652 \| +0.0017 |
| pooled | 2382 \| +101.33 \| 0.521 \| +0.0143 | 2573 \| +9.30 \| 0.509 \| +0.0016 | 21389 \| +176.65 \| 0.687 \| +0.0029 |

## (b) Dip depth per year, mix% (win)

| year | 2.5 | 3.0 | 3.5 | 4.0 | 5.0 |
|---|---|---|---|---|---|
| 2021 | +46.04 (0.81) | +6.76 (0.65) | -5.21 (0.52) | -11.27 (0.38) | -8.42 (0.35) |
| 2022 | +34.95 (0.87) | +11.71 (0.72) | -2.94 (0.59) | -10.70 (0.44) | -12.96 (0.30) |
| 2023 | +38.64 (0.87) | +12.31 (0.76) | -2.11 (0.63) | -7.30 (0.55) | -12.72 (0.36) |
| 2024 | +55.02 (0.84) | +23.56 (0.73) | +8.28 (0.63) | -0.48 (0.53) | -5.87 (0.38) |
| 2025 | +27.21 (0.81) | +5.72 (0.64) | -2.57 (0.53) | -6.46 (0.42) | -4.53 (0.34) |
| pooled | +201.86 (0.84) | +60.06 (0.70) | -4.54 (0.58) | -36.22 (0.46) | -44.50 (0.35) |

## (c) Coin per year, mix% (win) — books + rungs entering that year

| year | BTC | ETH | SOL | BNB | XRP |
|---|---|---|---|---|---|
| 2021 | +6.22 (0.61) | +6.26 (0.60) | +12.76 (0.67) | +4.16 (0.57) | +4.00 (0.63) |
| 2022 | +8.98 (0.63) | +5.25 (0.65) | +6.70 (0.69) | -0.02 (0.63) | +20.10 (0.71) |
| 2023 | +14.17 (0.68) | +11.06 (0.68) | +20.06 (0.72) | +5.43 (0.68) | -3.51 (0.71) |
| 2024 | +18.15 (0.64) | +16.44 (0.67) | +16.98 (0.68) | +12.06 (0.66) | +54.67 (0.72) |
| 2025 | +0.66 (0.57) | +8.50 (0.62) | +8.71 (0.64) | +17.71 (0.65) | +11.82 (0.67) |
| pooled | +48.16 (0.62) | +47.51 (0.64) | +65.20 (0.68) | +39.33 (0.64) | +87.07 (0.69) |

## (d) Dip exit kind per year (n | mix%)

| year | rung_tp (win 1.0) | rung_sl (win 0.0) | rung_timeout (win ~0.41) |
|---|---|---|---|
| 2021 | 1856 \| +86.01 | 208 \| -27.27 | 2045 \| -30.84 |
| 2022 | 2130 \| +80.46 | 242 \| -35.56 | 1688 \| -24.85 |
| 2023 | 2438 \| +93.20 | 287 \| -52.61 | 1820 \| -11.78 |
| 2024 | 2090 \| +111.10 | 50 \| -9.22 | 1806 \| -21.36 |
| 2025 | 2247 \| +55.80 | 137 \| -14.37 | 2345 \| -22.08 |
| pooled | 10761 \| +426.57 | 924 \| -139.02 | 9704 \| -110.90 |

## (e) Agent TP choice per year (n | mix% | win)

| year | 0.5 | 1.0 | 1.5 |
|---|---|---|---|
| 2021 | 15 \| +0.15 \| 0.80 | 2745 \| +37.17 \| 0.70 | 1349 \| -9.41 \| 0.52 |
| 2022 | 32 \| -0.24 \| 0.75 | 3408 \| +23.73 \| 0.72 | 620 \| -3.45 \| 0.55 |
| 2023 | 56 \| -0.79 \| 0.68 | 2942 \| +24.03 \| 0.77 | 1547 \| +5.57 \| 0.66 |
| 2024 | 48 \| -0.48 \| 0.75 | 2933 \| +68.54 \| 0.76 | 965 \| +12.46 \| 0.62 |
| 2025 | 269 \| +0.54 \| 0.90 | 3308 \| +18.80 \| 0.70 | 1152 \| +0.02 \| 0.46 |
| pooled | 420 \| -0.81 \| 0.84 | 15336 \| +172.27 \| 0.73 | 5633 \| +5.19 \| 0.57 |

## Drawdown episodes: who carries them (realized mix% and share of window net)

| episode (mixed DD 4h/1m) | window realized mix% | book long (share) | book short (share) | dip (share) |
|---|---|---|---|---|
| 2023-04-17->06-15 (15.3/16.2) | -9.94 | -2.57 (25.8%) | +0.76 (-7.7%) | -8.13 (81.8%) |
| 2023-07-14->10-02 (13.3/13.7) | -7.10 | -0.87 (12.2%) | -4.07 (57.3%) | -2.17 (30.5%) |
| 2024-01-03 11:00->16:00 (14.8/16.9) | -15.55 | -0.91 (5.9%) | 0.00 (—) | -14.64 (94.1%) |
| 2024-06-07->07-16 (11.8/15.1) | -6.78 | +0.22 (-3.3%) | -3.78 (55.7%) | -3.23 (47.6%) |
| 2025-10-07->10-17 (11.7/12.8) | -6.40 | -1.98 (30.9%) | +1.30 (-20.4%) | -5.72 (89.5%) |

Bucket detail per episode (share of window net; + = carries loss, - = offsets it):

- By dip exit: stops always exceed the window net (shares 109/128/102/173/120%) with
  TPs offsetting (-142/-111/-7/-137/-112%); timeouts add 95/32/0/11/82%.
  Crash window 2024-01-03: 67 stops (-15.84 mix%) vs 30 TPs (+1.15).
- By depth: slow episodes are carried by deep rungs (4.0+5.0 shares ~42+46%,
  26+26%, 30+39%, 55+31% in the four slow windows; 2.5 GAINS in 4 of 5:
  -41/-42/-36/-45% i.e. offsets). The flash is depth-blind and SAVE-blind:
  2.5/3.0/3.5/4.0/5.0 = -2.7/-3.2/-3.0/-2.5/-3.2 mix% (17/21/20/16/20%).
- By coin: the carrier rotates — BNB -8.36 (84%) in 2023-04, mixed in 2023-07,
  BTC -5.39 (35%) led but ALL coins bled in the flash, XRP -10.84 (160%) in
  2024-06 with everything else offsetting, BTC -4.88 (76%) in 2025-10.
- By TP choice: 1.0 carries volume share (57/11/60/-28/86%) but that is where its
  return lives too; 1.5 carries 21/20/34/76/3% while earning ~0 pooled; 0.5 is
  negligible (420 rungs, -0.81 pooled).

## Plain paragraph
The five-year return is earned by dip take-profits (+426.6 mix% additive, win 1.0 by
construction) concentrated in shallow 2.5σ rungs (+201.9, win 0.84) plus 3.0σ (+60.1,
win 0.70), with the agent's TP=1.0σ choice holding essentially all of it (+172.3 of
+176.6 dip; TP=1.5 earns +5.2 on 5,633 rungs, TP=0.5 is 420 rungs of noise); books add
about a third of the additive total (longs +101.3 on 2,382 episodes at 0.52 win and
+0.014 per gross — the best per-notional bucket — shorts +9.3 at 0.51), with XRP
(+87.1) and SOL (+65.2) the best coins and every coin positive pooled. The drawdown is
the mirror image carried by the dip sleeve (31-94% of each window's realized net):
rung stops print more than 100% of every window's net with TPs as the only offset,
deep 4.0/5.0σ rungs both lose money in EVERY year (-36.2/-44.5 pooled) AND carry
~50-90% of each slow drawdown while shallow 2.5σ gains inside 4 of 5 episodes, so per
unit of DD carried the shallow/TP-1.0/book-long buckets are the only ones with a
positive return and the deep/TP-1.5/timeout buckets take pain without pay; the gate
flash (2024-01-03, dip 94%, no book short on) is the exception where breadth, not
depth, kills — every depth and every coin stops together, consistent with
oc_ddanat4p's same-bar cascade finding.

## Verdict
VERDICT (descriptive, no selection): shallow dips + TPs + book longs earn the return
while deep rungs + stops + timeouts carry the drawdown, and the gate episode is a
depth-blind all-coin dip stop cascade.

## Caveats
Additive `pnl_mix` sums to +287.3 mix% vs the true compounded 5y net +2533.9%
(26.34x): the gap is compounding (yearly additive 33/41/47/118/47 vs geometric
39.7/~51/~72/~257/~80 from R=2.83/3.51/4.67/11.27/5.06), excluded book funding, 18
still-open book positions, and exit-time (not marked) DD windowing. FIFO rung pairing
matches oc_kpi/oc_ddanat4p but same-symbol concurrent rungs exiting out of order can
misattribute depth/TP (max fill/exit weight diff 0.40 recorded in results.json);
sleeve/coin/exit-kind totals are unaffected. Checks: 0 unpaired exits, 0 open rungs,
18 open books (excluded, as oc_kpi), 0 unknown TP joins.
