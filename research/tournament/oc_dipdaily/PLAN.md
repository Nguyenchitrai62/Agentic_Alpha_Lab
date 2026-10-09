# oc_dipdaily PLAN (pre-registered BEFORE any outcome, 2026-10-08 — FROZEN)

Task: docs/opencode/OPENCODE_W_oc_dipdaily.md + docs/opencode/OPENCODE_W_COMMON_20261007.md
(+ AGENTS.md, OPENCODE_VF_COMMON.md). Write ONLY `research/tournament/oc_dipdaily/`
and `tests/test_oc_dipdaily.py`.

## Question
A SLOWER dip sleeve on the daily grid (big, rare flushes) next to G2, with G2's
mechanism. The 4h dip sleeve is the program's robust edge; a 1h sleeve failed
(oc_dipdip1h / oc_dip1h: small TPs vs 4-sigma stops, correlated with G2's
sell-offs). A daily-grid sleeve catches larger, rarer capitulations with wider
TPs; it may be less correlated with the 4h sleeve's losses and has fewer, larger
fills (fees matter less). Exactly TWO variants (pre-registered, no other rows;
any post-outcome change is a disclosed extra row, never a replacement).

## G2 parameters read from config (frozen here, before any outcome)
- Source: `backend/history_tm.py` KW_OVERRIDE["v321"] (R2 ladder
  2.5..5.0 sigma, close5 stop m_sleeve_sl=4.0 + backstop 8.0, budget 0.26),
  `research/tournament/oc_dipbe/be_core.py` (RUNGS/M_SL/BACKSTOP/TP constants),
  oc_dip1h/PLAN.md (frozen G2 size reading, adopted verbatim).
- RUNGS k = (2.5, 3.0, 3.5, 4.0, 5.0) sigma units (R2 deployed ladder).
- TP multiple = 1.0 sigma (engine_user m_sleeve_tp default; a standalone daily
  sleeve has no 4h-book context, so fixed 1.0).
- Stop depth = 4.0 sigma, TOUCH stop (market, taker), stop-first on a same-1m-bar
  tie. Disclosed simplification (same as oc_dip1h): G2's deployed stop is
  bot-watched 5m-close 4-sigma + 8-sigma native backstop; the assignment names
  one stop depth, so the literal 1m implementation is a touch stop at 4.0
  sigma, no backstop.
- G2 per-rung size_frac = (0.25/4/1.657) x kd(1.7) = 0.0641312 of equity
  (engine_user rung notional s*g*0.25/4/1.657 with D17 kd=1.7; no B1
  correlation multiplier, no learned size agents, no governor, no risk budget —
  disclosed simplification, frozen here, copied from oc_dip1h).
  - D05:  0.5  x G2 = 0.0320656 per rung per coin.
  - D025: 0.25 x G2 = 0.0160328 per rung per coin.
  Max sleeve gross (25 concurrent rungs): D05 0.80x, D025 0.40x.

## Daily sleeve mechanics (frozen)
- Bars: 1d, opens at 00:00 UTC (minute-0 1m open), majors only
  (BTC/ETH/SOL/BNB/XRP USDT perp). 1m sources (same files the 4h replicas use):
  BTC `data/raw/btc_intraday_20260924/klines_1m_20*.parquet`, others
  `data/raw/majors_intraday_20260924/<SYM>_1m_20*.parquet` (cover
  2019-12-31/2020..2026-09-23 23:59; ETH from 2019, SOL/BNB/XRP from 2020).
- sigma1d per coin = std (ddof=1) of the last 120 DAILY log returns of daily
  opens, causal: lr[i]=ln(o[i]/o[i-1]), sg[j]=std(lr[j-120:j]) with min_periods
  60, then shifted so sg[j] uses only bars strictly before day j (known at j's
  open). Window 120 per the assignment; min 60 (labelled) so the short Y2017
  pre-sample leg stays tradeable; every main-window bar has the full 120
  (verified and reported). Day j skipped when sg[j] is NaN/non-positive.
- Ladder at each daily open O: resting limit bids at O x (1 - k x sigma1d),
  k in RUNGS.
