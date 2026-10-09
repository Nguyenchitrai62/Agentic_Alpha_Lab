# oc_dip1h PLAN (pre-registered BEFORE any outcome, 2026-10-08 — FROZEN)

Task: docs/opencode/OPENCODE_W_oc_dip1h.md + docs/opencode/OPENCODE_W_COMMON_20261007.md.
Write ONLY `research/tournament/oc_dip1h/` and `tests/test_oc_dip1h.py`.

## Question
A 1h-grid dip sleeve with G2's mechanism, as an extra return source next to G2.
Exactly TWO variants (pre-registered, no other rows; any post-outcome change is a
disclosed extra row, never a replacement).

## G2 parameters read from config (frozen here, before any outcome)
- Source: `backend/history_tm.py` KW_OVERRIDE["v321"] (R2 ladder), `research/
  tournament/oc_dipbe/be_core.py` (deployed-ladder replica constants),
  `research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py`
  (SIZE=0.25, S_REF=1.657, RUNGS default), v411 (D17 = dips x1.7, budget
  0.26x1.7, bear-book filter), v421 (G2 = R2B1D17BFG2 = D17BF + gross cap 2.0).
- RUNGS k = (2.5, 3.0, 3.5, 4.0, 5.0) sigma units (R2 deployed ladder; the
  engine_user default (2.5..4.0) is the pre-R2 ladder and is NOT used).
- TP multiple = 1.0 sigma (engine_user m_sleeve_tp default; R2 agents vary TP
  per rung but a standalone 1h sleeve has no 4h-book context, so fixed 1.0).
- Stop depth = 4.0 sigma, TOUCH stop (market, taker), stop-first on a same-1m-bar
  tie. Disclosed simplification: G2's deployed stop is bot-watched 5m-close
  4-sigma + 8-sigma native backstop; the assignment names one stop depth, so the
  literal 1m implementation is a touch stop at 4.0 sigma, no backstop.
- G2 per-rung size_frac = (0.25/4/1.657) x kd(1.7) = 0.0641312 of equity
  (engine_user rung notional s*g*0.25/4/1.657 with D17 kd=1.7; no B1
  correlation multiplier, no learned size agents, no governor — disclosed
  simplification, frozen here).
  - H05:  0.5  x G2 = 0.0320656 per rung per coin.
  - H025: 0.25 x G2 = 0.0160328 per rung per coin.
  Max sleeve gross (25 concurrent rungs): H05 0.80x, H025 0.40x.

## 1h sleeve mechanics (frozen)
- Bars: 1h, opens on the hour (minute-0 1m open), from data/raw majors 1m:
  BTC `data/raw/btc_intraday_20260924/klines_1m_20*.parquet`,
  others `data/raw/majors_intraday_20260924/<SYM>_1m_20*.parquet`
  (same files the 4h replicas use; yearly files cover 2020..2026-09-23).
  Majors only (BTC/ETH/SOL/BNB/XRP USDT perp).
- sigma1h per coin = std (ddof=1) of the last 720 hourly LOG returns of 1h
  opens, causal: uses only bars strictly before the decision bar (shift(1));
  min_periods 120, else the bar is skipped (no rungs).
- Ladder at each 1h open O: bids at O x (1 - k x sigma1h), k in RUNGS.
- Orders live minutes 5..59 of the bar (offsets 5..59 inclusive; minutes 0..4
  excluded = 5-minute pipeline delay). Fill ONLY on strict 1m trade-through
  (minute low < bid); fill price = bid (maker 0.0002). Equality never fills.
- After a fill at minute f: scan minutes f+1..59. Stop if minute low <=
  stop = fill x (1 - 4.0 x sigma1h) -> market exit at min(stop, minute open)
  (taker 0.00055). Else TP if minute high > TP = fill x (1 + 1.0 x sigma1h) ->
  limit exit at TP (maker 0.0002). Stop checked FIRST each minute (stop-first).
- Anything still open at the next 1h open exits by market at that open
  (taker 0.00055).
- Funding (gate): longs pay 0.0001 x notional when a settlement (00/08/16 UTC)
  falls in the holding hour, i.e. exit-bar-open hour in {0,8,16}. Shorts n/a
  (sleeve is long-only).
- Costs: maker 0.0002 (bid fill, TP), taker 0.00055 (stop, timeout exit).

