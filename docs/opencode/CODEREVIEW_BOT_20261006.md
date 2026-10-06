# Bot code review 2026-10-06 — interaction bugs (PostOnly + risk guard, cycle timing + kline lock, carry sleeve, maintenance window + startup check)

Scope: `bot/run.py`, `bot/carry.py`, `bot/mirror.py`, `bot/paper.py`, `bot/bybit_v5.py`, `bot/risk_guard.py`, `docs/BOT_EXECUTION.md` CHANGES 2026-10-06, `tests/test_bot_*.py`, `tests/mock_bybit_v5.py`. No `bot/` code changed, no commits, no network, no orders. Failing regression tests: `tests/test_bot_review_carry_guard.py`, `tests/test_bot_review_runner_paths.py` (all fail on current code, each maps to a finding below).

## F1 — RISK GUARD REJECTS CARRY HEDGE-RECOVERY / TIMEOUT-CLOSE / DELIVERY-SALE MARKETS (high)
- `bot/carry.py:268-275` (`market_payload`, no `reduceOnly` on hedge retries / spot timeout-close / spot delivery sale) x `bot/carry.py:327-331` (`guard_carry` converts them to `Order(price=None, reduce_only=False)`) x `bot/risk_guard.py:271-273` (`_is_market` -> `market_not_reduce_only` reject).
- Scenario: carry opens with one leg filled (e.g. spot fills, fut IOC misses). Next cycle `decide` returns a fut `Sell Market` hedge (`op=carry_unhedged` logged), but `_carry_cycle` (`bot/run.py:611`) sends it through `guard_carry`, which rejects it. Same for the spot-leg retry `Buy Market`, the spot timeout `carry_close` `Sell Market`, and the delivery `carry_settle` spot `Sell Market`. Only the reduce-only fut `Buy` legs pass. Reproduced: `guard_carry` on a real `decide` retry returns `([], [{reason: market_not_reduce_only}])`.
- Effect: with the guard ON (default on testnet/live) a single-fill carry open can never re-hedge and a delivered pair can never sell its spot — the exact recovery/settlement path the sleeve depends on. Paper default (guard OFF) works, so paper is green while testnet/live is broken: a testnet/live-vs-paper divergence.
- Fix direction (leader decides): allowlist carry-hedge/close/settle markets in `guard_carry` (e.g. mark them carry-recovery and exempt from `market_not_reduce_only` while keeping the 0.30x cap + single/total caps), or make the retry/close/sale legs reduce-only where the exchange allows.

## F2 — SPOT CARRY FILLS INVISIBLE ON TESTNET/LIVE (high)
- `bot/bybit_v5.py:393` (`executions` hardcodes `category="linear"`) x `bot/run.py:499-502` (`_carry_sync` uses `self.ex.executions(start)` for ALL carry links incl. `spot`) x `bot/bybit_v5.py:390` (`open_orders` hardcodes `category="linear"`).
- Scenario: live/testnet carry spot `Buy` IOC fills (category spot). `_carry_sync` polls only the linear execution list, so the spot fill is never seen: `spot_filled` stays False while the fut leg fills -> perpetual `carry_unhedged` retries -> `carry_close` of the wrong leg, and physical spot stranded with no record. `PaperExchange.executions` returns all categories, so paper tests pass and hide this.
- Fix direction: poll spot executions too (category spot) in `_carry_sync`, or route carry sync through a category-aware execution fetch.

## F3 — NORMAL CYCLE HAS UNGUARDED `equity_usdt()` + `have()`; ONE BLIP ABORTS PROTECTION (medium)
- `bot/run.py:1038` (`equity = ... self.ex.equity_usdt()`, no try) and `bot/run.py:1133` (`have_before = self.have()`, no try). The ledger-only (no-plan) path guards both (`925-928`, `988-991`); the normal path does not.
- Scenario: one `equity_usdt` / `open_orders` exception (timeout, 10006 burst, partial response) raises out of `cycle()` — no TP/SL/market-exit placement, no carry pass, no `_store_cycle_timing`, state not saved. The ledger-only path for the same blip keeps protection running.
- Fix direction: wrap both calls like the ledger-only path (fall back to last equity / empty `have` + continue), log `op=cycle_error`-local, still reach `_store_cycle_timing`.

## F4 — OLD `state.json` DIP PIECES CRASH `desired()` (medium)
- `bot/mirror.py:392` (`frac = float(pc["frac"])`, direct) + `400` (`pc["dist"]`) + `301` (`v["qty"]`, `v["phase"]`, `v["symbol"]` direct). Old ledgers (pre-frac/dist fields) raise `KeyError` out of `cycle()` -> same abort as F3.
- Reproduced: `mirror.desired` on a dip piece without `frac` raises `KeyError: 'frac'`.
- Fix direction: `.get` with safe defaults (or a state-migration that backfills `frac/dist/planned_qty/entry_px` on load).

