# oc_gex PLAN (pre-registered 2026-10-07, BEFORE any outcome)

## Question
Dealer gamma exposure (GEX) proxy from Deribit strike-level trades: does it predict G2 dip-rung outcomes?

## Write scope
ONLY `research/tournament/oc_gex/` + `tests/test_oc_gex.py`. No other edits.

## Data (read-only)
- `data/raw/deribit_strike_20261007/{BTC,ETH}/*.parquet` (primary, months 2021-01..2026-06 BTC / ..2026-10 ETH).
- `data/raw/deribit_strike_20261007_b/{BTC,ETH}/*.parquet` (overlap 2025-07..2026-09, verified byte-identical on overlap sample; dedupe rule: load primary, then append ONLY months missing from primary, then drop duplicates on (hour, instrument_name) keeping first).
- Columns used: hour, instrument_name, expiry, strike, cp, sum_amount, vwap_iv, vwap_index, taker_buy_amount, taker_sell_amount.
- No other option data. 1m klines only inside the copied dip replica (unchanged).

## Proxy (FIXED before any outcome; no tuning after)
- Assumption (disclosed): takers = customers, makers = dealers.
- Per instrument i, customer net position: q_i(t) = cumsum over hours h <= t of (taker_buy_amount - taker_sell_amount)_i,h, starting at the instrument's first trade in the data. Uses only hours <= t (causal).
- Proxy starts 2021-04-01 00:00 UTC. Hours before that are used only to build q (burn-in); no GEXn output before 2021-04-01. Instruments listed before 2021-01 have unknown pre-history (left-censored); report the share of alive-at-2021-04-01 instruments affected + their share of volume. OPERATIONAL DEFINITION (fixed now): "older" = first in-sample trade at hour <= 2021-01-15 00:00 UTC (already listed and trading at sample start, hence listed in 2020 with high probability); shares reported by count, by |q| at proxy start, and by pre-start traded notional. (CHANGELOG 2026-10-07: added this operational definition + the IV-percent fix above; both before any outcome was computed.)
- Expiry: data `expiry` is a date at 00:00 UTC; Deribit settlement is 08:00 UTC that date, so instrument i is alive at hour-end t iff t < expiry_date + 8h. Expired instruments excluded from the sum at t. (Diagnostic note: "alive" counts include not-yet-listed future instruments with q=0 — zero GEX contribution; the censored share uses alive AND first-trade<=proxy-start.)
- Expiry: data `expiry` is a date at 00:00 UTC; Deribit settlement is 08:00 UTC that date, so instrument i is alive at hour-end t iff t < expiry_date + 8h. Expired instruments excluded from the sum at t.
- iv_i(t) = last traded vwap_iv of instrument i with hour <= t (as-of forward-fill); UNITS: raw vwap_iv is in
  PERCENT (verified 2026-10-07 on BTC_2021-01: median 131.7, i.e. Deribit API percent convention; a (0,10] decimal
  filter would reject 99.3% of rows — logged as a pre-outcome bug fix, no outcomes seen). Valid raw in [1.0, 990.0);
  raw < 1.0 or >= 990.0 (sentinel cap) or non-finite -> missing (ffill past it); iv_decimal = raw/100, then CLIP the
  as-of iv into [0.05, 3.0] (5%..300% ann). If no valid iv yet for i at t, skip i at t.
- S_t = median of vwap_index across rows with that hour (robust; single market price). If no rows that hour, S_t = last S (ffill); hours with no S at all are NaN (no GEX).
- Time to expiry: T_i(t) = max((expiry_08UTC - t).total_seconds() / (365.25*86400), 1/8760) (floor 1 hour; avoids div-by-zero in the expiry hour).
- Black-Scholes gamma (European, same for C/P), r = 0, q = 0 (disclosed; crypto short-dated, rate second-order vs IV/T noise): d1 = [ln(S/K) + 0.5*iv^2*T] / (iv*sqrt(T)); gamma = N'(d1) / (S*iv*sqrt(T)), N'(x)=exp(-x^2/2)/sqrt(2pi). Skip if any input non-finite or <= 0.
- Dealer gamma: GEX(t) = -sum_{i alive at t} q_i(t) * gamma_i(t) * S_t^2 * 0.01 (dollar gamma per 1% move; q in coin units as stored in sum_amount).
- Hourly traded notional: H(t) = sum_i sum_amount_i(t) * vwap_index_i(t) (USD/hour traded that hour; 0 if no trades).
- NORMALISATION (pick ONE now — chosen): dollar-notional: GEXn(t) = GEX(t) / (S_t * N30(t)), where N30(t) = trailing 30-day (720h) mean of H ending at t (causal, requires >=168 valid hourly H values else NaN). The z-score alternative is REJECTED now and will not be computed.
- Output: hourly series for BTC and ETH, timestamp = hour END (value known at end of that hour). CSV/parquet `gex_hourly_{BTC,ETH}.parquet` with columns hour_end, S, GEX, H, N30, GEXn. For SOL/BNB/XRP dip rungs use BTC's GEXn (market-wide dealer state; disclosed).
- Units note (disclosed): GEX is USD per 1% move; denominator S*N30 is USD^2/hour; GEXn is therefore 1/(USD/hour)-scaled — a pure cross-sectional normalisation, sign and rank are what the screen uses.

