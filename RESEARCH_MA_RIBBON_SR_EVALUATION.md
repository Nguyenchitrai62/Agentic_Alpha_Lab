# TradingView MA Ribbon as support/resistance — detailed evaluation (2026-09-25)

User settings (screenshot): MA #1 SMA 50 close, MA #2 SMA 200 close, MA #3/#4 off,
timeframe = chart, "wait for timeframe closes" on. Values verified against the user's
Bybit 5m chart to < 1 USD.

## Test design (`scripts/masr_reaction.py`)

- BTC, ETH, SOL USD-M, 2019/2020 to 2026-09; bars for 15m/1h/4h/1d rebuilt from real 1m
  bars; SMA uses closed bars only (the value of the last closed bar).
- A test = previous bar closed above (support) / below (resistance) the SMA and the
  current bar trades to it. From the first touching minute the real 1m path runs a race:
  +k*ATR in the bounce direction first = HOLD, -k*ATR through the line first = BREAK
  (k = 0.5, 1, 2; ATR14 of that timeframe; 20-bar horizon; same-minute ties excluded).
- Placebo: levels at the same distance from the previous close (distance drawn from the
  real test distribution), touched in the same way, not within 0.25 ATR of the SMA.
- ~416k events. Under no support/resistance effect, MA and placebo hold rates are equal.

## Results (±1 ATR race; all symbols and years; diff = MA minus placebo, 95% CI)

| TF | SMA | Support hold MA / placebo | diff | Resistance hold MA / placebo | diff |
|---|---|---|---|---|---|
| 15m | 50 | 49.3 / 48.9 (n=54.7k) | +0.4 ±0.6 | 49.7 / 49.8 | -0.1 ±0.6 |
| 15m | 200 | 49.3 / 48.7 (n=25.7k) | +0.7 ±0.9 | 49.8 / 50.1 | -0.3 ±0.9 |
| 1h | 50 | 50.1 / 49.6 (n=13.3k) | +0.5 ±1.2 | 48.6 / 49.1 | -0.5 ±1.2 |
| 1h | 200 | 49.0 / 50.4 (n=6.0k) | -1.4 ±1.8 | 49.1 / 50.4 | -1.3 ±1.8 |
| 4h | 50 | 48.1 / 50.9 (n=3.2k) | -2.8 ±2.5 | 49.6 / 49.7 | -0.1 ±2.5 |
| 4h | 200 | 50.4 / 52.1 (n=1.3k) | -1.7 ±3.9 | 46.3 / 51.3 | -4.9 ±3.9 |
| 1d | 50 | 50.9 / 54.7 (n=436) | -3.8 ±6.6 | 50.1 / 48.6 | +1.6 ±7.1 |
| 1d | 200 | 57.7 / 44.0 (n=137) | +13.6 ±11.8 | 37.5 / 41.7 | -4.2 ±11.3 |

Daily follow-up with 5 majors and BTC spot history from 2017 (1h path): SMA200 support
-2.7 ±7.4 pp (n=348; the +13.6 above was small-sample noise), SMA50 support -5.8 ±4.6 pp,
SMA200 resistance -6.5 ±7.7 pp. Results at k=0.5 and k=2 ATR, by trend state, by symbol,
development vs hidden year: same picture (`artifacts/research/masr/reaction/`).

Model (`scripts/masr_touch_model.py`): HGB on touch-time features (MA slopes, other-MA
distance, approach speed, recent touches, ATR%, daily trend, TF, time): AUC 0.510 on late
training data and 0.511 on the hidden year; top-decile predicted holds held 50.6%.

## Verdict

On 15m, 1h, 4h and 1d, SMA 50 and SMA 200 hold about 50% of the time, the same as an
arbitrary price at the same distance. Higher timeframes do not improve it; 4h/1d SMA50
support is, if anything, slightly worse than random. The lines are useful as a trend
state (the daily SMA50/200 regime is the one filter that survived every test in this
project), not as precise support/resistance.

Why they look like S/R on a chart: a random price touched from above also holds ~50% of
the time; holds are memorable while breaks are forgotten; smooth lines through the middle
of price swings are always "near" a turning point; and the eye reads the chart with
hindsight of which touch mattered.

## Update 2026-09-26: MA Ribbon as model features (v123, pooled majors model)

Registry parallel-20260906-r2 / v123 tested the multi-timeframe version of the user's TradingView MA Ribbon
(SMA50/SMA200 on 4h closes, the daily ribbon already used by v92, and a weekly ribbon from 50/200-week SMAs on daily
closes, plus a 4h+daily+weekly agreement score) as extra features for the v92/v94 models on the extended 2013+ history.

| | v115 portfolio (daily ribbon only) | v123 (+ 4h and weekly ribbon features) |
|---|---|---|
| normal, %/month | 2.61 | 2.59 |
| execution stress, %/month | 2.11 | 2.10 |
| full-path DD (execution stress) | 19.1% | 19.5% |
| v96 blend (v92 LO + v94 LS), %/month | 2.74 (v114) | 2.62 |

Verdict: the daily SMA50/SMA200 ribbon remains useful as a regime gate and feature (it is part of every surviving
model); 4h and weekly ribbons add no out-of-sample information on top of it. Combined with the earlier findings
(S/R touches at the ribbon lines have no reliable bounce/reject edge on 15m-4h after costs), the ribbon's value is
as a trend-regime filter, not as a stand-alone S/R entry signal.
