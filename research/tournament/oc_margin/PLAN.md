# oc_margin PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

RISK / ops report (no selection rule, no PROMISING verdict).
Question: deployment config R2B1D17BFG2 (= registry v421: R2B1D17BF + dip
gross-notional cap G = 2.0) on Bybit USDT perps, cross margin, Hedge Mode —
what leverage setting never blocks an order, how far is liquidation, and would
the instant -10% / -20% all-coin gaps of oc_gapstress liquidate the account?

## Inputs (fixed here, read-only)
- research/tournament/oc_kpi_g2/events_s{0..3}.parquet — engine_user events for
  the exact v421 R2B1D17BFG2 s=0..3 replicas (book_fill/add/reduce/partial/
  close/stop/tp with signed `weight`, rung_fill/tp/sl/timeout with `weight`).
- research/tournament/oc_kpi_g2/barsum_s{0..3}.parquet — per 4h bar end: t,
  n_book, gross_book, equity (phase sub-account equity).
- research/tournament/ext/hourly_ext.parquet — hourly marks for the 5 majors.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides the
  old RULES.md hidden-year cut; all five years are research data; findings need
  prospective validation). No refit, no selection, no tuning.
- LIGHT job: one process, no 1m data, peak RAM < 1 GB.

## Exact causal position definitions (fixed; same as oc_gapstress C1-C3)
- Engine semantics (verified in engine_user/engine_user.py before writing this
  plan): book quantities q = w/o1 with w = weight fraction of bar-start equity;
  every book_* event `weight` is a SIGNED delta of that fraction
  (book_fill = dw, book_add = +dq*px/prev_eq, book_reduce/partial/close/stop/tp
  = -dq*px/prev_eq). Dip rung_fill `weight` = rn (fraction of start equity,
  always long); rung exit `weight` = same rn.
- Open book fraction per coin at minute T: engine q-units cumulated per coin
  (book_fill qk = weight/limit-price; book_add/reduce/partial qk =
  weight*prev_eq/price; book_stop/tp/close zero the coin's qty), times the
  hourly mark, times bar-start equity / indexed end equity. Open dip fraction
  per coin: FIFO fill quantities (qk = weight/limit-price, exits pop oldest)
  marked the same way. Post-event state at each sample minute.
- Equity at T = barsum indexed equity (end of the containing bar).
- Hedge-Mode convention (fixed): per coin, book_net and dip_net are kept
  separate; signed net S = book_net + dip_net (PnL on net — a book short hedges
  a dip long on the same coin); gross G = |book_net| + |dip_net| summed over
  coins (margin on BOTH sides — netting per coin would understate MM when
  hedged). Cross-symbol: no offset.
- Check: reconstructed |book| gross vs barsum gross_book at bar ends
  (median/max abs diff reported).

## Sampling (fixed; same as oc_gapstress)
- Per phase: distinct event-minute timestamps (any book/dip delta) UNION 4h
  bar ends, restricted to minutes where book or dip gross > 0 (open minutes).
- 4-phase mix: union of the four phases' sample times; at each, phase states
  and equities are ffill'd; mix equity = mean of phase equities (1/4 capital
  each); mix S/G = equity-weighted mean of phase S/G.

## Margin math (fixed)
- Bybit tier assumption (fixed; no tier table found in the repo — stating the
  assumption): all five majors inside tier-1 for an account < 10k USDT
  (max combined notional here ~3-4x equity ≈ 30-70k USDT, far below any tier-1
  value limit, e.g. BTC ~2M USDT on Bybit docs). Flat MMR = 0.005 (0.5%)
  on gross notional. Engine's 1% MM check is the conservative side row, not
  used here. Hedge Mode, cross margin, one-way fee ignored for margin.
- Per open minute, fractions of that minute's equity:
  G = gross notional / equity; S = signed net / equity (long-positive).
  IM_L = G / L for L in (3, 5, 10, 20) (Bybit IM = notional / leverage).
  MM = MMR * G with MMR = 0.005.
  free_L = 1 - IM_L (share of equity not locked as initial margin).
  blocked_L = IM_L > 0.95 (order blocked; 95% budget rule from AGENTS.md).
- Liquidation distance (all positions long-weighted, worst case): treat the
  whole gross G as adverse net. After a uniform adverse move of fraction d
  (0<d<1), equity E' = E*(1-G*d), MM' = MMR*G*E*(1-d). Liquidation when
  E' <= MM': d_liq = (1-MMR*G) / (G*(1-MMR)) (exact with shrinking MM;
  ≈ 1/G - MMR). Grounded in engine check `1+path.min() < MMR*gross` (MMR=0.01
  there, no (1-d) shrinkage — more conservative; documented as side note).
  d_liq <= 0 means already below MM (never happens here; reported if so).
  d_liq is INDEPENDENT of L (cross margin) — it is reported "for" the minimum
  setting on the same samples.
- Gap liquidation (same minutes): DOWN-gap loss_frac = S*g + TAKER*G*(1-g),
  TAKER = 0.00055, g in (0.10, 0.20) (same formula as oc_gapstress; S may be
  < G when hedged/shorted — that is the realised gap loss, while d_liq above
  is the long-weighted worst case). Liquidated by the gap iff
  loss_frac >= 1 - MMR*G*(1-g) (equivalently g >= d_liq when S == G).

## Outputs (fixed)
- Script compute_margin.py (one process, no 1m data, RAM < 1 GB): per phase
  s=0..3 and mix: n samples, open/live minutes, coverage; G distribution
  (median/p99/max, minute-weighted); per L: max IM, share blocked (of open
  min and of live min); minimum L with zero blocked minutes (IM <= 95%
  everywhere); for that L: free-buffer distribution (median/p1/min) and
  d_liq distribution (median/p1/min, minute-weighted); gap -10%/-20%:
  share of open minutes liquidated + worst-10 timestamps (loss%, G, d_liq,
  equity); recon check vs barsum; build-integrity counters.
- results.json (all numbers + checks + config + tier assumption), REPORT.md
  (tables, plain language, one-line descriptive summary, plain Vietnamese
  runbook recommendation; no PROMISING verdict — RISK/ops report, no rule).
- Test tests/test_oc_margin.py (presence, plan-predates-results, no data >=
  2026-09-24, reconstruction check, margin-math spot checks, JSON/REPORT
  consistency). No commits; no edits outside research/tournament/oc_margin/
  + the test file.
