# oc_vipfees PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

REPORTING task only (no selection rule, no PROMISING verdict, no hypothesis test).
Question: the gate cost model prices Bybit VIP0 fees (maker 0.02 %, taker
0.055 %). How much monthly return would the deployment configuration
R2B1D17BFG2 (oc_kpi_g2) gain under Bybit VIP1 / VIP2 fees, and what monthly
volume is needed to reach each tier at 5k / 10k / 50k USDT equity?

## Inputs (fixed here, read-only)
- research/tournament/oc_kpi_g2/events_s{0..3}.parquet — every fill/exit of the
  exact v421 R2B1D17BFG2 s=0..3 replicas (book_fill/add/reduce/partial/
  close/stop/tp, rung_fill/tp/sl/timeout, each with signed `weight`).
- research/tournament/oc_kpi_g2/barsum_s{0..3}.parquet — per holding-bar start:
  t, n_book, gross_book, equity (phase sub-account equity, starts 1.0).
- research/tournament/oc_kpi_g2/results_equity.json — continuous 4-phase mix
  monthly returns (61 months, 2021-09 partial .. 2026-09 partial) and 5y net.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides the
  old RULES.md hidden-year cut; all five years are research data; findings need
  prospective validation). No refit, no selection, no tuning. LIGHT job: one
  process, RAM < 1 GB, no 1m data (engine already aggregated the fills).

## Exact causal fee-leg definitions (fixed; verified BEFORE outcomes)
- Engine fee semantics (backend/history_tm.py ll.117-156 + oc_kpi_g2/compute_kpi.py):
  MAKER legs: book_fill, book_add, book_reduce, book_partial, book_tp,
  book_close, rung_fill, rung_tp.
  TAKER legs: book_stop, rung_sl, rung_timeout.
  Ignored (no fill, no fee): order_issue/expire/cancel, sl_move.
- Notional: event `|weight|` = notional as a fraction of the phase
  sub-account's contemporary equity (book_fill mean |w| 0.079, rung_fill mean
  0.121; sub equity 1.0 -> ~56). Exit-price vs fill-price drift is ignored
  (rung nets are +/- a few %; second-order). Funding is identical across tiers
  and excluded.
- Fee schedules (no repo doc lists Bybit VIP tiers; per the assignment these
  are ASSUMED values, cross-checked against Bybit's current public derivatives
  schedule 2026-10-06: VIP0 maker 0.0200 % / taker 0.0550 % = gate;
  VIP1 maker 0.0180 % / taker 0.0400 %; VIP2 maker 0.0160 % / taker 0.0375 %).
  Tier volume thresholds (public Bybit derivatives 30d volume, assumed):
  VIP1 >= 10M USDT, VIP2 >= 25M USDT.

## Decision rule / computation (fixed; additive per-bar approximation)
- Per shift s and holding bar b, fee saving in sub-equity fractions:
  D_s(b) = sum_maker |w|*(0.0002-m_new) + sum_taker |w|*(0.00055-t_new).
- Mix saving fraction of contemporary mix equity:
  m(b) = sum_s D_s(b)*eq_s(b) / sum_s eq_s(b), eq from barsum.
- Monthly saving S(M) = sum_{b in M} m(b) (bar equity ~= month-start equity;
  error = saving x intra-month return, second-order). New monthly return:
  1+R_new(M) = 1+R_old(M) + S(M) (gross path unchanged, only fees repriced).
  Recompound: 5y net, 5y monthly geo mean over the 60 full months
  2021-10..2026-09, per-anchor-year monthly geo means, per-year mean S(M).
- Volume: mix volume fraction v(b) = sum_s V_s(b)*eq_s(b)/sum_s eq_s(b),
  V_s(b) = sum_legs |w| (each fill counted once at its notional). Mean monthly
  turnover tau = mean_M sum_{b in M} v(b) (x contemporary equity / month).
  USD volume at account equity E (4 phases x E/4): Vol(E) = tau*E.
  Required equity per tier: E_req = threshold/tau. Report Vol at E =
  5k/10k/50k USDT vs 10M/25M thresholds, plus fee USD saved/month = sbar*E.
- Win rates: invariant to first order; count rung/book trades that would flip
  sign under repricing (rung delta_ret = Dmaker+Dexit on fill notional; book
  episode fee delta from its legs) and report the count only.
- Drawdown: fee saving is non-negative on every bar, so the equity path is
  pointwise >= the VIP0 path; DD reported as unchanged (no recompute).

## Outputs (fixed)
- compute_vipfees.py (one process, events+barsum+results_equity only),
  results.json (all numbers + checks + assumed schedules), REPORT.md (tables,
  plain language, one-line descriptive summary; no verdict),
  tests/test_tournament_oc_vipfees.py. No commits; no edits outside
  research/tournament/oc_vipfees/ + the test file.
