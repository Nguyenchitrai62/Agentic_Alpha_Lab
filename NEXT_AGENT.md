# Handoff for the next coding agent

This is the canonical continuation guide after cloning `Agentic_Alpha_Lab`.
Read this file and `AGENTS.md` completely before changing code or running an
experiment. The repository is a research and paper-trading system, not a live
order executor.

## 1. Objective

Build a leakage-aware BTCUSDT perpetual research loop that:

1. downloads closed market candles and related market data;
2. runs Kronos on several timeframes;
3. converts calibrated model outputs into `WAIT`, `LONG`, or `SHORT` plus an
   entry limit, TP1, TP2, stop loss, holding horizon, confidence, and position size;
4. backtests those decisions after fees, funding, fill rules, drawdown, margin,
   and liquidation risk;
5. packages training data for Google Colab and brings the trained checkpoint
   back into the same locked evaluation pipeline;
6. exposes inference and experiment results in the local web dashboard.

The immediate goal is robust positive out-of-sample net return. Do not optimize
accuracy alone and do not claim a usable strategy from an in-sample threshold.

## 2. Repository relationship

The expected sibling layout is:

```text
Source_code/
├── Agentic_Alpha_Lab/   # this repository
└── Kronos/              # untouched upstream reference repository
```

Clone the official Kronos repository beside this repo if `../Kronos` is absent.
Do not copy its checkpoints into Git and do not modify upstream Kronos merely to
make an experiment pass. Put reusable adaptations in this repository.

Downloaded checkpoints, raw data, generated reports, virtual environments, and
Node dependencies are intentionally ignored. A fresh clone must regenerate them.

## 3. Non-negotiable trading assumptions

- Instrument: linear `BTCUSDT` perpetual.
- Base data: closed 5-minute candles; aggregate only complete higher-timeframe candles.
- Entry and normal exit: limit/maker fee `0.0002` (0.02%) per fill, or 0.04% round trip.
- Long funding scenario: pay `0.0001` (0.01%) at each 00:00, 08:00, and 16:00 UTC boundary held.
- Short funding income: always zero. This deliberately avoids optimistic funding income
  and acts as a small allowance for unmodeled slippage.
- Signal formed after candle `t` closes; the earliest possible entry is candle `t+1`.
- A limit order fills only if the following real OHLC range touches its price.
- If stop and take-profit are both touched in one OHLC candle, use `stop_first`.
- Initial capital is displayed as index `100`. Position notional is recalculated from
  current equity after every trade, so results compound.
- Default comparison is 1x. Confidence-based leverage must be reported separately,
  capped at 2x until calibrated, and must never be enabled because it improves the
  same sample used to design it.
- Bybit-style liquidation is triggered using mark-price logic in production. The
  current OHLC approximation is conservative but is not an exchange-perfect simulator.
- Never place authenticated or live orders without a new explicit user instruction.

## 4. Bootstrap a fresh Windows/NVIDIA clone

Run from the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install torch==2.12.1 --index-url https://download.pytorch.org/whl/cu126
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

On this Windows setup, GPU entry points must import `torch` before `pandas` or
`c10.dll` can fail with WinError 1114.

Download model files and market data:

```powershell
.\.venv\Scripts\python.exe scripts\download_kronos_models.py --variants mini small base
.\.venv\Scripts\python.exe scripts\download_btc.py --days 30
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider
```

Expected baseline at this handoff: 7 tests pass. If they do not, stop and fix the
regression before running new experiments.

## 5. Reproduce inference and the dashboard

Generate a four-timeframe probabilistic snapshot using Kronos-mini:

```powershell
.\.venv\Scripts\python.exe scripts\generate_dashboard_data.py --variant mini --paths 16
cd web
npm ci
npm run build
npm run dev
```

Open `http://localhost:3000/`. The dashboard source is under `web/app/`; its
generated data is written to both `web/app/dashboard-data.json` and
`web/public/data/dashboard.json`.

The current dashboard covers:

- 5m context → 1-hour forecast;
- 15m context → 4-hour forecast;
- 1h context → 24-hour forecast;
- 4h context → 72-hour forecast;
- probabilistic P10–P90 bands from independent stochastic paths;
- timeframe consensus, entry/TP/SL candidates, compounded backtests, and a
  separate leverage comparison.

Known web work still to finish:

1. run and fix the production build if necessary;
2. wire `web/public/og.png` into Open Graph/X metadata;
3. validate the timeframe tabs and responsive layout in the browser;
4. validate the optional WebMCP `select_forecast_timeframe` tool where a supported
   browser context is available;
5. keep the dashboard read-only until there is a safe local inference API.

## 6. Current evidence — do not reinterpret it

All numbers below use 0.02% entry plus 0.02% exit fees, long funding 0.01%/8h,
short funding zero, compounded equity, and conservative OHLC execution.

| Experiment | Capital 100 becomes | Net return | Important note |
|---|---:|---:|---|
| Mini 1h, 2,706 windows | 86.47 | -13.53% | 400 trades; fees dominate |
| Mini 4h, threshold 30 bps, full sample | 102.66 | +2.66% | in-sample only |
| Mini 4h validation, threshold 30 bps | 101.83 | +1.83% | PF 1.43 |
| Mini 4h embargoed locked test | 99.74 | -0.26% | PF 0.95; direction accuracy 46.15% |
| Dynamic 1x/1.5x/2x, full sample | 102.34 | +2.34% | worse than fixed 1x and larger DD |

