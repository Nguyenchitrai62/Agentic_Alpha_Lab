# Phase A — zero-shot feasibility results

Run date: 2026-09-05. These are research observations, not trading advice.

## Environment and data

- Windows, Python 3.11.9, PyTorch 2.12.1 + CUDA 12.6.
- NVIDIA GTX 1650 4 GB; all three released Kronos variants loaded successfully.
- 8,639 closed Binance USD-M BTCUSDT 5-minute candles.
- Range: 2026-08-06 07:40 UTC through 2026-09-05 07:34:59.999 UTC.
- Data validation: no duplicate timestamps, missing intervals, invalid OHLC, or non-positive prices.

## Single-window latency

Context 512 bars, forecast 12 bars, greedy decoding (`top_k=1`), one path.

| Model | Time | Peak allocated CUDA memory | Direction on held-out window |
|---|---:|---:|---|
| Kronos-mini | 0.46 s | 51.9 MB | Correct |
| Kronos-small | 0.32 s | 136.4 MB | Incorrect |
| Kronos-base | 0.64 s | 447.9 MB | Incorrect |

One window cannot rank model quality; this only verifies execution and resource use.

## One-hour forecast/bracket smoke comparison

Same 256 windows, 15-minute decision stride, 12-bar horizon, 12 bps forecast gate,
1x notional, 0.04% per fill, long funding 0.01%/8h, short funding zero.

| Model | Direction accuracy at coverage | Trades | Gross PnL | Fees + funding | Net return |
|---|---:|---:|---:|---:|---:|
| mini | 51.8% | 51 | +62.46 | 404.47 | -3.42% |
| small | 50.9% | 54 | +48.22 | 427.57 | -3.79% |
| base | 52.3% | 52 | -76.65 | 407.53 | -4.84% |

## Longer mini runs

### One-hour horizon

- 2,706 rolling windows over roughly 28 days.
- 755 actionable forecasts at a 12 bps gate; 400 non-overlapping filled trades.
- Direction accuracy at coverage: 54.17%.
- Gross PnL: +145.04; fees: 2,772.53; funding: 4.66.
- Net return: **-26.32%**.

The raw sign forecast showed a small positive gross result, but turnover made it unusable.

### Four-hour horizon

- 674 rolling windows, one decision per hour, 48-bar horizon.
- The full-sample 40 bps gate appeared profitable (+0.80%), but this was selected on the same sample.
- A chronological validation/test audit selected 30 bps on the first half:
  - validation: +0.74%, 27 trades;
  - embargoed second half: **-1.61%**, 34 trades, profit factor 0.74;
  - direction accuracy fell from 65.7% to 46.2%.

Therefore no zero-shot configuration tested in Phase A passes an out-of-sample acceptance gate.

### Passive BTC comparison

Over the same downloaded period, BTC buy-and-hold returned +22.63%; it returned
+20.36% on the validation half and +2.98% on the locked-test half. This is not a
like-for-like futures strategy comparison, but it shows that the sample was strongly
bullish and the tested Kronos signal/execution combinations failed to preserve that beta.

## Latest uncalibrated observation

At 2026-09-05 07:34:59.999 UTC for the next 12 five-minute bars:

- mini: WAIT at the 12 bps gate;
- small: SHORT;
- base: SHORT.

This is saved only to demonstrate the live-data interface. It must not be treated as an executable signal.
Small and base produced the same decoded endpoint in this run, so their matching
votes are correlated evidence rather than two independent confirmations.

## Current simulator limitations

- Maximum drawdown is computed from closed-trade equity, not intratrade mark-to-market equity.
- OHLC bars cannot represent exchange queue priority or the probability that a touched limit fills.
- Slippage, liquidation, maintenance margin, latency, and variable historical funding are not modeled yet.
- Funding is the fixed scenario requested here, not Binance's historical realized funding series.

## Next research step

Do not search more thresholds on this test interval. The next useful work is to:

1. acquire a longer immutable history and define train/validation/locked-test ranges;
2. add cheap EMA/logistic/tree baselines;
3. cache Kronos hidden states;
4. train a fee-aware multi-horizon directional head with calibrated abstention;
5. evaluate on a new forward interval before changing TP/SL rules.
