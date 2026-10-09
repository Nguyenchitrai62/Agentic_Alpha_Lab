# oc_putwrite PLAN (pre-registered 2026-10-07, BEFORE any outcome computed)

Question: is a simple weekly cash-secured put-write sleeve (BTC+ETH) profitable
after costs in every dev year, and does it add return per unit of DD on top of
G2 (or make a MANUAL product possible: one human action per week)?

## Fixed rule (from OPENCODE_W_oc_putwrite.md, no discretion)

- Cycle: every Friday. Entry 08:05 UTC (after 08:00 weekly expiry), expiry next
  Friday 08:00 UTC (7 days, T = 7/365 at entry, r = 0, q = 0).
- sigma_e = iv_otm_put of the last 4h bar whose close <= 08:05 (bar starting
  04:00) / 100; fallback Deribit DVOL hourly close / 100 (last hourly candle
  with close <= 08:05). If both missing, skip that coin that week (logged).
- S = 1m close of minute 08:04 (Binance USD-M perp 1m close as price).
  Strike K = S * exp(-z * sigma_e * sqrt(7/365)), rounded DOWN to grid
  (BTC 1000, ETH 50). Guard: K <= 0 or non-finite => skip coin/week.
- Premium/unit = Black-Scholes European put with sigma_sell = 0.95 * sigma_e.
- Fee/side/unit = min(0.0003 * S_trade, 0.125 * option_price), where S_trade is
  the underlying price at that trade (entry: S_entry; TP/SL exit: triggering
  close price; expiry settlement: S_settle). Settlement fee if ITM
  = min(0.00015 * S_settle, 0.125 * intrinsic).
- Exits (every trade carries SL+TP):
  * TP: at each 4h close (00/04/08/12/16/20 bars, price = 1m close of minute
    :59 before the close), mark = BS put at sigma_mark = 1.05 * (latest KNOWN
    4h iv_otm_put as of that close) / 100 with remaining T = (expiry - close) /
    365d. If mark <= 0.2 * premium, buy back at mark + fee. Earliest trigger
    wins; TP checked before SL at the same 4h close (a 4h close is also an 1h
    close; TP uses the 4h rule). No exit check on the entry day before the
    first 4h close after entry (12:00 Friday).
  * SL: at each 1h close (price = 1m close of minute :59), same sigma_mark rule
    (latest known 4h IV at that hour; DVOL fallback same as entry). If
    mark >= 3 * premium, buy back at mark + fee. Same-bar stop-first rule is
    moot here (single mark per check); TP at a 4h close takes precedence when
    both conditions coincide there.
  * Otherwise expire: payoff/unit = -max(K - S_settle, 0),
    S_settle = mean of 1m closes 07:30..07:59 Friday (30 bars).
- Sizing (cash-secured): each coin gets half the sleeve equity;
  q = 0.5 * f * E_entry / K (collateral q*K = 0.5 f E). Standalone f = 1.
- BS put: P = K*N(-d2) - S*N(-d1),
  d1 = (ln(S/K) + 0.5 s^2 T)/(s sqrt(T)), d2 = d1 - s sqrt(T);
  T <= 0 => intrinsic max(K-S,0); s <= 0 => intrinsic.
- Variants (ONLY these four):
  * P1 z = 1.0, P2 z = 1.5, P3 z = 2.0,
  * P4 = put credit spread: P2 short put + LONG put same expiry at z = 3.0,
    bought at sigma_buy = 1.05 * sigma_e + 0.05, same fee rule;
    long leg closed together with short leg on TP/SL at its own mark with
    sigma 0.95 * latest IV + 0.05 (remaining T same). Collateral
    q*(K_short - K_long), q = 0.5 f E / (K_short - K_long); guard
    K_short <= K_long => fall back to naked P2 for that coin/week (logged).

## Data (as-of only)

- IV: data/raw/deribit_opt_20260926/{BTC,ETH}_options_4h.parquet (bar = 4h bar
  start UTC; a bar is known at start+4h). BTC 2019-01-01..2026-10-07 no NaN;
  ETH 2019-03-21..2026-09-24 with 102 NaN put / 39 NaN call => DVOL fallback.