- Orders live minutes 5..1439 of the day (offsets 5..1439 inclusive; minutes
  0..4 excluded = 5-minute pipeline delay). Fill ONLY on strict 1m
  trade-through (minute low < bid); fill price = bid (maker 0.0002). Equality
  never fills. At most one fill per (day, coin, k).
- After a fill at minute f: scan minutes f+1..1439. Stop if minute low <=
  stop = fill x (1 - 4.0 x sigma1d) -> market exit at min(stop, minute open)
  (taker 0.00055). Else TP if minute high > TP = fill x (1 + 1.0 x sigma1d) ->
  limit exit at TP (maker 0.0002). Stop checked FIRST each minute (stop-first).
- Anything still open at the next daily open exits by market at that open
  (taker 0.00055).
- Funding (gate): longs pay 0.0001 x notional per 8h settlement (00/08/16 UTC
  timestamps) spanned by the hold: n_settle = #{ts : fill_time < ts <=
  exit_time}, charged on EVERY exit type (stop/TP/timeout). A full-day timeout
  always spans 3 settlements (08, 16, 24h). Shorts n/a (long-only sleeve).
- Costs: maker 0.0002 (bid fill, TP), taker 0.00055 (stop, timeout exit).
- Traded daily opens T (main window): 2021-09-24 00:00 <= T <= 2026-09-22 00:00
  (last day whose next-day 00:00 open exists in the 1m data, which ends
  2026-09-23 23:59). A day is skipped unless all 1440 minutes and the next-day
  open are present (logged skip count). Hence the post-release year covers
  opens 2025-09-24..2026-09-22 (363d), labelled.

## Pre-sample (frozen; standalone only, no G2 overlay there)
- Data (read-only, same as oc_presample2): `data/raw/spot_1m_presample_20261007`
  (Binance SPOT 1m 2017-08..2020-09; BTC/ETH from 2017-08-17, BNB from
  2017-11-06, XRP from 2018-05-04; SOL absent -> never traded pre-sample).
  Spot-vs-perp caveat labelled on every pre-sample table (fills/exits on SPOT
  prices, perp gate costs), same as oc_presample2.
- Legs (oc_presample2-exact): Y2017=[2017-10-16,2018-01-01) (77d),
  Y2018=[2018-01-01,2019-01-01), Y2019=[2019-01-01,2020-01-01),
  Y2020p=[2020-01-01,2020-09-01) (244d). Rungs opened on days with open in the
  leg; exits may realise on the first day of the next leg (labelled).
- Warm-up per coin (data-start + 60d, oc_presample2 dates): BTC/ETH 2017-10-16,
  BNB 2018-01-05, XRP 2018-07-03; plus sigma must be finite (min 60).
- Same ladder/exit/cost/funding rules as the main window, both D05 and D025.
- Metric norm: full 365d legs (Y2018/Y2019) use geometric 12th-root %/mo;
  partial legs (Y2017 77d, Y2020p 244d) use 100*(E^(30.4375/N_days)-1),
  labelled (oc_presample2 convention).

## Accounting (frozen)
- Standalone sleeve: per anchor year reset equity 1.0 at A; days with open in
  [A, A+365d) (main) or the leg interval (pre-sample). Rung notional =
  size_frac x E at the entry day open (compounds intra-year). Concurrent rungs
  across coins allowed, no standalone cross-cap (disclosed; the combined
  account enforces the 2x cap). Equity stepped per day by realised PnL (exits
  attributed to the exit day). Main-window %/month = 100 x (E_end^(1/12) - 1).
  DD = daily-close DD (labelled lower bound; intraday excursion is bounded
  because every rung carries a 4-sigma touch stop). Trades, win rate (net ret
  > 0 after fees+funding, equal-weight over rungs), fee share = total fee legs
  / max(sum of positive-trade gross, eps) with fee_leg = 2*MAKER (TP) else
  MAKER+TAKER, gross from exit/fill price ratio only (oc_dip1h-exact; funding
  reported separately).