The zero-shot model therefore does not pass the acceptance gate. The full-sample
profit must not be described as validation. The previously opened locked interval
is no longer pristine for future tuning; collect a new forward interval for the
next locked test.

The last generated multi-timeframe snapshot was:

- 5m: `WAIT`, 50.0% sampled upside probability;
- 15m: `LONG`, 62.5%;
- 1h: `LONG`, 93.8%;
- 4h: `LONG`, 100.0%;
- weighted consensus: `LONG`, 85.625%.

This is a 16-path zero-shot snapshot, not calibrated confidence and not a live signal.

## 7. Priority continuation: build the training pipeline

Do not start with reinforcement learning or architecture search. First establish a
strong, cheap, reproducible supervised baseline.

### Data to acquire

Use at least 3 years and preferably a full bull/bear cycle. Store immutable raw
partitions with a manifest and SHA-256 hashes. At minimum collect:

- Binance and/or Bybit trade OHLCV at 5m;
- mark-price and index-price candles;
- historical funding rate and exact funding timestamps;
- open interest, turnover, taker-buy volume, and basis where available;
- exchange maintenance-margin/risk-tier metadata for realistic liquidation tests.

Use only fields known after the decision candle closes. Join 15m, 1h, and 4h
features backward onto the 5m decision clock and discard incomplete higher-frame bars.

### Labels

Create multi-horizon targets for 1h, 4h, and 24h:

- three-class direction: `SHORT / WAIT / LONG`, where the WAIT band is wider than
  round-trip fees plus a validation-selected safety buffer;
- return quantiles (P10/P50/P90), not only point MSE;
- future MFE/MAE for both sides to supervise TP and SL distances;
- limit fill probability for a small set of entry offsets;
- holding/timeout target and regime/volatility auxiliary targets.

Labels may use future data; features never may. Use purged chronological walk-forward
splits with an embargo at least as long as the longest horizon.

### Recommended architecture sequence

1. Train logistic regression, LightGBM/XGBoost, and a small MLP on engineered
   multi-timeframe features. These are mandatory baselines.
2. Freeze Kronos-mini and cache pooled embeddings for each timeframe. Train a
   small cross-timeframe fusion head with gated attention.
3. Use separate heads for direction probabilities, return quantiles, MFE/MAE,
   limit-fill probability, and holding time.
4. Calibrate direction probabilities on validation (temperature or isotonic
   calibration) and learn an abstention threshold.
5. Derive entry/TP1/TP2/SL deterministically from calibrated outputs. Keep risk
   sizing outside the forecaster so it remains auditable.
6. Only if frozen embeddings beat all cheap baselines, unfreeze the final one or
   two Kronos blocks with a low learning rate. Do not redesign the tokenizer first.
7. Consider offline RL only after the supervised policy is stable; otherwise an
   RL reward will mostly exploit simulator artifacts.

### Colab deliverables to create

- `scripts/build_training_dataset.py` for deterministic Parquet splits;
- `configs/training.yaml` for all feature, label, cost, model, and seed settings;
- `notebooks/train_colab.ipynb`, runnable top-to-bottom on a Colab GPU;
- a packaging command that creates `artifacts/colab_bundle.zip` containing processed
  splits, manifest, config, and code but no secrets;
- checkpoint metadata containing Git SHA, data hashes, seed, validation metrics,
  calibration parameters, and feature schema;
- `scripts/evaluate_checkpoint.py` that evaluates an imported checkpoint without
  touching validation thresholds.

The Colab notebook should mount Drive only for input/output transfer, install pinned
requirements, verify hashes, train with mixed precision and early stopping, save the
best validation checkpoint, and export a small inference bundle back to this repo.

## 8. Acceptance gates

A coding agent may call a model a candidate only if a new untouched forward test has:

- positive net return after all specified costs;
- profit factor at least 1.15;
- at least 200 filled trades across multiple regimes;
- mark-to-market maximum drawdown no worse than 10%;
- calibrated expected calibration error no worse than 5%;
- performance that is not concentrated in one month, one direction, or a few trades;
- no material degradation under worse fill and slippage stress scenarios.

Leverage is a risk overlay, not a way to rescue a negative 1x strategy. Enable it
only when calibrated confidence buckets show monotonic out-of-sample expectancy.

## 9. Files worth reading first

- `AGENTS.md`: hard research and safety rules.
- `PHASE_A_RESULTS.md`: current feasibility summary.
- `configs/research.yaml`: current inference/execution defaults.
- `src/agentic_alpha_lab/models/kronos_adapter.py`: upstream model integration.
- `src/agentic_alpha_lab/backtest/engine.py`: compounding, costs, fills, funding,
  mark-to-market drawdown, leverage, and approximate liquidation.
- `src/agentic_alpha_lab/data/timeframes.py`: complete-candle aggregation.
- `scripts/generate_dashboard_data.py`: probabilistic multi-frame inference.
- `scripts/evaluate_confidence_leverage.py`: exploratory leverage comparison.
- `web/app/dashboard.tsx`: current visualization.

## 10. Definition of done for the next agent

Before handing off again, the agent must:

1. keep all existing tests passing and add tests for new leakage/cost logic;
2. record exact data ranges, hashes, seeds, model checkpoints, and cost assumptions;
3. report capital index, net return, mark-to-market drawdown, PF, trade count,
   coverage, long/short breakdown, fees, funding, and liquidation count;
4. distinguish train, validation, locked test, and exploratory/in-sample results;
5. update this file and `PHASE_A_RESULTS.md` with what changed and the exact next step;
6. never silently tune using a locked test result.
