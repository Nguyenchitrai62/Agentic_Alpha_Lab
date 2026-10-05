# oc_bookic — PLAN (pre-registered BEFORE any outcome is computed)

## Hypothesis

The deployed BOT book (`forward_v205.research_books_d2`) earns its gross P&L
unevenly: shorts and/or one regime (BTC-below-trend, high-vol) and/or one or
two coins carry disproportionate losses, while longs in uptrends pay for them.
Finding the loss carrier tells the leader where a gate/hedge rule could help.

## Inputs (read-only, never edited)

- Books: `research_books_d2` rebuilt EXACTLY as `scripts/forward_v205.py`:
  `o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2` with A=`member_A_O1_orders`,
  Aq=`member_Aq_O1_orders`, B=`member_B_tv`, Bq=`member_Bq_tv`;
  `d2 = 0.8*o1 + 0.2*(D+Dq)/2` with D=`members_v154[D]`, Dq=`members_quarterly_D`;
  union index, missing → 0.0. All from `artifacts/research/engine_real/`.
- Opens: `artifacts/research/engine_real/opens_v154.parquet`
  (the `eu.er.v154_books()` 4h opens).
- Symbols: BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides the
  tournament-harness dev cutoff; all five years are research data, findings
  still need prospective validation).

## Exact definitions (fixed before seeing numbers)

- Grid: inner join of books index with opens index, sorted 4h grid.
  Weight `w[t]` is known at the close of bar `t`.
- Next-bar return: `r[t] = open[t+1]/open[t] - 1` (simple, per coin).
  Vectorised gross P&L (no costs): `pnl[t] = w[t] * r[t]`.
  The last grid bar has no forward return and is dropped.
- 42-bar forward return: `R42[t] = open[t+42]/open[t] - 1` (7 days).
- Anchor years: `Y_k = [A_k, A_k + 365d)` on bar `open_time`,
  `A_k = 2021-09-24, ..., 2025-09-24` (5 years).
- IC: per (year, coin), Spearman corr of `(w[t], R42[t])` over bars `t` in the
  year with `R42` available (last 42 bars of the full sample excluded).
  Report `n` alongside every IC.
- Leg split: long leg `pnl` where `w[t] > 0`, short leg where `w[t] < 0`
  (flat `w == 0` contributes 0). Sums per (year, coin).
- Trend regime (causal, BTC 4h opens from 2017 so all scored years have full
  windows): `MA1200[t] = mean(BTC_open[t-1199..t])`; above iff
  `BTC_open[t] >= MA1200[t]`, else below.
- Vol regime (causal): `sig[t] = std` of BTC 4h log-returns over trailing
  180 bars ending at `t` (≈30d); `med[t] = median` of `sig` over trailing
  2190 values ending at `t` (≈1y, min_periods 1000); high-vol iff
  `sig[t] >= med[t]`, else low-vol. Same BTC regime labels applied to every
  coin's P&L split.
- Drawdown windows (UTC, bar `open_time >= start 00:00` and
  `< end 00:00 + 1 day`): W1 `2022-07-20..2022-11-10`,
  W2 `2023-04-17..2023-06-14`, W3 `2022-01-13..2022-01-22`,
  W4 `2024-01-03` (single day = 6 bars). P&L = sum of `pnl[t]` in window,
  per coin and summed over the 5 coins.
- Units: weight×return per-unit-equity gross, BEFORE vol target, governor,
  fees, funding, and the dip sleeve. This diagnoses the book signal, not the
  engine net.

## Decision (verdict) rule — fixed now

The loss carrier = the (leg × regime × coin) grouping with the largest
negative contribution to total 5-year gross P&L. The verdict names it from
the tables. At most 2 follow-up rules may be PROPOSED (never tested here),
each with an economic reason.

## Resources / constraints

- Write ONLY to `research/tournament/oc_bookic/` (+ `tests/test_oc_bookic.py`).
  No commits, no edits outside these paths.
- One process; only 4h opens + book parquets are loaded (small frames,
  RAM ≪ 1.5 GB). No 1m data is needed for this vectorised diagnostic, so the
  1m-handling constraint is vacuous here.

## Post-hoc log (allowed by VF_COMMON; definition fix, before REPORT)

- Anchor years use partition boundaries `[A_k, A_{k+1})` for the first four
  years and `[A_4, A_4 + 365d)` for the last, instead of literal `+365d` for
  all: 2023-09-24..2024-09-24 spans Feb-29 2024 (366 days), so literal +365d
  would orphan the 6 bars of 2024-09-23..24 from every year while the 5y
  total still includes them. No outcome was inspected before this fix beyond
  a failing aggregation test.

## Outputs

- `results.json` (per-year-per-coin IC + n, pnl total/long/short,
  trend-regime split, vol-regime split, window P&L, coverage/mean-|w|,
  5-year totals, definitions hash).
- `REPORT.md` (tables + one-line verdict + ≤2 proposed rules).
