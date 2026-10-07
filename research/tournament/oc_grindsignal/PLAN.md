# oc_grindsignal PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

DIAGNOSTIC only (no PROMISING rule, no verdict threshold). Question (assignment):
research/tournament/oc_ddanat_g2 finds the deployment config's gate DD is a
synchronous 59-day grind 2023-04-17 -> 2023-06-15 (book longs + dip
stops/timeouts, BNB-led). Was there a CAUSAL pre-signal visible at the window
start or over the preceding 30 days? Compare each candidate statistic's value
at this window's start with its distribution over all 4h bars of the 5 years
(percentile), and with the starts of the other big DD episodes
(research/tournament/oc_ddanat4p mix_episodes.json). Report which (if any)
statistic sat in an extreme percentile at the start of most DD episodes -- as
hypotheses for a later pre-registered rule only.

## Episodes (fixed here, read-only)

- E0 (grind gate): 2023-04-17 00:00 UTC (= oc_ddanat_g2 reset_episodes[0].peak).
- E1..E3 (other big DD starts, from oc_ddanat4p mix_episodes.json
  reset_episodes[1..3].peak): 2023-07-14 04:00, 2024-01-03 11:00 (flash crash),
  2025-10-07 14:00 UTC. E0 is also reset_episodes[0].peak there, so the set is
  the 4 reset_episodes peaks of oc_ddanat4p.
- All five years are research data (assignment overrides the old RULES.md
  hidden-year cut; market data read only to 2026-09-24 00:00 UTC). Findings
  need prospective validation. No refit, no selection, no tuning.

## Statistic set S(T) (exact, causal: ONLY data strictly before T)

T is an episode peak (window start). "Strictly before T" means:
- hourly bar with open time t contributes its close iff t + 1h <= T
  (close known at bar end); equivalently last usable hourly open is <= T - 1h.
- funding settlement with calc_time c contributes iff c < T.
- strategy event with time t contributes iff t <= T (events are timestamped at
  the minute they occur; the start instant T = 00:00/04:00/11:00/14:00 is after
  that minute's close, so t <= T is known at T; the script ALSO verifies
  t < T + 1min never changes the counts).
Hourly source: research/tournament/ext/hourly_ext.parquet (hourly OHLC 35
coins, 2020-08-01 .. 2026-09-23 23:00 open). Funding source:
data/raw/binance_premium_20260928/{BTC,ETH,SOL,BNB,XRP}USDT_funding.parquet
(settled funding only; no premium_1m file is loaded). Strategy sources:
research/tournament/oc_kpi/events_s{0..3}.parquet (deployment-pick BF wiring
replicas; pooled over the 4 phase sub-accounts; rung_fill / rung_sl|tp|timeout
/ book_fill|add|reduce|partial|stop|tp|close with columns t, symbol, kind,
side, price, weight, ret). No 1m data of any kind is loaded.

Per-coin c in {BTC,ETH,SOL,BNB,XRP}USDT (+ mkt = equal-weight mean of the 5
per-coin values where defined):
1. fund7_c(T), fund7_mkt(T): mean last_funding_rate over settlements with
   calc_time in [T-7d, T). Per-coin NaN unless exactly 21 settlements present
   (same rule as oc_fundregime); mkt NaN unless all 5 coins non-NaN. Units:
   rate per 8h settlement (tables show x1e4 = bps).
2. rv30_c(T), rv30_mkt(T): realised vol = std of hourly log returns over the
   720 hourly bars ending at T (bar-ends in (T-30d, T]), x sqrt(24*365)
   (annualised). NaN unless all 720 closes present.
3. d_rv30_c(T), d_rv30_mkt(T): rv30(T) - rv30(T-30d). NaN if either end NaN.
4. trend90_c(T), trend90_mkt(T): log(C(T)/C(T-90d)), C(t) = last hourly close
   with bar-end <= t. NaN if either close missing.
5. breadth(T): share of the 5 majors with C(T) > mean of their hourly closes
   with bar-ends in [T-200d, T) (4800 bars; NaN for a coin unless all 4800
   present; breadth NaN unless all 5 coins valid). Range 0..1.
6. dip_fill30(T): count of pooled rung_fill events with t in (T-30d, T] / 30
   (fills/day). dip_tp_share30(T): TP exits / all exits among pooled
   rung_sl|rung_tp|rung_timeout events with t in (T-30d, T]; NaN if < 10 exits.
7. book_win30(T): win rate of book position episodes (EXACT v213/compute_kpi
   loop: book_fill opens, book_add increases, book_reduce|partial decreases,
   book_stop|tp|close closes; net = side*(proceeds-cost)-fees over cost, maker
   0.0002 entries/TP/close, taker 0.00055 stops, funding excluded; win =
   net > 0) with exit_t in (T-30d, T], pooled over s=0..3; NaN if < 10 exits.
   Episodes still open at T are ignored (no forward data).
8. bnb_rs30(T) = log(BNB(T)/BNB(T-30d)) - log(BTC(T)/BTC(T-30d));
   bnb_rs90(T) same over 90d. NaN if any of the 4 closes missing. (News-free
   BNB-vs-BTC relative-strength proxies.)
Total 30 series: fund7 x6, rv30 x6, d_rv30 x6, trend90 x6, breadth x1,
dip_fill30 x1, dip_tp_share30 x1, book_win30 x1, bnb_rs30 x1, bnb_rs90 x1.

## Background distribution + percentiles (fixed here)

- Grid G: 4h bar closes T_g in (2021-09-24 00:00, 2026-09-24 00:00] at
  00/04/08/12/16/20 UTC (5 full years; every statistic recomputed causally at
  each T_g with the same code as at episode starts).
- For each stat s with value v_e = s(E) at episode E: pct_e = 100 *
  mean(T_g in G, s valid: s(T_g) <= v_e). Extreme = pct <= 5 or pct >= 95.
- Cross-episode summary: for each stat, n_extreme = # of the 4 episodes with
  an extreme pct, and same-tail agreement (all extremes on the same side).
  A stat is listed as a hypothesis for a later rule ONLY if n_extreme >= 3
  with the same tail (pre-fixed; descriptive, not a PROMISING verdict).

## Decision / verdict rule

None (diagnostic). The assignment's default 4-of-5/LOYO PROMISING rule does
not apply (4 episodes, no year folds, no signed pre-expectation). REPORT.md
gives: (1) episode-start value + percentile table for the grind window E0;
(2) the same percentiles at E1..E3; (3) the n_extreme>=3 same-tail list as
hypotheses-only, each with its tail direction and a one-sentence sketch of
the rule that would have to be pre-registered later. One-line verdict names
which (if any) pre-signal stands out and which legs it would gate.

## Outputs (fixed)

research/tournament/oc_grindsignal/: PLAN.md (this file),
analyze_grindsignal.py (one process; hourly + funding + oc_kpi events only;
RAM < 1 GB; no premium_1m/intraday/1m token), results.json (episodes, per-stat
episode values + percentiles + valid-N, n_extreme table, checks), REPORT.md
(tables + one-line verdict; any post-hoc change logged). Test
tests/test_oc_grindsignal.py (files exist, PLAN predates results, funding and
hourly strictly-before-T, event t<=T, episode peaks match mix_episodes.json,
percentile recomputation on samples, no-1m token).
