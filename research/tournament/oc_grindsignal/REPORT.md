# oc_grindsignal REPORT — causal pre-signal diagnostic for the G2 grind (2026-10-06; PLAN pre-registered before any outcome)

DIAGNOSTIC (no PROMISING rule; the assignment's default 4-of-5/LOYO rule does
not apply: 4 episodes, no year folds, no signed pre-expectation). Episodes:
E0 grind gate 2023-04-17 00:00 (= oc_ddanat_g2 reset_episodes[0].peak) and
E1 2023-07-14 04:00 / E2 2024-01-03 11:00 (flash crash) / E3 2025-10-07 14:00
(oc_ddanat4p mix_episodes.json reset peaks; E0 matches G2's peak exactly).
30 stats, each strictly causal (hourly closes bar-end <= T; funding
settlements in [T-7d,T), exactly 21 else NaN; strategy events t in (T-30d,T];
book episodes = v213 loop, maker 0.0002/taker 0.00055). Percentile vs all
valid 4h grid bars 2021-09-24..2026-09-24 (n=10956; funding valid ~10726-10818,
dip-TP/book-win valid ~10790-10795, rest 10956). Extreme = pct <= 5 / >= 95;
hypothesis iff >= 3 of 4 episodes extreme on the same tail. One process;
hourly + settled funding + oc_kpi events only. Repro:
research/tournament/oc_grindsignal/{PLAN.md,analyze_grindsignal.py,
results.json}. All five years are research data; findings need prospective
validation. No post-hoc change to definitions or the hypothesis rule.

## (1) Grind-window start E0: value / percentile (bps where noted)

fund7 (per-8h bps): BTC 0.70/65.5, ETH 0.69/64.5, SOL 1.01/85.4, BNB 0.59/89.8,
XRP 0.51/53.1, mkt 0.70/79.3. rv30 (ann.): BTC 0.49/53.1, ETH 0.53/28.0,
SOL 0.82/39.9, BNB 0.43/26.5, XRP 0.88/70.8, mkt 0.63/46.4. d_rv30: BTC
-0.12/24.0, ETH -0.07/37.7, SOL -0.16/33.4, BNB -0.13/33.8, XRP +0.31/85.8,
mkt -0.03/50.4. trend90 (log): BTC +0.36/84.6, ETH +0.29/78.5, SOL +0.07/58.2,
BNB +0.15/69.3, XRP +0.30/84.7, mkt +0.24/73.0. breadth 1.00/100.0.
dip_fill30 7.50 fills/day/37.3. dip_tp_share30 0.618/87.6.
book_win30 0.537/56.9. bnb_rs30 -0.074/24.1. bnb_rs90 -0.206/16.3.
Nothing at E0 is extreme except breadth (all 5 majors above their 200d mean).
Vol is mid-range and mostly falling, funding mildly above median, book win
rate dead median — no fear, no crowding, no washout before the grind.

## (2) Same percentiles at E1 / E2 / E3 (value omitted, see results.json)

fund7_mkt: 10.4 / 96.8 / 70.8 (E2 crowded longs; E1 soft). rv30_mkt: 63.7 /
52.2 / 8.4 (E3 starts from very low vol). d_rv30_mkt: 81.0 / 52.9 / 32.7.
trend90_mkt: 57.8 / 96.0 / 86.5 (E2/E3 extended). breadth: 76.7 / 100.0 /
100.0. dip_fill30: 68.0 / 63.7 / 28.3. dip_tp_share30: 87.9 / 72.4 / 87.5.
book_win30: 80.8 / 78.6 / 48.8. bnb_rs30: 6.5 / 98.6 / 99.4. bnb_rs90: 10.1 /
40.8 / 99.7. Per-coin extremes all sit in E2 alone (funding 98.7-99.0 hi on
BTC/ETH/SOL/XRP with BNB 1.5 lo; BTC trend90 94.9 just short) — a crowded-long
top immediately before a one-bar crash, n_extreme = 1 each, not repeated.

## (3) Cross-episode count + hypotheses for a later rule only

Only ONE stat meets the pre-fixed >=3-of-4 same-tail bar: breadth HIGH
(E0 100.0, E1 76.7, E2 100.0, E3 100.0; n_extreme = 3, tail hi). Breadth 1.0
holds on 23.3% of grid bars, so 3/4 episodes at the maximum (4th at 0.8, same
direction; binomial p ≈ 4% under independence — suggestive, not proof, and
one of 30 stats tested). No funding, vol, vol-change, trend, dip-fill, dip-TP,
book-win, or BNB-RS stat is extreme in more than 2 episodes on one tail
(bnb_rs30 hi in E2/E3 only; dip_tp_share30 sits at 87-88th pct in E0/E1/E3 —
below the bar, same hot-TP direction, reported as an observation only).
A later pre-registered rule would read: when breadth == 1.0 (all majors above
their 200d mean, optionally with dip TP-share running hot), trim book-long
and dip-hold exposure — the grind, the flash crash, and E3 all started from
fully extended bull-market tops, never from weakness.

## One-line verdict

VERDICT (hypothesis only): the G2 grind had no fear/crowding/washout
pre-signal — the sole repeat extreme across DD starts is breadth pinned at
1.0 (E0/E2/E3 max, E1 0.8), i.e. drawdowns begin from fully extended tops, so
any future gate must be conditioned on over-extension, not on stress.
