# oc_vrpstraddle PLAN (pre-registered 2026-10-07, BEFORE any outcome computed)

Question: does the volatility risk premium (Deribit DVOL 30-day ATM IV usually
above later realised vol) survive realistic costs and the crash weeks when
harvested as a delta-hedged short ATM straddle on BTC+ETH, and does it
diversify G2 (a long-rebound book)? Options were never traded in this program;
this is the first execution screen.

## Fixed rule (from OPENCODE_W_oc_vrpstraddle.md, no discretion)

- Cycle: every Friday. Entry 08:05 UTC. S = Binance USD-M perp 1m close of
  minute 08:04. Strike K = S rounded to NEAREST grid step (BTC 1000, ETH 50;
  `round(S/grid)*grid`). Guard K <= 0 or non-finite => skip coin/week (logged).
- Expiry: next Friday 08:00 UTC (V1, V2; T_entry = (expiry-entry)/365d =
  (7d-5min)/365) or 4 weeks later (V3; T_entry = (28d-5min)/365), entered every
  4th Friday, non-overlapping. "Every 4th Friday" = Fridays with
  (friday_index mod 4 == 0) where friday_index counts Fridays on/after
  2021-09-24 00:00 UTC in order, so the set is fixed before seeing outcomes.
- sigma_sell = 0.97 * latest known DVOL / 100. "Latest known" = close of the
  last hourly DVOL candle with candle-close <= decision time (strictly as-of).
  Premium/unit = BS call + BS put (r = q = 0) at sigma_sell, T_entry.
- Option fee per leg per side = min(0.0003 * S_trade, 0.125 * leg_price), where
  S_trade is the underlying price at that trade (entry: S_entry; TP/SL buyback:
  the triggering close price). Settlement fee per ITM leg
  = min(0.00015 * S_settle, 0.125 * intrinsic); OTM legs pay no settlement fee.
- Size: q = 0.5 * E / S units per coin (E = sleeve equity at entry). Both coins
  => options notional 1.0 x E. Standalone sleeve f = 1.0.
- BS (r = q = 0): call C = S*N(d1) - K*N(d2), put P = K*N(-d2) - S*N(-d1),
  d1 = (ln(S/K) + 0.5*s^2*T)/(s*sqrt(T)), d2 = d1 - s*sqrt(T). Straddle delta
  = 2*N(d1) - 1 (call delta N(d1), put delta N(d1)-1). T <= 0 => intrinsic
  (call max(S-K,0), put max(K-S,0)); s <= 0 or non-finite => intrinsic.
- Delta hedge (V1, V3): at every 4h bar close of the standard grid
  (00/04/08/12/16/20 UTC) set the perp position to -q * BS straddle delta at
  sigma_mark = latest known DVOL / 100 and remaining T = (expiry - close)/365d.
  First hedge at the first 4h close strictly after entry (12:00 Friday), so the
  window 08:05..12:00 Friday is unhedged (disclosed). Hedge trades filled at
  the bar close price with 2 bps adverse slippage + maker 0.0002 on the traded
  notional (total 4 bps per unit traded; a limit order resting from minute 5
  would be the real implementation). Hedge position is per coin, sized off that
  coin's q (hedge ratio fixed at entry; no re-sizing on equity drift).
  Long hedge pays 0.0001 per 8h settlement held (00/08/16 UTC grid hours, on
  pos*px when pos > 0); short hedge receives nothing.
- V2 = V1 without any hedge (pure short straddle; control showing what hedging
  buys). No funding, no hedge costs in V2.
- Risk exits (every position has SL + TP):
  * SL: at every 1h close (price = 1m close of that minute; sigma from latest
    known DVOL as of that close), position P&L(t) = hedge_cash + pos*px(t)
    - q*(mark_call + mark_put) + opt_cash, where opt_cash is net premium cash
    (received minus fees paid so far) and hedge_cash accumulates hedge trade
    cashflows/fees/funding. If P&L(t) <= -1.0 x gross premium received
    (q*(call_prem + put_prem)), close everything: buy back the straddle at BS
    with sigma = 1.05 * latest known DVOL / 100 (remaining T) + per-leg fees at
    the triggering close price; hedge closed at the close price as taker
    (0.00055 on |pos|*px). Earliest trigger wins; no exit checks before the
    first hourly close strictly after entry (09:00 Friday).
  * TP: at each 4h close (a subset of the 1h closes; TP checked FIRST when both
    coincide there), if straddle mark (sigma_mark = latest known DVOL / 100,
    remaining T) <= 0.3 x gross premium, buy back at that mark + per-leg maker
    fees at the close price; hedge closed at the close price as taker (0.00055;
    conservative, labelled). Maker fee rate for the option buyback.
  * Otherwise settle at expiry: payoff/unit = -(|S_settle - K|) (call intrinsic
    + put intrinsic), S_settle = mean of the 30 1m closes 07:30..07:59 Friday
    (all known at 08:00), plus per-leg settlement fees if ITM; hedge closed at
    the first hourly close >= expiry (09:00 bar) at that price as taker.
- Variants (ONLY these three): V1 = 1-week hedged; V2 = 1-week unhedged;
  V3 = 4-week hedged, every 4th Friday, non-overlapping.

