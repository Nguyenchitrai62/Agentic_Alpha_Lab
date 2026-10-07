# Straddle paper ledger — weekly short straddle on REAL Bybit quotes (2026-10-07)
Rule (frozen, sha at loop start): Fri 08:05-08:59 UTC sell 1 ATM call+put on the NEXT-Fri 08:00 expiry (K = listed strike nearest S, ties -> lower) at BEST BID each leg (no bid -> skip coin); q = 0.5·f·E/S floored to the lot step (0 -> skip). SL every hourly run at -1.0x premium, TP on 4h-close runs (00/04/08/12/16/20) at 0.3x premium, both buy back at ASK + taker fee min(0.0003·S, 0.07·price) (TP also logs a mark-based maker side field); else settle at delivery price (index-mean fallback, labelled) + delivery fee min(0.00015·S, 0.125·intrinsic). Weekly research row: BS premium at 0.97x DVOL (Deribit public index, last closed 1h candle).
Leader start (hourly loop, like the carry loop — worker never starts it):
`.venv\Scripts\python.exe scripts/straddle_paper.py --equity 5000 --f 0.25 --tag straddle` (loops 3600 s; state `artifacts/bot/paper_straddle/`)
Test: `... --once --dry-run` (writes nothing).
Files: `scripts/straddle_paper.py` (ledger), `tests/test_straddle_paper.py` (11 tests, mocked HTTP, pass), state `artifacts/bot/paper_straddle/state.json` + `actions.jsonl` (loop-created, untracked).
Position fields: coin, call/put_symbol, K, S_ref(+source), q, premium, entry_fees, bid/ask/mark + bid/mark IV per leg, dvol_at_entry, bs_premium_097dvol, week, expiry_ms, unrealised (marked at MARK). History adds reason sl|tp|expired, close asks/fees, maker_side_cost (TP), S_settle+source, realised_pnl. Hourly equity_mark (same-hour upsert, restart-safe) + totals {n_entered, n_skipped, realised_pnl, fees_paid}.
Public GET only: Bybit `/v5/market/*` + Deribit index; keyless `Bybit(None, None)`; retry/backoff, errors logged, exit 0; idempotent per week (`entered_weeks`, no double entry).
Live `--once --dry-run` 2026-10-07 (Wed): `open=0 entered=0 settled=0 ... no entry window`, state written False. rule_sha256=00697cd7….
Note: default 5000×0.25 = 625 USDT/coin -> BTC qty 0.0074 < 0.01 lot step, so BTC skips until equity grows; ETH (0.1 step) trades. First possible entry Fri 2026-10-09 08:05 UTC.
Tests: `.venv\Scripts\python.exe -m pytest tests/test_straddle_paper.py -q` -> 11 passed.
