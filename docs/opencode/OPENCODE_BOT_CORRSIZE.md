# OpenCode task: correlation-aware dip sizing + risk multiplier in the order-mirror bot (read AGENTS.md, OPENCODE_VF_COMMON.md, docs/BOT_EXECUTION.md)

Scope: edit ONLY bot/mirror.py, bot/run.py, bot/paper.py (if needed) and tests/test_bot_mirror.py. Keep every existing behaviour the DEFAULT
(new options off -> identical orders; all existing tests must pass unchanged). No live trading, no keys, no commits, do not touch the backend.

Research result to implement (registry v399 / v400 candidate R2B1_130): at the minute a dip rung of coin a could fill, its size is multiplied by
1 / (1 + n), n = number of OTHER majors whose last CLOSED 1-minute close is at least 2.5 sigma_4h below THEIR own current bar open (same
phase / sub-book); additionally every size (book weights and dip rung sizes) is multiplied by a risk multiplier k (1.3) and the dip risk
budget becomes 0.26 * k.
1. mirror.py: add `corr_mult(plan_dips_for_phase, last_close: dict, a_sym) -> float` deriving each coin's bar open and sigma from the plan's dip
   rows of that phase (buy_limit = open (1 - k sigma), stop = buy_limit (1 - 4 sigma) -> sigma = (1 - stop / buy_limit) / 4,
   open = buy_limit / (1 - rung * sigma); use any rung row of that coin and phase), counting coins b != a with last_close[b] <= open_b (1 - 2.5
   sigma_b). Add parameters `risk_mult=1.0, corr=False, last_close=None` to `desired(...)`: book entry / add qty x risk_mult; dip bid qty x
   risk_mult x (corr_mult if corr else 1); budget = BUDGET x risk_mult; the budget admission keeps using the UNSCALED-by-corr cost (shallow-first as
   now) so that the corr factor only shrinks size.
2. run.py: CLI flags `--risk-mult` (default 1.0), `--corr-size` (default off) and `--tag` (state dir artifacts/bot/<mode>[_<tag>], default no
   tag -> unchanged paths); in paper mode pass the paper exchange's last_close; in testnet/live/dry fetch the last closed 1m close per symbol
   from Bybit public klines (interval 1, limit 2, take the closed bar). Resting bids get amended when the multiplier changes (the existing diff /
   amend path handles qty changes only for tp/stop: extend it so entry orders of kind 'entry' with a different qty are amended too, ONLY when
   corr or risk options are on).
3. tests: corr_mult on a synthetic plan (0, 1, 3 other coins flushing), desired() with risk_mult 1.3 (qty x 1.3, budget scaled), default-off
   equality with the old outputs, amend of a resting bid when n changes.
Run `.venv/Scripts/python.exe -m pytest -q tests/test_bot_mirror.py` and report. Write a short CHANGES note at the end of docs/BOT_EXECUTION.md.