## Data (as-of only)

- DVOL: data/raw/deribit_dvol_20261005/{BTC,ETH}_*.json, hourly candles
  [ms,o,h,l,c]; a candle is known at its close; use close/100. Coverage from
  2021-04 (warm: entries start 2021-09-24, so DVOL history is ample).
- Sensitivity IV only: data/raw/deribit_opt_20260926/{BTC,ETH}_options_4h.parquet
  (bar = 4h bar start UTC; known at start+4h); sigma_alt
  = 0.5*(iv_otm_put + iv_otm_call)/100, DVOL fallback when NaN.
- Underlying: Binance USD-M 1m: data/raw/btc_intraday_20260924/klines_1m_*.parquet
  (BTC), data/raw/majors_intraday_20260924/{ETH}USDT_1m_*.parquet (ETH).
  Perp 1m close as price. Hourly close = 1m close of minute :59; 4h closes
  likewise (standard grid).
- Hourly grid 2021-09-24 04:00 .. v388.Y1+12h for marks/DD (same convention as
  oc_putwrite).

## Years and selection (W_COMMON)

- Dev4 anchors 2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24, each year =
  [A, A+365d). Most recent year 2025-09-24..2026-09-23 scored ONCE, only for the
  chosen variant (+ G2 reference). No fitting of any kind; nothing estimated on
  any test year.
- Standalone sleeve: fresh account E = 1.0 at each anchor; only cycles with
  entry Friday in [A, A+365d) AND expiry <= A+365d 00:00 UTC are taken (boundary
  skip, disclosed; costs V3 ~1 cycle/year at the edge); no inherited state, no
  spanning positions. Metric: geometric %/month = 100*(E_end^(1/12)-1); DD =
  max hourly-marked drawdown within the year (marks use as-of DVOL only; option
  liability marked hourly at sigma_mark, hedge at px); plus worst week (min
  168-step hourly return), SL/TP/expiry counts, mean IV-RV gap at entries
  (sigma_sell vs 7d/28d realised vol from 1m log-returns entry->expiry,
  annualised), P&L split option leg vs hedge leg (net of all fees/funding).
- Robust criterion: among V1..V3 with DD <= 20 and no losing dev year, prefer
  dev4 mean >= 5 %/mo if any, then highest dev4 WORST-year monthly return, ties
  -> higher mean. Anything changed after seeing outcomes is a disclosed extra
  row, original kept.
- Sensitivity rows for the chosen variant only (labelled): (a) sigma from the
  OTM-IV average instead of DVOL (sell 0.97x, SL-buyback 1.05x, hedge/TP marks
  1.0x; DVOL fallback on NaN); (b) option fees x2 (0.0006*S cap/side, 0.0003
  settlement; 0.125 caps unchanged); (c) hedge slippage 5 bps (fee unchanged).

## Overlay on G2 (secondary, labelled)

- Reproduce G2 baseline (R2B1D17BFG2 in v421/v421_runs.pkl via v388.hourly)
  exactly vs v421_result.json before any overlay; else stop and report.
- Combo account (UTA assumption, labelled): per anchor year reset A = 1.0;
  A(t) = A(t-1)*(1+r_bot(t)) + dSleeve(t), r_bot from the stored 4-phase G2
  hourly mix, dSleeve from sleeve notionals sized at f x A at each entry
  (compounds intra-year), same weekly rule incl. boundary skip. f = 0.25 and
  0.5 of TOTAL equity. Marked path uses the same sleeve dU (close-marked
  options; DD lower bound labelled).
- Report per year: reset-metric R, yearly DD, full-path DD (continuous account,
  max of marked/close per v421 convention) vs G2 alone; daily-P&L correlation
  (sleeve leg vs G2 leg, from yearly-reset combo paths concatenated over the
  5y span) overall and in G2's worst 20 days; worst 5 combo weeks with dates.
- Caveat paragraph (mandatory): DVOL is a 30-day index; a 7-day (V1/V2) or
  28-day (V3) straddle has its own term-structure IV (usually lower in calm,
  higher in stress); no strike-level quotes (strike-level check needs
  data/raw/deribit_strike_20261007, being fetched by another worker).

## Leakage checks (to state in REPORT.md)

feature timing (DVOL candle known at close; S at 08:04 known at 08:05; marks
use latest closed hourly DVOL / closed 4h IV; settlement uses 07:30..07:59
closes known at 08:00); label windows (payoff uses only post-entry minutes);
fit windows (no fits, no thresholds); fill timing (option premium/marks, no
order book; hedge fills at known closes + adverse slippage; no fill in first
5 min after a 4h close is N/A for the hedge since rebalances sit on the close
itself — labelled as a research simplification vs the minute-5 limit rule).

## Outputs

research/tournament/oc_vrpstraddle/{PLAN.md (this file), vrp.py, run_vrp.py,
results.json, REPORT.md, trades_*.parquet, tmp/};
tests/test_oc_vrpstraddle.py (>=1 causality/truncation test + >=1 hand-checked
synthetic BS/parity/fee case; pytest -q). G2 numbers reproduced to the digit or
stop-and-report.
