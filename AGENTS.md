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
- Robust selection criterion (leader, 2026-09-27, applies to directions registered from v204 on; never retroactive):
  among variants with DD <= 20% and no losing year in the first four years, prefer those whose first-four-year mean is
  >= 5%/month (if any), and among them pick the highest WORST-YEAR monthly return of the first four years; ties -> the
  higher mean. Rationale: dev-mean improvements (v189-v197) did not transfer to the most recent year.
- Every trade must be structured like real trading (user rule 2026-09-27): limit entry, a stop-loss (market, taker
  0.055%) and a take-profit (limit, maker 0.02%) attached to every position, so a move against the forecast cannot cause
  an unbounded loss. Book entries/rebalances are limit orders; an unfilled limit expires (no market fallback for
  entries). If stop and take-profit are both hit in the same 1m bar, assume the stop first.
- ZERO DATA LEAKAGE (user rule 2026-09-27): features at t use only data available at the close of t; labels,
  normalisation, calibration, thresholds, model and parameter selection use only data before each anchor minus an
  embargo >= the horizon; no statistic computed on a test year (or the most recent year) may feed back into any choice;
  every blind audit must explicitly check feature timing, label windows, fit windows and fill timing.
- Gate cost model (user's real trading, Bybit, 2026-09-27): entries and take-profits are limit orders (maker 0.02%),
  stop/market exits are taker 0.055% (Bybit VIP0); no extra slippage term. Funding is deliberately adverse: longs pay
  0.01% every 8h, shorts receive nothing (this also stands in for small slippage). The carry sleeve depends on short
  funding income, so it earns nothing under this rule. Actual signed funding may be reported only as a labelled
  side row.

## Current execution assumptions (research engine `research/parallel/rounds/parallel-20260906-r2/engine_real`)

- Binance USD-M perps BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT; decisions at closed 4h bars; execution and
  intrabar risk on 1m klines (public archive).
- Book orders: limit 10 bps better than the minute-0 price, resting 60 minutes; filled (maker 0.0002) only on a 1m
  trade-through; an unfilled order expires and the position stays as it was until the next decision. Every book
  position carries a stop-loss (market, taker 0.00055) and a take-profit (limit, maker 0.0002). Do not claim queue
  position from OHLC. (engine_real's taker fallback at minute 60 is a legacy research convention.)
- Dip-sleeve orders: resting limit bids filled only on a 1m trade-through (maker 0.0002); exits by take-profit limit
  (maker) or by market at the next 4h open (gate: taker 0.00055).
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
- Exception: the old public dashboard demo (`archive/legacy_web_dashboard/`) snapshots are tracked, dated, research-only.
- Web app: `backend/` (FastAPI + SQLite, runs on this machine, port 8724, exposed by a Cloudflare tunnel) and
  `frontend/` (static site deployed by the user on Vercel). Secrets (Google client id, session secret, admin emails)
  live only in the local `.env`; never commit them.
- Legacy docs (Colab/baseline loop, Kronos, older result reports) live in `docs/legacy/` and `docs/research_reports/`;
  OpenCode assignments and the shared worker rules (`OPENCODE_VF_COMMON.md`) live in `docs/opencode/`.
- Prefer small, versioned experiment configs over agent-authored ad hoc parameter changes.