## F5 — PAPER PARKS UNFILLABLE IOCS AS RESTING ORDERS; LIVE CANCELS THEM (medium-low, paper/live divergence)
- `bot/paper.py:156-184`: `_ioc_try_fill` returns `None` when the ref price is unknown -> falls through to `self.s["orders"][link] = o` (rests). A real IOC is cancelled by the exchange when it does not cross.
- Scenario: first carry entry for a dated symbol before its `last_close` exists and with no ticker: paper rests the IOC and later fills it on trade-through (`_minute`); live cancels it. Reproduced: placing a dated IOC with empty `last_close` returns success and rests.
- Fix direction: `place` should return `None` (cancelled, no resting order) when an IOC does not cross, including the unknown-ref case.

## F6 — DUAL EXECUTION POLLS SHARE ONE CURSOR; A BOOK FILL CAN BE SKIPPED PAST (low-medium race)
- `bot/run.py:1041` (`sync_fills`) and `bot/run.py:578` (`_carry_cycle` -> `_carry_sync`) both consume `self.ex.executions(start)` keyed on the single `state["last_exec_ms"]`. `sync_fills` `continue`s past carry links without recording, `_carry_sync` `continue`s past book/dip links without recording, but each advances `last_exec_ms` past what the other skipped.
- Scenario: a book fill lands in the seconds between the two polls; `_carry_sync`'s fetch sees it, skips it, then advances `last_exec_ms` past it on a carry exec. Next cycle `sync_fills` starts after it — the fill is never applied to the ledger (missed TP/SL sizing, `plan_gone_since` drift).
- Fix direction: separate cursors (`last_exec_ms` vs `carry_last_exec_ms`) or advance the shared cursor only to execs actually processed by each consumer.

## F7 — `Bybit.executions(limit=100)` HAS NO PAGINATION (low)
- `bot/bybit_v5.py:392-393`: single page, no cursor. After downtime (restart looks back 3600 s) >100 execs in the window silently drops the oldest. `seen_exec`/`last_exec_ms` then jump past them.
- Fix direction: page with `endTime`/cursor until empty, or document the 100-exec/restart-gap limit.

## Checked and CLEAR (no bug found)
- Maint window vs carry: carry legs excluded from `_have_without_carry` (`run.py:184-190`), `_acts_without_carry_cancel` (`193-204`), `_maint_resting_entries` skips `c*` (`325-327`); `_carry_cycle` still runs during maint as documented. Carry entries during maint are intentional per doc (flagged as risk posture in N1 below, not a code bug).
- Maint window vs protection: only `kind == "entry"` filtered (`1117-1123`); TP/SL/backstop/market/time exits untouched; `maint_cancel`/`maint_resume` logging correct; resting entries cancel via normal `diff`.
- Maint vs `--adopt-fresh`: adopt orders are `kind == "entry"`, so they are blocked in maint and on stale/cached plans — correct (no fill without supervision).
- Risk guard vs maint order: maint filter runs before the guard (`1117` before `1129`), so blocked entries never pollute caps. Risk guard never blocks reduce-only protection (verified in `test_bot_testnetfix.py`).
- Startup `protection_check` vs carry: carry lives in `state["carry"]`, ledger scan only sees book/dip pids, `c*` links never collide with `pid+S/T` checks — no misread. Dip backstop (`pid+S`, kind stop) correctly counts as stop.
- Cycle-timing vs carry: carry runs after book/dip acts are placed and its latency is billed to `order_ms`; provisional+final state writes are heartbeat-only. No trading-behaviour impact.
- `MockBybitV5` spot/dated gap (test-only note): the mock ignores `category` and has no spot leg model, so F1/F2 pass in mock tests while failing live — carry runner tests should use a category-aware fake (as the new review tests do).
- Mock `equity_usdt` ignores spot holdings (paper counts them) — test-only divergence for guard caps, not production code.

## Non-blocking notes for the leader
- N1 (risk posture, not code): maint cancels dip/book entries so "no fill lands without its software stop" (outage runbook), yet carry entries (hedged pair, no stops) still fire inside maint. If the rationale is "no unsupervised fills during maint", carry should pause too; if carry is exempt by design, one line in `BOT_EXECUTION.md` saying so would close the question.
- N2: `bear_now` first-call fetch failure silently returns False (bull) with no log; consider logging the fallback.
- N3: carry `decide` with empty contracts/quotes returns `([], [])` silently; a throttled `carry_noquotes` log would help testnet triage.
- N4: `risk_guard` baseline ignores open carry notional for book/dip checks (carry state is not in the ledger). Total-gross can exceed `total_cap` across sleeves. If sleeves are meant to be additive-capped, pass carry notionals into the baseline.

## Testnet go / no-go
- NO-GO for a carry-enabled (`--carry-f`) testnet run until F1 (+F2 if spot legs are used): hedge recovery and spot settlement cannot execute with the guard on, and spot fills are invisible to `_carry_sync`.
- Book/dip-only testnet run: GO with caution — F3/F4 are crash-on-blip paths that cost protection for one cycle (exchange-native stops/TPs still rest), worth fixing first but not a hard blocker. F5–F7 do not affect book/dip testnet.
- Suggested order: fix F1 (guard allowlist for carry markets), F2 (spot execution poll), F3/F4 (defensive cycle + migration), then re-run this review's failing tests green + `test_bot_carry.py` + `test_bot_maint.py` + `test_bot_testnetfix.py` before testnet.