## Accounting (frozen)
- Standalone sleeve: per anchor year reset equity 1.0 at A; bars with 1h open
  in [A, A+365d). Rung notional = size_frac x E at the entry bar open
  (compounds intra-year). Concurrent rungs across 5 coins allowed, no
  standalone cross-cap (disclosed; the combined account enforces the 2x cap).
  Equity stepped per bar by realised PnL (exit time attributed to exit hour).
  %/month = 100 x (E_end^(1/12) - 1). DD = max(hourly-close DD, 1m-marked DD
  with open rungs marked at 1m closes — labelled lower bound). Trades, win
  rate (net ret > 0 after fees+funding), fee share = total fees /
  max(sum of positive-trade gross, eps).
- Combined account (frozen): G2 hourly equity from v421/v421_runs.pkl strat
  R2B1D17BFG2 via v388.hourly/mix on grid 2021-09-24 04:00 .. 2026-09-23 12:00
  (g1 = Y1+12h, Y1 = 2026-09-23; same as oc_carrycompound). f=0 (G2 alone) must
  reproduce v421_result.json G2 row (R/W/DD per year + full-path DD) TO THE
  DIGIT before any overlay, else stop and report.
  Overlay on TOTAL equity (UTA, as oc_carrycompound): A(t) = A(t-1) x
  (1 + r_bot(t)) + dSleeve(t); marked M(t) = A(t-1) x (ms_base(t)/es_prev(t)) +
  dU(t); sleeve notionals sized off COMBINED A at each entry bar
  (N = size_frac x A_entrybar); per-year reset to 1.0; continuous full-path DD
  (v421 convention). Cross-margin budget: gross <= 2.0 x A incl. G2 exposure;
  v421 runs store NO exposure series, so G2 gross is proxied as constant 1.0 x
  A (disclosed); a new rung is skipped when (open_sleeve + new)/A + 1.0 > 2.0.
  Skip count reported.
- Grid cut: everything ends at g1 = 2026-09-23 12:00 UTC (G2 runs end there);
  the post-release year [2025-09-24, 2026-09-23] is therefore covered to g1
  (~364.5d) and labelled as such. Sleeve 1m data reaches 2026-09-23 23:59 but
  is cut at g1 for comparability (labelled).

## Years, selection, scoring (frozen)
- Anchors: dev 2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24 (dev4);
  post-release 2025-09-24 scored ONCE, labelled, never used for selection.
- Robust pick among G2 / G2+H05 / G2+H025 on dev4 ONLY: DD <= 20 and no losing
  dev year; prefer dev4 mean >= 5 %/mo, then highest dev4 WORST-year monthly
  return, ties -> higher mean.
- Report: standalone per-year (%/mo, DD, trades, win, fee share); combined
  dev4 per-year/mean/WORST/DD; 5y mean; full-path DD (max close/marked);
  Pearson correlation of DAILY (00 UTC grid) simple returns, sleeve
  standalone vs G2, dev4 (+ post-year labelled separately).
- Vietnamese 3-line verdict (adopt / reject / needs prospective evidence).

## Leakage controls (frozen)
- sigma1h uses bars strictly before the decision bar; bids/fills use the bar
  open (known at open) and 1m lows/highs up to the fill minute only; TP/stop
  scan uses minutes after the fill only; timeout uses the next 1h open.
- No fits, no thresholds, no quantiles: every number above is copied from G2
  config or the gate cost model before any outcome. No statistic from any test
  year feeds any choice. REPORT.md states the four timing checks explicitly.

## Engineering (frozen)
- One process, one coin's 1m H/L in RAM at a time (float32); O/C cached as
  float32; two-pass (pass 1: collect per-rung unit-return records independent
  of equity — exact since sizing is a fixed equity fraction; pass 2:
  sequential equity accounting). Heavy run via heavy_slot
  `--tag oc_dip1h --min-free-gb 2.0`. Progress print every 10 minutes.
- Tests: `tests/test_oc_dip1h.py` with (1) causality/truncation tests
  (no fill in minutes 0..4; equality never fills; sigma excludes current bar;
  stop-first tie) and (2) hand-checked synthetic cases with exact expected
  returns incl. fees/funding. Run `.venv/Scripts/python.exe -m pytest
  tests/test_oc_dip1h.py -q`. Stop when done.
