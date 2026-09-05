# Agent rules

## Scope

This repository is a research and paper-trading environment. Do not place live
orders or add authenticated exchange trading without an explicit user request.
The sibling `../Kronos` repository is upstream reference code and must not be
modified from this project.

## Non-negotiable research rules

1. A feature at candle `t` may use only data available after candle `t` closes.
2. A signal created at `t` cannot fill before candle `t+1`.
3. Fit normalization, labels, calibration, and thresholds on train/validation only.
4. Use chronological splits with an embargo at least as long as the forecast horizon.
5. Never tune on a locked test. Once inspected, that interval becomes research data.
6. Report gross PnL, fees, funding, net PnL, drawdown, trade count, and coverage.
7. Persist the data range, model/checkpoint, parameters, costs, and execution assumptions.

## Current execution assumptions

- Binance USD-M `BTCUSDT`, closed 5-minute candles.
- Limit entry begins on the next candle and expires after the configured number of bars.
- Fee is `0.0002` per entry/exit fill (0.04% round trip).
- Long funding is `0.0001` every 8 hours; short funding is zero by user assumption.
- Capital is compounded from current equity and reported with initial capital indexed to 100.
- Keep fixed 1x as the baseline; report confidence-based leverage separately and cap it at 2x until validated.
- When stop and take-profit are both touched inside one OHLC bar, use stop-first.
- Do not claim maker fill probability or queue position from OHLC alone.

## Development

- On this Windows host, import `torch` before `pandas` in GPU entry points to avoid a DLL load-order failure.
- Run `.venv/Scripts/python.exe -m pytest` before handing off changes.
- Keep downloaded data, checkpoints, predictions, and reports out of Git.
- Prefer small, versioned experiment configs over agent-authored ad hoc parameter changes.
