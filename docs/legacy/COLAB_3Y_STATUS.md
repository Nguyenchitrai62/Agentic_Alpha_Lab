# Colab 3-year dataset handoff — 2026-09-05

## Completed locally

- Raw: `data/raw/binance_usdm/BTCUSDT/5m/history_3y_20260905.parquet`.
- 315,359 closed BTCUSDT Binance USD-M 5m candles, 2023-09-06 10:10 UTC
  through 2026-09-05 10:04:59.999 UTC.
- Downloader reports zero duplicates, gaps, invalid OHLC and non-positive prices;
  the training builder also passed its stricter finite/grid/closed-candle checks.
- Immutable dataset: `data/processed/btc_3y_20260905_v1`.
- Train 188,309 rows; validation 46,572; calibration 30,856; test 46,861.
- ZIP: `artifacts/colab_btc_3y_20260905_v1.zip` (56,638,714 bytes).
- ZIP SHA-256: `61454f820a077138de738d86dba45fc3a936c2dca4558d87387cf190c50b1e74`.
- ZIP excludes test and raw candles. Git ignore verified for raw, processed and artifacts;
  no tracked files were found under data/artifacts. No push was performed.

## Colab status

The Colab home UI was observed signed in to the user's explicitly requested account.
User permits either Chrome or the already-installed Google Colab VS Code extension.
Only free GPU is authorized: no paid plan, compute-unit purchase or quota bypass.

**NOT uploaded; GPU NOT allocated; training NOT started.** Browser control was
rejected by the tool approval service because Codex usage was exhausted. This says
nothing about Colab GPU availability. Resume after access is restored; do not
work around the rejection with another control mechanism.

## Resume

1. Read AGENTS.md, TRAINING.md and this file. Preserve existing dirty-worktree changes.
2. Open `notebooks/train_colab.ipynb` in the user's Colab account.
3. Select free GPU if offered; verify actual CUDA device. Stop if payment or quota bypass is needed.
4. Upload the exact ZIP above and execute the notebook in a fresh runtime.
5. Save/download checkpoint safetensors and metadata into a new ignored artifacts directory.
6. Compare validation/logistic baselines before deciding to open test. Do not search
   policies on test, and do not call this interval pristine: its recent portion was
   already inspected in previous experiments.
7. Evaluate imported checkpoint with the same immutable dataset and a new report path;
   preserve costs and capital 100 as described in TRAINING.md.

This bundle trains the existing engineered multi-timeframe MLP on longer history,
not a new Kronos architecture or RL. It is a data-quality baseline experiment, not
a promise of profitability. Tree baselines, walk-forward comparisons, improved
execution-aware labels and Kronos fine-tuning remain subsequent research tasks.
