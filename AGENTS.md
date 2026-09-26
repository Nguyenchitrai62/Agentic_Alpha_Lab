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

## User goal and validation protocol (user, 2026-09-27)

- Goal (mandatory): >= 5%/month compounded net with drawdown <= 20%, trading only the majors BTC, ETH, SOL, BNB,
  XRP (Binance USD-M perps; account < 10k USDT, so limit orders on majors carry no size slippage).
- Realistic simulation = the walk-forward replay: pretend "now" is the anchor date, freeze everything, run the
  pipeline continuously over every candle of the following year and score it. The most recent year
  (2025-09-24 .. 2026-09-23) plays "one year ago -> now"; the five anchors 2021-2025 repeat the same simulation. A
  candidate must pass in general (the 5-year walk-forward and the most recent year) before any real money.
- Prospective paper logs (`scripts/advisor_shadow.py`, `scripts/dip_sleeve_forward.py`) add evidence on data that did
  not exist when the rules were frozen.
- Selection rule (user-approved 2026-09-27): compare and choose variants ONLY on the first four walk-forward years
  (anchors 2021-2024). The most recent year is scored once, at the end, for the frozen finalist; it is never used to
  pick between variants. Versions that already looked at the last year need the prospective log as clean evidence.
- Gate (user-approved 2026-09-27): (a) 5-year walk-forward geometric mean >= 5%/month, (b) the most recent year alone
  >= 5%/month, (c) no losing year; and drawdown <= 20% over the full path (max of 4h-close and 1m-marked DD).
- Pre-register at most 2-3 variants per research direction, then close the direction.
- Gate cost model (user's real trading, Bybit, 2026-09-27): entries and take-profits are limit orders (maker 0.02%),
  stop/market exits are taker 0.04% (user's tier); no extra slippage term. Funding is deliberately adverse: longs pay
  0.01% every 8h, shorts receive nothing (this also stands in for small slippage). The carry sleeve depends on short
  funding income, so it earns nothing under this rule. Actual signed funding may be reported only as a labelled
  side row.

## Current execution assumptions (research engine `research/parallel/rounds/parallel-20260906-r2/engine_real`)

- Binance USD-M perps BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT; decisions at closed 4h bars; execution and
  intrabar risk on 1m klines (public archive).
- Book orders: limit 10 bps better than the minute-0 price, resting 60 minutes; maker 0.0002 only on a 1m
  trade-through, otherwise a market order at the minute-60 open (gate: taker 0.0004, no slippage term). Do not claim
  queue position from OHLC.
- Dip-sleeve orders: resting limit bids filled only on a 1m trade-through (maker 0.0002); exits by take-profit limit
  (maker) or by market at the next 4h open (gate: taker 0.0004).
- Funding (gate): longs pay 0.0001 per 8h settlement held, shorts zero (user rule above). engine_real's actual
  signed funding (longs pay positive rates, shorts receive them) is a labelled side row only. Carry sleeve: spot 0.001
  + perp taker per leg switch; no funding income under the gate rule.
- Capital: compounded from current equity (indexed to 100); cross-margin budget (spot cash + perp gross / leverage
  setting <= 95% of equity); Binance minimum notional per symbol; liquidation check on 1m marks when leveraged.
- Drawdown for the gate = max(4h-close full-path DD, 1m-marked full-path DD including open positions).
- Cost stress row: maker 0.0004 / taker 0.0007 + 5 bps on taker fills (robustness report).
- Keep fixed 1x as the baseline and report leveraged variants separately.
- User rule (2026-09-27): leverage above 2x is allowed when the model's confidence is high, but only if it is
  evaluated as realistically as possible: Binance USD-M cross margin (initial margin at the account leverage setting,
  maintenance margin per symbol, an account liquidation check on 1m marks), funding and fees on the full notional,
  and the DD <= 20% gate (max of 4h-close and 1m-marked DD) still holds. Trading stays majors-only
  (BTC, ETH, SOL, BNB, XRP).
- When stop and take-profit are both touched inside one OHLC bar, use stop-first.
- Legacy (pre-2026-09 BTC 5-minute engine `ohlc-v2`, flat funding 0.0001/8h longs, zero short funding, close-sampled
  DD, Phase A reports): do not mix those results with engine_real results without explicit labels.

## Development

- Latest user compute preference (2026-09-06): heavy training must use private
  Kaggle CLI/free GPUs. Use the local GTX1650 for inference, replay and backtests;
  do not launch another heavy local training job. Check existing cloud jobs and
  quota before submitting, preserve checkpoints, keep credentials out of bundles.

- On this Windows host, import `torch` before `pandas` in GPU entry points to avoid a DLL load-order failure.
- Run `.venv/Scripts/python.exe -m pytest` before handing off changes.
- Keep downloaded data, checkpoints, predictions, and reports out of Git.
- User rule (2026-09-26): commit code/docs only. Trained deployment models live locally in `models/frozen/`
  (gitignored; see `models/frozen/manifest.json`); logs, result JSONs and audit CSVs stay local too.
- Exception: the existing public dashboard demo snapshots are tracked, explicitly dated, and research-only.
- Read `TRAINING.md` for the working Colab/baseline loop and the already-opened smoke-test interval.
- Prefer small, versioned experiment configs over agent-authored ad hoc parameter changes.
