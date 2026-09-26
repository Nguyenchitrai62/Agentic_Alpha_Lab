# Forward-log paper scorer (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)

Write only: `scripts/forward_scorer.py` (new) and `tests/test_forward_scorer.py` (new). Do not edit any other file.

Goal: score the prospective advisory log `artifacts/research/advisor_shadow/shadow.jsonl` as paper trading, per candidate.

Input rows (JSON lines): every row has `candidate`, `decision_bar_close` (UTC, end of a closed 4h bar), `logged_at`, `mode`.
Use only rows with `mode == "prospective"`. Weight formats:
- portfolio candidates (`v99_models_portfolio`, `v104_*`, `v115_*`, `v127_*`, `v133_*`, `v144_*`, `v151_*`, `v154_*`,
  `portfolio_v1_3book`): `perp_weight` {SYMBOL: fraction of equity, signed} and `spot_weight` {SYMBOL: fraction}. The
  spot legs are the carry hedge (spot long + perp short already netted inside `perp_weight`); score perp weights as the
  directional exposure and spot weights as long spot exposure.
- BTC single-asset candidates: `target_fraction` (fraction of equity in BTCUSDT perp) or `size_fraction_of_equity` with
  `target_position` (sign); treat as the BTCUSDT perp weight.
Execution convention (same as the research engine): a row decided at bar close T holds from the open of the next 4h bar
(T + 1 ms) until the next logged decision of the same candidate replaces it; returns come from Binance USD-M 4h opens
(fetch with `agentic_alpha_lab.data.binance_usdm.fetch_klines`, public REST, no keys) and Binance spot 4h opens for spot
legs (`https://api.binance.com/api/v3/klines`). Costs: 0.0002 per unit of weight change (maker-like), long funding
0.00005 per 4h bar on long perp gross. If a candidate has a gap (missing bar), keep the previous weights.
Governor: for candidates whose `note` contains "UNGOVERNED", ALSO report a governed version: multiply the weights by
g = clip((0.20 - DD)/0.10, 0, 1) where DD is the paper equity drawdown from its 90-day peak lagged 2 bars (v110 rule).
Output: `python scripts/forward_scorer.py` prints and writes `artifacts/research/advisor_shadow/forward_score.json` with,
per candidate: first/last decision, number of decisions, bars held, cumulative net return %, max drawdown %, turnover,
and (if applicable) the governed figures. Unpriced bars (the latest bar whose next open is not yet available) are skipped.
Tests: synthetic log + synthetic prices (no network) checking timing (no fill before the next open), cost and funding
arithmetic, gap handling and the governor. Run `.venv/Scripts/python.exe -m pytest tests/test_forward_scorer.py`.
Do not place orders, do not use credentials, do not edit leader files.
