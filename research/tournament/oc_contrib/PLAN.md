# oc_contrib PLAN (pre-registered BEFORE computing attribution, 2026-10-06)

DIAGNOSTIC only. No hypothesis to confirm, no selection, no PROMISING rule,
no verdict on strategy quality. Goal: attribute the 5-year R2B1D17BF return
and the drawdown episodes to buckets so the leader sees where alpha and risk sit.

## Inputs (fixed, read-only)
- `research/tournament/oc_kpi/events_s{0..3}.parquet` + `barsum_s{0..3}.parquet`
  (R2B1D17BF engine replicas, 4 phases/shifts, live 2021-09-24..2026-09-23+shift).
- `research/tournament/oc_kpi/results.json` (monthly/yearly/DD/win-rate reference).
- `research/tournament/oc_ddanat4p/mix_episodes.json` (episode windows only).
- `research/parallel/rounds/parallel-20260906-r2/v376/tables_hidden/r2_table_s{shift}.parquet`
  (agent TP choice 0.5/1.0/1.5 per (T,sym,rung_idx); T = 4h bar-start grid of that shift).
- Market data read: only the above parquet/json files (all five years are research
  data per assignment; findings need prospective validation). No 1m data.
- Pre-PLAN inspection was schema-only (event kinds, columns, depth values,
  R2 table grid); no attribution outcome was computed before this PLAN.

## Exact causal definitions (fixed)
- Rung pairing: FIFO per symbol over sorted `t`: `rung_fill` -> first later
  `rung_sl|rung_tp|rung_timeout` (copy of oc_kpi `pair_rungs`). Each pair gives
  `fill_t, exit_t, symbol, depth=float(fill.rung), exit=exit kind,
  weight=float(fill.weight), ret=float(exit.ret)`.
  `pnl = weight*ret` (fraction of sub-account bar-start equity; engine `ret` is
  already net of rung maker/taker fees and timeout funding). `gross = weight`.
  `win = ret > 0`. Unpaired exits counted as check (expected 0).
- Book episodes: exact copy of oc_kpi `book_episodes` (v213 loop): `book_fill`
  opens (side=+1 buy/-1 sell; `cost=|weight|` in equity fraction),
  `book_add`/`book_reduce|book_partial` adjust, `book_stop|book_tp|book_close`
  closes with maker entries/TP/close (0.0002), taker stops (0.00055), funding
  excluded. Per episode: `net_ret=(side*(proceeds-cost)-fees)/cost`,
  `pnl_eq=side*(proceeds-cost)-fees` (equity fraction), `gross=cost_total`
  (initial cost + adds), `win=net_ret>0`. Sleeve split: `book long` = episode
  side +1, `book short` = side -1. Exit kind of book close recorded but the
  (a)-sleeve split is long/short/dip only.
- Year bucket = ENTRY time in anchor year `[A_k, A_k+365d)`, A=(2021..2025)-09-24,
  A_5=2026-09-24 (same as oc_kpi). Pooled over the 4 phase sub-accounts
  (counts summed; win rates pooled over trades).
- Per bucket per year: `pnl_sub` = sum(pnl) over trades entering that year
  (fraction of sub-account equity, reported x100 as "sub-account-summed %");
  `pnl_mix = pnl_sub/4` (mix holds 1/4 capital per phase under the reset metric;
  reported x100 as "% of mix equity", additive approximation — compounding gap
  vs `results.json` 5y net is stated, not hidden). `n`, `win`, `pnl_per_gross =
  sum(pnl)/sum(gross)` (return per unit notional; book gross=cost_total).
- Buckets: (a) sleeve {book_long, book_short, dip}; (b) dip depth {2.5,3.0,3.5,
  4.0,5.0} (float(fill.rung)); (c) coin {BTC,ETH,SOL,BNB,XRP}USDT; (d) dip exit
  {rung_tp, rung_sl, rung_timeout} — assignment's "close-stop/backstop" are NOT
  distinguished in `events` (both log as `rung_sl` in this engine; reported as
  one combined stop bucket with this caveat); (e) agent TP choice {0.5,1.0,1.5}:
  join each fill to its shift R2 table on `sym`, `rung_idx={2.5:0,3.0:1,3.5:2,
  4.0:3,5.0:4}`, `T=max table T <= fill_t` (merge_asof backward per shift);
  unmatched fills counted (expected 0) and put in `"unknown"`.
- Drawdown episodes: union of distinct (peak,trough] windows in
  `mix_episodes.json` `full_episodes`+`reset_episodes` = 5 windows
  (2023-04-17->2023-06-15, 2023-07-14->2023-10-02, 2024-01-03 11:00->16:00,
  2024-06-07->2024-07-16, 2025-10-07->2025-10-17; 4h-close peak/trough on the
  mixed path). Bucket DD contribution = sum(pnl) of trades with
  `exit_t in (peak, trough]` (realized only; open-position marks and funding
  excluded), in mix-equity % (`pnl_sub/4*100`); share = bucket window pnl /
  total window pnl over all buckets (shares sum to 100% of realized window P&L;
  also reported against the episode's mixed DD magnitude with the
  realized-vs-marked caveat). Episode windows use the mixed-path clock directly
  on sub-account event times (phases share UTC; shift offsets are hours).
- Checks: unpaired rung exits; unmatched TP joins; open book positions at live
  end (excluded, as oc_kpi); per-year entry coverage sums to pooled totals;
  attribution `sum(pnl_mix)` vs oc_kpi 5y economics stated with funding/marks gap.

## Decision rule
None (diagnostic). No PROMISING/REJECT label, no parameter choice, no tuning.

## Resources
LIGHT: one process, RAM < 1 GB (events ~80k rows + R2 tables streamed per shift),
no 1m data, runtime < 10 min.

## Outputs (fixed)
- `research/tournament/oc_contrib/attribute.py` (single script),
  `results.json` (all tables + checks + methods note),
  `REPORT.md` (tables + one plain paragraph: which buckets earn, which carry DD,
  return per unit of DD contribution + one-line descriptive verdict; no selection).
- Test `tests/test_oc_contrib.py` (pairing math, depth/TP join, year bucketing,
  DD windowing on synthetic events; results.json schema/consistency).