- Combined account (frozen, oc_carrycompound/oc_dip1h UTA method): G2 hourly
  equity from v421/v421_runs.pkl strat R2B1D17BFG2 via v388.hourly/mix on grid
  2021-09-24 04:00 .. 2026-09-23 12:00 (g1 = Y1+12h, Y1 = 2026-09-23; same as
  oc_carrycompound/oc_dip1h). f=0 (G2 alone) must reproduce v421_result.json G2
  row (R/W/DD per year + full-path DD) TO THE DIGIT before any overlay, else
  stop and report. Overlay on TOTAL equity: A(t) = A(t-1) x (1 + r_bot(t)) +
  dSleeve(t); marked M(t) = A(t-1) x (ms_base(t)/es_prev(t)) + dU(t); sleeve
  notionals sized off COMBINED A at each entry day (N = size_frac x A_entryday);
  exits attributed to the exit hour; per-year reset to 1.0; continuous
  full-path DD (v421 convention). Cross-margin gross cap 2.0: G2 gross proxied
  as constant 1.0 x A (disclosed; v421 runs store no exposure series); a new
  rung is skipped when (open_sleeve + new)/A + 1.0 > 2.0 (rungs ordered by
  fill minute, then coin, then k). Skip count reported.
- Grid cut: everything ends at g1 = 2026-09-23 12:00 UTC (G2 runs end there);
  all sleeve exits are <= 2026-09-23 00:00 by construction (last traded open
  2026-09-22), so the overlay needs no truncation (labelled).

## Years, selection, scoring (frozen)
- Anchors: dev 2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24 (dev4);
  post-release 2025-09-24 scored ONCE, labelled, never used for selection.
- Robust pick among G2 / G2+D05 / G2+D025 on dev4 ONLY: DD <= 20 and no losing
  dev year; prefer dev4 mean >= 5 %/mo, then highest dev4 WORST-year monthly
  return, ties -> higher mean.
- Report: standalone per-year (%/mo, DD, trades, win, fee share) for dev4 +
  post (labelled) + pre-sample legs (labelled, both variants); combined dev4
  per-year/mean/WORST/DD; 5y mean; full-path DD (max close/marked); Pearson
  correlation of DAILY (00 UTC grid) simple returns, sleeve standalone
  (continuous, no reset) vs G2, dev4 (+ post labelled separately).
- Vietnamese 3-line verdict (adopt / reject / needs prospective evidence).

## Leakage controls (frozen)
- sigma1d uses daily opens strictly before the decision day (shifted);
  bids/fills use the day open (known at open) and 1m lows/highs up to the fill
  minute only; TP/stop scan uses minutes after the fill only; timeout uses the
  next daily open; funding counts only settlements in (fill, exit].
- No fits, no thresholds, no quantiles: every number above is copied from G2
  config/gate costs/oc_dip1h readings in this PLAN before any outcome. No
  statistic from any test year feeds any choice. REPORT.md states the four
  timing checks explicitly.

## Engineering (frozen)
- Files (ONLY these): research/tournament/oc_dipdaily/PLAN.md (this file),
  dipdaily_core.py (pure-numpy mechanics, no I/O), run_dipdaily.py
  (--step g2 | pass1 --coin X [--pre] | pass2 | all), REPORT.md, results.json,
  tmp/ (g2_hourly.npz, rec_<COIN>.parquet, rec_pre_<COIN>.parquet, logs).
- One process, one coin's 1m H/L in RAM at a time (float32); O cached as
  float32; two-pass (pass1: per-rung unit-return records independent of
  equity — exact since sizing is a fixed equity fraction; pass2: sequential
  equity accounting). Heavy 1m work via heavy_slot `--tag oc_dipdaily
  --min-free-gb 2.0`. Progress print every 10 minutes. No 4-phase engine runs.
- Tests: `tests/test_oc_dipdaily.py` with (1) causality/truncation tests (no
  fill in minutes 0..4; equality never fills; sigma excludes current bar;
  stop-first tie; funding settlement counting; next-day-open timeout) and (2)
  hand-checked synthetic cases with exact expected returns incl. fees/funding.
  Run `.venv/Scripts/python.exe -m pytest tests/test_oc_dipdaily.py -q`.
  Stop when done.
