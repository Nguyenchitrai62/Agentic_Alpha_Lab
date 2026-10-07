# oc_stopslip PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

DIAGNOSTIC, no selection. Question: the friction row S4 "stop slip 0.5"
(`stop_slip=0.5` in `research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py::_slip`:
long fill = px - 0.5*max(0, px - minute low); short fill = px + 0.5*max(0, high - px))
assumes market stops fill halfway between the stop level and the exit-minute bar
extreme. Measure what that slippage really is on Binance 1m vs Bybit 1m.

## Hypothesis (fixed here, diagnostic only)

No directional pre-claim. The script measures, for every stop exit of the
deployment config, the adverse slippage of a market fill at the next minute's
open versus the stop level on each venue, the S4-implied slip from the same
minute's range, the implied slip fraction (actual / S4), and the share of stops
landing in flash minutes (1m range > 3 sigma). No tuning, no selection.

## Data (fixed here, all in repo - no fetch)

- Stop universe: `research/tournament/oc_kpi_g2/events_s{0,1,2,3}.parquet`,
  kinds `book_stop` + `rung_sl` only, pooled over the 4 phase sub-accounts
  (each is 1/4 capital; counts are summed). Fields used: `t` (exit minute),
  `symbol`, `kind`, `side`, `price`, `ret` (rungs only), `weight`.
- Binance 1m: `data/raw/btc_intraday_20260924/klines_1m_20*.parquet` (BTC),
  `data/raw/majors_intraday_20260924/{SYM}_1m_20*.parquet` (ETH/SOL/BNB/XRP),
  columns open_time/open/high/low/close (open_time already UTC datetime).
- Bybit 1m (the S5 store used by
  `research/parallel/rounds/parallel-20260906-r2/v411_audit/robust_v411.py::bybit_minutes`):
  `data/raw/bybit_linear_1m_20261004/{SYM}_1m.parquet` with `open_time` in ms
  epoch, columns open/high/low/close.
- Cap: no 1m row with open_time >= 2026-09-24 00:00 UTC is ever loaded into a
  comparison (Bybit file runs to 2026-10-03 but rows >= the cap are dropped at
  load). Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- All five years are research data; any finding needs prospective validation
  before real money (disclosed vs RULES.md hidden-year rule).
- Resources: one process; 1m OHLC of ONE coin x BOTH venues at a time
  (peak < 1 GB); RAM < 3 GB.

## Exact causal definitions (frozen)

1. Stop level proxy (the events store the base-engine fill, not the level;
   the deployment replica ran with `stop_slip=0`, touch stops, so under the
   engine the fill equals the stop except on gap opens):
   - `book_stop`: stop := event `price` (raw fill `min(sl, open)` for a long /
     `max(sl, open)` for a short; fees are booked separately, not in the price).
   - `rung_sl`: the event `price` = `lv*(1+ret)` is NET of rung fees
     (`ret = raw/lv - 1 - MAKER - TAKER`), so stop := `price + lv*(MAKER+TAKER)`
     with `lv = price/(1+ret)`, i.e. the raw fill `min(sl, open)`; equivalently
     `stop = lv*(raw/lv)` where `raw/lv = 1+ret+0.0002+0.00055`. When a minute
     open gaps beyond the stop, the recorded stop is the gap open (the true
     level is unobserved); this is disclosed as a caveat and makes the measured
     slip a lower bound on those events.
   - `side=="sell"` = long stopped (exit is a sell); `side=="buy"` = short
     stopped (exit is a buy). All `rung_sl` are sells (dip rungs are long).
2. Venue bars: for stop at minute `t`, coin `c`, venue V: the 1m bar with
   `open_time == t` gives `O/H/L/C`, and the bar with `open_time == t+1min`
   gives `O_next` (no ffill; NaN = missing, reported as coverage, excluded
   from that venue's stats).
3. Actual slippage (adverse-positive bps, market fill proxied by next-minute open):
   - long stop: `slip = (stop - O_next)/stop * 1e4`;
   - short stop: `slip = (O_next - stop)/stop * 1e4`.
   Positive = the market fill is worse than the stop; negative = price moved
   back in favour before the next open. Uses only the exit minute's bar and the
   next minute's open (both known after the exit; a measurement, not a signal).
4. S4-implied slip from the SAME exit-minute bar on the same venue:
   - long: `depth = max(0, (stop - L)/stop*1e4)`, `s4 = 0.5*depth`;
   - short: `depth = max(0, (H - stop)/stop*1e4)`, `s4 = 0.5*depth`.
   Slip fraction: `frac = slip / s4` where `s4 > 0` (events with `s4 == 0`
   contribute `frac = NaN` and are counted separately; `slip <= 0` gives
   `frac <= 0`). `frac = 0.5` would mean the next-open fill sits halfway
   between the stop and the S4 fill; `frac = 1` means the next-open fill equals
   the S4 assumption; `frac > 1` means worse than S4.
5. Flash minutes: minute range `R = (H - L)/O*1e4` bps. Trailing moments
   `mu, sig = mean/std(R over the 1440 minutes strictly before t, min_periods 720,
   ddof=1)` per coin per venue (causal: nothing at/after `t` enters them).
   Flash := `R > mu + 3*sig` (requires finite `mu`, `sig > 0`; else not flash,
   counted separately). Reported as the share of stops in flash minutes.
   POST-HOC FIX (logged): first draft used `R > 3*sig`, which flags ~85% of
   stops (for a non-negative range whose mean exceeds its std, `3*sig` sits
   below an ordinary minute). `mu + 3*sig` is the intended 3-sigma tail event;
   the script was fixed before REPORT.md was written and no outcome seen under
   the old rule is reported.
6. Years: by EXIT time `t` in anchor years `Y0..Y4 = [A_k, A_k+365d)` with
   `A = (2021-09-24, ..., 2025-09-24)` (same windows as `compute_kpi.year_of`;
   exitša of the final live bar after `A_4+365d` join Y4). Per (coin, year) and
   pooled rows.
7. Distributions: over stops with a finite venue slip, per (coin, year, venue)
   and pooled: n, median / p90 / p99 / max of `slip` (bps), median of `s4`
   (bps), median of `frac`, share flash, share `s4 == 0`, share missing.
8. Worst 10: the 10 stops with the largest adverse `max(slip_bin, slip_byb)`
   (venues with finite slips; ties by exit time). Each row: exit time, coin,
   kind, side, shift, stop level, per-venue `O/H/L/O_next/slip/s4/frac/flash`.

## Decision rule (fixed: DIAGNOSTIC, no PROMISING rule)

No PROMISING/NOT-PROMISING verdict (the assignment marks this DIAGNOSTIC, so
the default >=4/5 same-sign + >=4/5 leave-one-year-out rule does NOT apply).
The REPORT answers in plain words: (a) per-coin x year slip tables for both
venues; (b) the median slip fraction vs the S4=0.5 assumption (is 0.5
conservative or aggressive, per coin/year); (c) the flash-minute share; (d) the
worst-10 list. One-line verdict = the (b) sentence with numbers.

## Protocol (fixed)

- PLAN.md written before any outcome computation. Then script `run.py`
  (per-coin loop, venue bars, causal flash sigma, per-coin-year stats ->
  results.json + stops ledger parquet). Outputs: results.json, REPORT.md
  (tables + one-line verdict). Test `tests/test_oc_stopslip.py` (synthetic
  hand checks: side-aware slip sign, s4/frac arithmetic, flash rule, year
  bucketing, Bybit cap at 2026-09-24).
- No commits; no edits outside research/tournament/oc_stopslip/
  (+ tests/test_oc_stopslip.py).