- DVOL: data/raw/deribit_dvol_20261005 BTC/ETH monthly JSON, hourly candles
  [ms,o,h,l,c]; candle known at its close; use close/100.
- Underlying: Binance USD-M 1m (data/raw/btc_intraday_20260924/klines_1m_*.parquet
  for BTC, data/raw/majors_intraday_20260924/ETHUSDT_1m_*.parquet for ETH;
  2021..2026-09-23 full coverage verified). Perp 1m close as price. Hourly
  close = 1m close of minute :59; 4h close likewise.
- Hourly grid 2021-09-24 00:00 .. 2026-09-23 23:00 UTC for marks/DD.

## Years and selection (W_COMMON)

- Dev4 anchors 2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24, each year =
  [A, A+365d). Most recent year 2025-09-24..2026-09-23 scored ONCE, only for
  the chosen variant (+ G2 reference). No fitting (z fixed); nothing estimated
  on any test year.
- Standalone sleeve: fresh account E = 1.0 at each anchor; only cycles with
  entry Friday in [A, A+365d) AND expiry <= A+365d 00:00 UTC are taken; entries
  whose expiry would fall after the year end are SKIPPED (disclosed boundary
  skip, ~1 week/year), so no spanning positions; no inherited state. Metric: geometric %/month =
  100*(E_end^(1/12)-1); DD = max hourly-marked drawdown within the year
  (marks use as-of IV only); plus worst week, trades, TP/SL/expiry counts,
  win rate (net P&L > 0), mean premium yield/week = mean over cycles of
  (premium*q both coins / E_entry).
- Robust criterion: among P1..P4 with DD <= 20 and no losing dev year, prefer
  dev4 mean >= 5 %/mo if any, then highest dev4 WORST-year monthly return,
  ties -> higher mean. Anything changed after seeing outcomes is added as a
  disclosed extra row, original kept.
- Sensitivity (chosen variant only, labelled): sigma_sell haircut 0.90;
  fees x2 (0.0006*S cap side, 0.0003 settlement; 0.125 caps unchanged).

## Overlay on G2 (secondary, labelled)

- Reproduce G2 baseline (R2B1D17BFG2 in v421/v421_runs.pkl via v388.hourly)
  exactly vs v421_result.json before any overlay; else stop and report.
- Combo account (UTA assumption, labelled: needs Bybit UTA portfolio margin; no
  margin model here): per anchor year reset A = 1.0; A(t) = A(t-1)*(1+r_bot(t))
  + dSleeve(t), r_bot from stored 4-phase G2 hourly mix, dSleeve from put-write
  notionals N sized at f x A at each entry (compounds intra-year), same weekly
  rule incl. boundary skip. f = 0.25 and 0.5 on TOTAL equity.
- Report per year: 4-phase reset metric R, yearly DD, full-path DD (continuous
  account, max of marked/close per v421 convention) vs G2 alone; daily-P&L
  correlation (combo sleeve leg vs G2 leg); worst 5 weeks of combo with dates
  (same crash weeks as dip sleeve? stated qualitatively).
- MANUAL view: same overlay on honest MANUAL M5_human hourly equity
  (research/diagnostics/oc_manualcap/oc_manualcap_runs.pkl, row M5_human via
  v388.hourly); if unloadable, write "not found". Yearly-level only, labelled.

## Leakage checks (to state in REPORT.md)

feature timing (IV bar known at close; S at 08:04 known at 08:05; marks use
latest CLOSED 4h bar / closed hourly DVOL; settlement uses 07:30..07:59 closes
known at 08:00); label windows (expiry payoff uses only post-entry minutes);
fit windows (no fits); fill timing (N/A: option premium/marks, no order book;
entry/exit at known closes).

## Outputs

research/tournament/oc_putwrite/{run_putwrite.py,results.json,REPORT.md,
trades_*.parquet,tmp/}; tests/test_oc_putwrite.py (>=1 causality/truncation
test + >=1 hand-checked synthetic BS/settlement case; pytest -q). G2 numbers
reproduced to the digit or stop-and-report.
