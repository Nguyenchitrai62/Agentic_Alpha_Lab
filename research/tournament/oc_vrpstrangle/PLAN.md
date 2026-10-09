# oc_vrpstrangle PLAN (pre-registered 2026-10-07, BEFORE any outcome computed)

Question: does the volatility risk premium survive realistic costs and crash
weeks when harvested as an UNHEDGED weekly short OTM strangle on BTC+ETH whose
legs are priced from TRADED OTM IV (not an index), and does it diversify G2?
Second, independent VRP structure after oc_vrpstraddle (ATM straddle priced at
0.97 x DVOL: failed alone with DD 25.8, overlay f=0.25 gave 6.41 %/mo with
lower DD). The pricing input here is different and traded: per-4h-bar
notional-weighted traded IV of OTM puts / calls with expiry <= 60 days
(`iv_otm_put`, `iv_otm_call` in data/raw/deribit_opt_20260926, bar = 4h bar
start UTC, known at start+4h).

## Fixed rule (from OPENCODE_W_oc_vrpstrangle.md, no discretion)

- Cycle: every Friday 08:05 UTC, BTC and ETH. S = Binance USD-M perp 1m close
  of minute 08:04 (bar open exactly 08:04; else last bar open strictly before;
  logged as inexact). Expiry next Friday 08:00 UTC.
  T_entry = (expiry - entry) / 365d = (7d - 5min) / 365 in years.
- Sigmas at entry: sigma_p = iv_otm_put / 100, sigma_c = iv_otm_call / 100 of
  the last 4h bar with close <= 08:05 (bar starting 04:00); per-leg fallback
  DVOL / 100 when that leg is NaN (disclosed per trade). Skip coin/week if
  both legs NaN and DVOL NaN, or sigma <= 0 (logged).
- Strikes: K_p = S * exp(-z * sigma_p * sqrt(T)) rounded DOWN to the grid,
  K_c = S * exp(+z * sigma_c sqrt(T)) rounded UP (grids BTC 1000, ETH 50).
  Guard K <= 0 / non-finite / K_p >= K_c => skip coin/week (logged).
- Premium/unit = BS put(K_p, 0.97 * sigma_p) + BS call(K_c, 0.97 * sigma_c),
  r = q = 0 (BS copy of oc_vrpstraddle mechanics). Marks / SL buy-back legs at
  1.05 x the latest known sigma of each leg (same per-leg DVOL fallback);
  TP marks at 1.0 x. "Latest known" at time t = last 4h IV bar close <= t
  (fallback: last hourly DVOL candle close <= t), strictly as-of.
- Option fee per leg per side = min(0.0003 * S_trade, 0.125 * leg_price),
  S_trade = underlying price at that trade. Settlement fee per ITM leg
  = min(0.00015 * S_settle, 0.125 * intrinsic); OTM legs pay nothing.
- Risk exits (every position has SL + TP; TP checked FIRST at 4h closes):
  * SL: at every 1h close (hourly px = 1m close of the prior minute, e.g. the
    09:00 bar is the 08:59 1m close), per-unit P&L(t) = opt_cash - mark_sl(t),
    opt_cash = gross - entry fees, mark_sl at 1.05x sigmas. If P&L <= -1.0 x
    gross premium received => buy back both legs at BS(1.05x sigmas) + per-leg
    fees at the triggering close. Earliest trigger wins; no checks before the
    first hourly close strictly after entry (09:00 Friday).
  * TP: at each 4h close (hour % 4 == 0, subset of 1h closes), if mark_tp(t)
    at 1.0x sigmas <= 0.3 x gross => buy back at that mark + per-leg maker
    fees at the close.
  * Else settle at expiry: payoff/unit = -(max(K_p - S_settle, 0)
    + max(S_settle - K_c, 0)), S_settle = mean of the 30 1m closes
    07:30..07:59 on expiry Friday (all known at 08:00), plus per-leg
    settlement fees if ITM. No exit checks at the expiry step itself.
- No hedge of any kind (pure short strangle; hedge leg identically zero).
- Size: q = 0.5 * f * E / S units per coin (E = sleeve/account equity at
  entry). Both coins => options notional f x E in total. Standalone f = 1.0.
- Variants (ONLY these two): Z1 z = 0.5; Z2 z = 1.0.

## Data (as-of only; same loaders as oc_vrpstraddle)

- OTM IV: data/raw/deribit_opt_20260926/{BTC,ETH}_options_4h.parquet
  (bar = 4h bar start UTC; known at start+4h).
- DVOL fallback: data/raw/deribit_dvol_20261005/{BTC,ETH}_*.json hourly
  candles; known at candle close. Coverage from 2021-04.
