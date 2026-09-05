# Phase A — zero-shot feasibility results

Run date: 2026-09-05. These are research observations, not trading advice.

Latest continuation: `RESEARCH_V4_RESULTS.md` supersedes the status below.
Full-trunk Kronos-base v2 completed but remained all WAIT. Tree v3 failed its
first holdout; expanded-history tree v4 returned+5.1135% with DD4.2228% on the
April–July2026 reserve, but ONE fill is insufficient evidence. User maxDD now20%.

**Historical engine warning:** Phase A numbers below were produced with legacy
OHLC v1. They have not been recomputed after v2 fixed ambiguous entry-candle TP,
funding notional and truncated holding windows. Do not compare them as though the
execution model were unchanged, or call the old simulator uniformly conservative.

## Continuation: supervised pipeline smoke (2026-09-05)

`TRAINING.md` documents the implemented dataset/Colab/checkpoint loop. Local CUDA
MLP training completed (best epoch 6, stopped at 12); calibration temperature 1.2.
New **ohlc-v2** evaluation with fixed 1x and the requested fees/funding:

- Capital 100 -> 99.6459, return -0.3541%, close-sampled Max DD -0.9029%, PF 0.8051.
- 12 long / 0 short trades; gross +0.13419, fees 0.47832, funding 0.00999 (capital 100 units).
- 4h three-class accuracy 47.00%, ECE 9.32%; P10–P90 realized coverage 71.97%.
- Uniform fee stress 0.055%/fill: -1.1882%; this is a scenario, not a verified exchange tariff.
- Test is a short, previously inspected research interval, not new forward evidence.
- Not a candidate. No threshold was adjusted after opening it; no leverage enabled.

This MLP uses engineered multi-timeframe features, NOT trained Kronos embeddings.
Colab notebook/package exist, but execution in a real Colab runtime is unverified.

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
1x notional, 0.02% per fill (0.04% round trip), long funding 0.01%/8h,
short funding zero.

| Model | Direction accuracy at coverage | Trades | Gross PnL | Fees + funding | Net return |
|---|---:|---:|---:|---:|---:|
| mini | 51.8% | 51 | +61.94 | 204.77 | -1.43% |
| small | 50.9% | 54 | +48.37 | 217.53 | -1.69% |
| base | 52.3% | 52 | -77.16 | 206.83 | -2.84% |

## Longer mini runs

### One-hour horizon

- 2,706 rolling windows over roughly 28 days.
- 755 actionable forecasts at a 12 bps gate; 400 non-overlapping filled trades.
- Direction accuracy at coverage: 54.17%.
- Gross PnL: +149.38; fees: 1,497.13; funding: 5.08.
- Net return: **-13.53%**; capital index 100 became 86.47.

The raw sign forecast showed a small positive gross result, but turnover made it unusable.

### Four-hour horizon

- 674 rolling windows, one decision per hour, 48-bar horizon.
- The full-sample 30 bps gate appeared profitable (+2.66%), but this was selected on the same sample.
- A chronological validation/test audit selected 30 bps on the first half:
  - validation: +1.83%, 27 trades, profit factor 1.43;
  - embargoed second half: **-0.26%**, 34 trades, profit factor 0.95;
  - direction accuracy fell from 65.7% to 46.2%.

Therefore no zero-shot configuration tested in Phase A passes an out-of-sample acceptance gate.

### Leverage experiment

An exploratory strength-based policy used 1x normally, 1.5x when the absolute
forecast was at least twice the signal threshold, and 2x at four times the threshold.
On the same full sample it returned +2.34% with -3.24% drawdown versus +2.66% and
-2.97% at fixed 1x. Forecast magnitude is not calibrated confidence, and leverage
made both return and drawdown worse; it remains disabled by default.

### Passive BTC comparison

Over the same downloaded period, BTC buy-and-hold returned +22.63%; it returned
+20.36% on the validation half and +2.98% on the locked-test half. This is not a
like-for-like futures strategy comparison, but it shows that the sample was strongly
bullish and the tested Kronos signal/execution combinations failed to preserve that beta.

## Latest uncalibrated observation

The latest probabilistic Kronos-mini snapshot uses 16 paths per timeframe:

- 5m → 1h: WAIT, 50.0% upside probability;
- 15m → 4h: LONG, 62.5%;
- 1h → 24h: LONG, 93.8%;
- 4h → 72h: LONG, 100.0%;
- weighted view: LONG, 85.625% upside probability.

This is saved only to demonstrate the live-data interface. It must not be treated as an executable signal.
The sampled percentages are not calibrated probabilities and the combined
multi-timeframe rule has not passed a locked test.

## Current simulator limitations

- Maximum drawdown samples trade-candle-close equity, not exchange mark prices or every intrabar trough.
- Stop/timeout are market-like exits at the user scenario fee; they are not guaranteed maker exits.
- OHLC bars cannot represent exchange queue priority or the probability that a touched limit fills.
- Approximate isolated liquidation is modeled, but true mark price, risk tiers, latency,
  and historical variable funding are not modeled yet.
- Funding is the fixed scenario requested here, not Binance's historical realized funding series.

## Next research step

Do not search more thresholds on this test interval. The next useful work is to:

1. acquire a longer immutable history and define train/validation/locked-test ranges;
2. add cheap EMA/logistic/tree baselines;
3. cache Kronos hidden states;
4. train a fee-aware multi-horizon directional head with calibrated abstention;
5. evaluate on a new forward interval before changing TP/SL rules.
# Newer supervised Kronos experiment

See `KRONOS_TRADING.md`: actual frozen Kronos-mini plus multi-frame attention and
learned bracket scoring is implemented. Private Kaggle dataset uploaded and kernel
`nguynchtrai/kronos-btc-mtf-20260905-v1` completed on 2 Tesla T4. Checkpoint downloaded
and replay verified. Validation: all 971 decisions WAIT, zero trades, equity 100;
not accepted as a trading candidate. This is a new supervised experiment,
not a revision of the historical Phase A results below. Local smoke proves pipeline
execution only, not profitability. Read the newer document for final run status.