## Sanity checks (no dip outcomes)
- GEX sign/median by regime: full-sample + dev-year medians; sign on expiry days (last trading day before monthly/quarterly 08:00 UTC) vs non-expiry; sign during 2022 crash months (2022-05, 2022-06, 2022-11). No dip-rung outcome used.
- Mechanism check (realised vol IS an outcome -> dev years ONLY, 2021-09-24..2025-09-23): Spearman(GEXn(t), subsequent 24h realised vol from hourly S) on dev rows only. Expect NEGATIVE if dealers-dampen mechanism exists. Never computed on the most recent year in this study.

## Dip screen (dev years 2021-09-24..2025-09-23 for SELECTION; most recent year once at end)
- Replica: copy `research/tournament/oc_placebo_dip/compute_placebo_dip.py` core (D0 outcomes TP1sg/sl4sg-close5/bl8sg/timeout next-bar open; maker 0.0002/taker 0.00055; v293 settle funding; B1 sizes w=1/(1+n); 4 clock phases; majors x R2 rungs 2.5..5; live 16..238 strict trade-through; bars open [2021-09-24, 2026-09-24)). MUST reproduce base_sum5y = 7.718 (4-phase-mean sums [0.911, 0.833, 2.100, 3.197, 0.677] to 3 decimals) before any join; else stop and report.
- Join (causal): each rung fill's bar open time bt (4h grid) -> g = GEXn of the last full hour with hour_end <= bt - 1 minute (i.e. last closed hour strictly before the bar open; hourly series known at hour end). Label rows with g missing as NaN (excluded from terciles/corrs, counted). Coin mapping: BTC/ETH own series; SOL/BNB/XRP use BTC GEXn.
- 1) DESCRIPTIVE (dev fills only, per dev year y in 0..3): Spearman(GEXn, rung net outcome y10 with B1 weight applied? — fixed: Spearman on raw rung outcome y10 (unweighted) + weighted-mean check disclosed); mean outcome by GEXn tercile (tercile cuts from that year's own dev rows — descriptive only, no forward use); stop-out rate (how in {stop, backstop} / filled) by tercile. Hypothesis direction FIXED NOW: HIGH GEXn (dealers long gamma) = better rung outcomes / fewer stops.
- 2) CONDITIONAL TILT (only if sign as hypothesised in >= 3 of 4 dev years, i.e. top-tercile mean outcome > bottom-tercile mean outcome in >=3 dev years; Spearman sign is secondary): single pre-registered variant T1 = rung weight x1.25 in top GEXn tercile, x0.75 in bottom tercile, x1.0 middle/missing. Tercile cut points for year Y come ONLY from rows with bar open < anchor(Y) - 7 days (embargo), pooled across the 4 phases (per-coin? NO — single pooled cut on BTC-mapped GEXn for uniformity; disclosed). Scored with the established dip gate: PROMISING legs (per-year 4-phase-mean S_rule>=S_base AND DD_rule<=DD_base+0.01, >=4/5 years) PLUS dSum5y >= +0.273 (labelled 5-year calibration; pooled placebo p95), AND the dev4 view (same legs on years 0..3 + dSum_dev4 reported). Exposure-matched constant control T1c: uniform multiplier c = (total T1 weight)/(total base weight) on the same fills (isolates selection vs leverage). NO other variants. If the >=3/4 condition fails, NO tilt is scored (report descriptive only).
- Most recent year (2025-09-24..2026-09-23): scored ONCE, only for the chosen variant (T1 if triggered, else base reference) + base; labelled. Never used to choose.
- Costs: replica legs already net of maker/taker + settle funding (same as placebo base). No extra cost layer.
- Leakage checks (REPORT): feature timing (hour_end <= bt-1min), label windows (outcomes after fill, never in GEX), fit windows (tercile cuts end anchor-7d), fill timing (replica unchanged).

## Outputs
- `research/tournament/oc_gex/{PLAN.md(this), compute_gex.py, screen_gex_dip.py, gex_hourly_BTC.parquet, gex_hourly_ETH.parquet, results.json, REPORT.md (<=58-line style: setup, fidelity, per-year table, verdict), tmp/ scratch only}`.
- `tests/test_oc_gex.py`: >=1 causality/truncation test + >=1 hand-checked synthetic case (BS gamma put/call parity + fixed GEX hand total; tercile-cut embargo test). Run `.venv/Scripts/python.exe -m pytest tests/test_oc_gex.py -q`.
- REPORT ends with 3-line Vietnamese verdict (adopt / reject / needs prospective evidence). If PROMISING say so in BOLD; leader decides on an engine run.
- Progress print >= every 10 min in long scripts.