- Underlying: Binance USD-M 1m: data/raw/btc_intraday_20260924/klines_1m_*
  (BTC), data/raw/majors_intraday_20260924/{ETH}USDT_1m_* (ETH). Hourly
  px at grid point t = 1m close of minute t - 60s.
- Hourly grid 2021-09-24 04:00 .. v388.Y1+12h for marks/DD.

## Years and selection (W_COMMON)

- Dev4 anchors 2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24, each year =
  (A, A+365d] on the hourly grid. Most recent year 2025-09-24..2026-09-23
  scored ONCE, only for the chosen variant (+ G2 reference). No fitting of any
  kind; nothing estimated on any test year.
- Standalone sleeve: fresh account E = 1.0 at each anchor; only cycles with
  entry Friday in (A, A+365d] AND expiry <= year-end grid edge are taken
  (boundary skip, disclosed). Metric: geometric %/month = 100*(E_end^(1/12)-1);
  DD = max hourly-marked drawdown within the year (option liability marked
  hourly at 1.0x sigmas); plus worst week (min 168-step hourly return), trade
  count, TP / SL / expiry counts, mean premium % of S (gross/S*100 averaged
  over trades), mean entry sigma avg in points with DVOL-fallback share, mean
  (IV - realised) gap in decimals = mean(0.5*(sig_p_raw+sig_c_raw)/100 - rv),
  rv = 1m log-return realised vol entry->expiry annualised (same loader as
  oc_vrpstraddle).
- Robust criterion: among Z1/Z2 with DD <= 20 and no losing dev year, prefer
  dev4 mean >= 5 %/mo if any, then highest dev4 WORST-year monthly return,
  ties -> higher mean. If none qualifies, fallback to the highest dev4 worst
  year (as oc_vrpstraddle did). `final <VARIANT>` asserts the winner
  recomputation before scoring. Anything changed after seeing outcomes is a
  disclosed extra row, original kept.

## Overlay on G2 (secondary, labelled)

- Reproduce G2 baseline (R2B1D17BFG2 in v421/v421_runs.pkl via v388.hourly,
  reset_metric.year_reset) exactly vs v421_result.json (5.41 / 16.91 / 16.82)
  before any overlay; else stop and report.
- Combo account (UTA assumption, same convention as oc_carrycompound /
  oc_vrpstraddle): per anchor year reset A = 1.0;
  A(t) = A(t-1)*(1+r_bot(t)) + dSleeve(t), r_bot from the stored 4-phase G2
  hourly mix, dSleeve from sleeve notionals sized at f x A at each entry
  (compounds intra-year), same weekly rule incl. boundary skip. f = 0.25 and
  0.5 of TOTAL equity. The open option liability MUST be marked at every
  hourly point in the combined equity used for DD (close-marked; DD lower
  bound labelled). f = 0 must reproduce G2 to the digit (asserted).
- Full-path DD: continuous account from grid start (max of marked/close).
- Report per year: reset-metric R, yearly DD, full-path DD vs G2 alone;
  daily-P&L correlation (sleeve leg vs G2 leg, yearly-reset f=0.25 combo paths
  concatenated over the 5y span) overall and in G2's worst 20 days; worst 5
  combo weeks with dates.

## Caveat paragraph (mandatory)

Aggregated OTM IV mixes strikes and tenors <= 60 d (not the 7-day OTM quote at
K_p/K_c); term-structure and smile risk unmodeled. No bid/ask (BS mids with
Deribit-style fee caps). Settlement uses the Binance perp 1m mean, not
Deribit's settlement index. Marks are hourly closes: DD is a lower bound
(no intrabar). No hedge by design: crash weeks are borne in full.

## Leakage checks (to state in REPORT.md)

feature timing (4h IV bar known at start+4h; hourly DVOL known at close; S at
08:04 known at 08:05; marks use latest closed 4h IV / closed hourly DVOL;
settlement uses 07:30..07:59 closes known at 08:00); label windows (payoff
uses only post-entry minutes); fit windows (no fits, no thresholds); fill
timing (options at model marks, no order book; no position events before
09:00 Friday; TP-before-SL at 4h closes; no fill in the first 5 min after
entry by construction).

## Outputs

research/tournament/oc_vrpstrangle/{PLAN.md (this file), strangle.py,
run_strangle.py, results.json, REPORT.md, trades_*.parquet, tmp/};
tests/test_oc_vrpstrangle.py (>=1 causality/truncation test + >=1
hand-checked synthetic BS/parity/fee/strike case; pytest -q). G2 numbers
reproduced to the digit or stop-and-report.
