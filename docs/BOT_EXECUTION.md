# BOT execution: order mirror for R2-4P (Bybit USDT perps)

`bot/` turns the merged multi-phase paper plan (`artifacts/research/advisor_shadow/trade_plan_v376.json`, refreshed hourly by the backend)
into exchange orders. Logic: `bot/mirror.py` (pure, tests in `tests/test_bot_mirror.py`); exchange client: `bot/bybit_v5.py`; loop: `bot/run.py`.

## Modes
- `python -m bot.run --once --equity 2000` - DRY RUN: prints the orders that should rest now (public market data only, sends nothing).
- `python -m bot.run --mode testnet` - Bybit TESTNET, every 20 s. Put `BYBIT_TESTNET_API_KEY` / `BYBIT_TESTNET_API_SECRET` in `.env`
  (testnet keys from testnet.bybit.com; never commit them).
- `python -m bot.run --mode paper --equity 5000` - PAPER: the same bot against a simulated account filled from LIVE Bybit 1m klines
  (`bot/paper.py`: trade-through limits, stop-first, taker market / stops, adverse long funding); prospective evidence for the whole bot
  stack without keys. Running since 2026-10-05 04:46 UTC (state `artifacts/bot/paper/exchange.json`, log `runner.log`; one runner per mode,
  OS lock `runner.lock`).
- `--mode live` is LOCKED: it needs `BYBIT_API_KEY` / `BYBIT_API_SECRET` in `.env` AND `BOT_ALLOW_LIVE=yes-real-money` set by the
  account owner. Start live only after a clean testnet run and with a small account.

## Rules implemented (same as the research engine)
- Hedge mode: longs positionIdx 1, shorts 2 (a sub-book short never nets against a long dip rung).
- Book entries: PostOnly limits (maker-only, as the research fill rule) from minute 5 after the plan's issue time until `valid_until`; a crossing limit is rejected (logged `postonly_reject`) and retried next cycle, never chased.
- Every filled piece gets its own reduce-only exits: book = conditional market stop at the plan SL + limit TP (amended when the plan moves
  SL/TP, e.g. break-even / tighten); plan add / reduce / close = limit orders.
- Dip rungs: limit bids from minute 16 to the bar end, admitted shallow-first inside each sub-book's risk budget (0.26 x sub capital,
  stop distance + 2 %), TP limit + 8-sigma native backstop on the exchange, 4-sigma stop on a CLOSED 5m bar close (bot market exit), time
  exit at the bar end (market).
- The exchange is the truth for open pieces: when the paper plan has exited a book position that is still open on the exchange, the bot
  closes it at market after 3 minutes (logged `plan_closed_divergence`).
- Safety: a plan older than 4h30m blocks new entries (exits keep running); orders below Bybit lot / notional minimums are skipped and logged
  (at ~2000 USDT some BTC rungs are below 0.001 BTC; see the small-account study).

State: `artifacts/bot/<mode>/state.json`; every action: `artifacts/bot/<mode>/actions.jsonl`.
Known caveats: plan levels come from Binance prices (Bybit within ~2 bps, BNB ~10 bps cheaper on Bybit); the backend must run
for fresh plans; a new fill has no exit orders until the next cycle (<= 20 s) places its stop and TP.

## CHANGES (bot_bookgap: dust + in-flight double-spend, mirror-only, default behaviour)
- `mirror.apply_fill` clamps ULP-level remainders (<= 1e-9 of the piece size) to exactly 0, so a closed piece never
  refires market exits every 2 minutes (parity window: one 1.5e-12 XRP leftover alone caused 3,781 futile placements).
- `mirror.desired` emits no other order (TP/stop/reduce/add/entry-remainder) for a piece with a market exit in flight
  (`exit_sent` < 2 min old): the market exit and a resting TP could otherwise both fill for the full piece qty out of
  the shared (symbol, positionIdx) net, spending other pieces' balances and stranding victims in an exit-retry loop
  (parity window: 25,435 exit placements for 143 fills). Stale markers restore protection, so a failed exit never
  disarms a piece. NOTE: `tests/test_bot_resilience.py::test_1` and `::test_6` still assert the old behaviour
  (protection rests alongside a fresh market exit) and need updating to the fixed behaviour.

## CHANGES (v399/R2B1_130: correlation-aware dip sizing + risk multiplier, default off)
- `mirror.corr_mult(dips_of_phase, last_close, a) = 1/(1+n)`: n = other majors in the same phase whose last closed 1m
  close <= open_b*(1-2.5*sigma_b), with open/sigma from any rung row (`sigma=(1-stop/buy_limit)/4`,
  `open=buy_limit/(1-rung*sigma)`). `desired(..., risk_mult=1.0, corr=False, last_close=None)`: book entry/add qty x
  risk_mult; dip qty x risk_mult x corr_mult (when corr); budget `BUDGET x risk_mult` with UNSCALED-by-corr admission
  (shallow-first), so corr only shrinks size. Defaults keep every order identical.
- `run.py`: `--risk-mult` (default 1.0), `--corr-size` (default off), `--tag` (state dir
  `artifacts/bot/<mode>[_<tag>]`, default unchanged); paper passes the paper exchange `last_close`, other modes fetch
  the last closed 1m close per symbol (Bybit klines interval 1, limit 2, closed bar). Resting `entry` bids are amended
  on qty change ONLY when corr/risk options are on (`diff(..., amend_entry_qty=True)`; tp/stop amend as before).
- Bear-regime book filter (registry v410, R2B1D18BF; default off): `mirror.is_bear(opens)` is True while the latest
  BTCUSDT 4h bar OPEN < the mean of the last 1200 4h opens including it (min 600); `desired(..., bear_book=False,
  bear=False)` halves book ENTRY/ADD qty on the LONG side only when both flags are set (shorts, reduce/close/tp/stop,
  dips unchanged). `bybit_v5.Bybit.klines_4h_opens(symbol, n=1200)` pages the public kline endpoint (interval 240,
  limit 1000, `end` cursor) oldest-first; `run.py --bear-book` recomputes bear from BTCUSDT every 10 minutes (cached)
  and logs `op='bear_state'` on change.
- Closed gap (2026-10-05, bot_beartrim): `--bear-book` halves NEW book long entries / adds in the bear regime; the research engine (v410) halves the book
  long TARGET; the bot now also trims each open book long once per bear episode to half its plan size with one reduce-only limit.
- Dip stop-cascade controls (registry v417 rows C/X, default off): `run.py --dip-cooldown-h H` (default 0) records each dip
  stop-out (bot close5 market exit or native backstop fill; TP / time exits never) as `stop_exit_t` on its piece via
  `mirror.note_dip_stop`, and `desired(..., dip_cooldown_h)` places no NEW dip rung of the same coin+phase whose bar open B
  satisfies s < B <= s+H (open pieces keep TP/backstop; same-bar B <= s unaffected). `--dip-sl-coin SYM=M` (repeatable)
  replaces the 4-sigma dip close-stop for that coin (`mirror.dip_stop_price`, budget `frac*(M*sigma+GAP)`; backstop 8 sigma
  unchanged). Defaults reproduce every old order bit-for-bit.
- Dip gross-notional cap (research v421 G2 / v422 engine hook `sleeve_gross_cap`, default off): `run.py --dip-gross-cap G`
  (default 0 = off) keeps, per phase sub-book, every resting dip entry bid at min(its normal size, room) where
  room = G x sub equity - OPEN filled dip notional of that phase (NOT minus other resting bids, recomputed every
  cycle so bids shrink after a fill; resting bids amend qty down/up, never chase price). This mirrors the engine,
  which only cuts a rung at its fill minute to (G - notional of rungs open at that minute). Residual risk: several
  bids filling inside one cycle can exceed G by at most the sum of their sizes (the engine cannot see within a minute
  either); hard safety bound: open + resting dip notional <= 2 x G x sub equity (shallow-first, rarely binds).
  Book orders and protection (tp/stop/reduce) are never touched.
  (bot_capfix 2026-10-06: the previous cumulative room allocation counted resting bids against each other and cost
  2.46pp on 2026-09-01..23 (C +1.12 % vs +3.58 % uncapped); the engine-faithful cap costs 0.38pp (C +3.20 %,
  dips 261 vs 271 uncapped; see research/diagnostics/bot_capfix/REPORT.md).

## CHANGES (bot_adopt: optional --adopt-fresh, default off)
- `python -m bot.run --adopt-fresh`: when a phase sub-plan holds a book POSITION the bot does not hold for that
  (phase, symbol) and the plan position is fresh, place the SAME limit the engine had (side from
  `position.side`, price = `position.avg_entry`, size = `position.weight` x equity / price with the usual
  risk_mult / bear-book halving, valid until the window end; GTC like any book entry) with its stop/TP attached
  (`position.sl`/`position.tp`). Plan fields: `position.opened` = the engine holding-bar start (= entry bar close,
  e.g. `2026-10-04 12:00:00+00:00`) and `position.avg_entry` = the engine limit price; window = opened + 5 min ..
  opened + 65 min (the engine 60-min book entry window from minute 5). Fills only on a later trade-through (no
  chasing); after the window it cancels like any expired entry. Never adopts older positions, never market-enters,
  never adopts dips. Default off reproduces every old order bit-for-bit.

## CHANGES (bot_testnetfix 2026-10-06: PostOnly entries + wired risk guard)
- F1: book entries / adds and dip rung bids are sent `timeInForce:"PostOnly"` (maker-only, as the research fill rule
  and `bot/paper.py` assume); reduce-only TP / reduce limits stay GTC; stops / market exits unchanged. A crossing
  PostOnly is rejected (paper returns None, live raises PostOnly 110079/170146): logged `op=postonly_reject` and
  retried next cycle at the same price, never converted to market/taker.
- V4: `bot/risk_guard.check()` filters `want` after stale/plan_error trimming and before rounding/`diff` in both
  `Runner.cycle` paths (normal + ledger-only), with exchange equity, ledger positions and last prices (closed 1m
  closes falling back to 5m closes / plan marks), default limits per-coin 2.5x / dip 2.0x / total 4x / single 1x.
  Rejects log `op=risk_reject` and are not sent; protection / reduce-only never blocked. Flag `--no-risk-guard`
  disables in testnet/live (guard ON there by default); in paper/dry the guard is OFF unless `--risk-guard` (leader 2026-10-06: paper stays engine-faithful, e.g. uncapped R2-4P dip gross can exceed 2.0x).
- `tests/test_bot_testnetfix.py` covers both; `test_bot_mirror` entry payload updated to PostOnly.

## CHANGES (bot_opsfix 2026-10-06: shared kline cache + quiet skip log, default behaviour unchanged)
- Shared public-kline cache `artifacts/bot/_kline_cache/<SYMBOL>.json` (TTL 20 s, file lock, existing 10006 backoff kept):
  `last_close_1m`, paper `step()` 1m fills and the bear `klines_4h_opens` check all read through it, so N runners on one
  machine make ~1 request per symbol per TTL; miss path fetches exactly as before.
- `skipped_below_minimum` now logs once per (link, 4h bar) instead of every 20 s cycle (tests/test_bot_opsfix.py).

## CHANGES (bot_cycletime 2026-10-06: cycle timing + bounded cache lock, default behaviour unchanged)
- `Runner.cycle` measures wall time per stage (`plan_ms, kline_ms incl. cache lock wait, sync_ms, decide_ms, order_ms, state_ms`)
  and writes `last_cycle_ms + last_cycle_stages_ms (+ last_cycle_lock_wait_ms)` into state.json every cycle (two writes:
  provisional then final with the measured state_ms). One `op=slow_cycle` (with the stage breakdown) logs when a cycle
  exceeds 60 s; one `op=lock_wait` logs when the accumulated kline-cache lock wait exceeds 10 s. Normal fast cycles log
  nothing extra, orders bit-for-bit identical.
- `bot/bybit_v5._kline_locked` now bounds the acquire (`KLINE_CACHE_LOCK_TIMEOUT_S=30 s`, warn `10 s`, wait accumulated
  for `pop_kline_lock_stats()`): on timeout it yields unlocked and the caller falls back to a direct fetch (get -> miss,
  put/merge -> skip the write), still never raising. POSIX previously blocked indefinitely; Windows keeps its
  non-blocking spirit with a bounded retry. `cached_call / kline_cache_get-put / cached_1m_rows` accept `lock_timeout`.
- `scripts/bot_health.py` shows `cycle_ms=<s>` from `last_cycle_ms` and flags WARNING when > 60 s.
- Tests: `tests/test_bot_cycletime.py` (fake `_cycle_now` clock for slow_cycle, injected lock wait, real held OS lock with
  a short timeout for the direct-fetch fallback, health warning).

## CHANGES (bot_carry 2026-10-06: cash-and-carry sleeve, default off)
- Opt-in `python -m bot.run --carry-f F` (default 0 = off, orders bit-for-bit unchanged when off): per coin
  (BTC, ETH) the SAME frozen rule as `scripts/carry_paper.py` (imports its `RULE_PARAMS` and
  `is_quarterly_delivery`, never re-defined): flat + roll due (no open pair and the front quarterly has
  <= 7 d left, or first availability) + annualised basis ln(F/S)*365/DTE >= 4 %/yr -> spot BUY (category
  spot, limit at the ask, IOC) + quarterly SELL (category linear/inverse as listed, limit at the bid,
  IOC), each leg notional = F x equity, equal coin quantity, bot-owned link ids with prefix `c`.
  Single-fill opens retry the missing leg at market next cycle (`op=carry_unhedged`); never left unhedged
  > 2 cycles, otherwise the filled leg is closed (`op=carry_close`). Held to delivery; after delivery the
  spot leg is sold at market (plus a safety reduce-only futures buy-back for sim accounts where dated
  shorts do not auto-settle) and realised P&L is logged (`op=carry_settle/carry_settled` via the frozen
  `realised_pnl_pair`). All carry orders pass through `risk_guard` (extended allowlist for dated symbols;
  extra cap: futures short notional <= 0.30 x equity per coin, `op=carry_cap`/`risk_reject`) and are never
  counted in the dip gross cap. Paper fills: spot + dated futures on 1m trade-through like every other
  paper order (`bot/paper.py`: physical spot vs cash, dated shorts like perps, no short funding).
  Live note: `Bybit.place` hardcodes linear, so carry posts via `post()` with the leg category; spot IOC
  legs do not rest, so the preflight `^[bd]` link regex still sees no resting `c` orders in practice.
  Tests: `tests/test_bot_carry.py` (entry, skip < 4 %, partial-hedge recovery, delivery settlement,
  flag-off no-change, all through `tests/mock_bybit_v5.py`).

## CHANGES (bot_maint 2026-10-06: opt-in maintenance window + restart protection check, default off)
- `python -m bot.run --maint-start ISO --maint-end ISO` (UTC) or a per-cycle file
  `artifacts/bot/<mode[_tag]>/maintenance.json` (`{"start": ISO, "end": ISO}`; present-but-empty = cleared):
  from 30 minutes before start until end the bot places NO new dip bids and NO new book entries
  (`mirror` kind `entry` filtered after stale/plan_error trimming, before the risk guard) and cancels its
  resting dip bids + unfilled book entry limits via the normal `diff` (logged `op=maint_cancel` with
  `blocked_new`/`cancel_resting`; `op=maint_resume` once on exit). Protection (TP/SL/backstops, market exits,
  time exits) and carry legs (`c*` links, `_carry_cycle` still runs) are untouched. No flags and no file =
  inactive, orders bit-for-bit identical. Rationale: `research/tournament/oc_outage/REPORT.md` (routine outages
  are cheap; cancel resting dip bids before PLANNED maintenance so no fill lands without its software stop).
- Startup check after every restart: `Runner` logs `op=protection_check` (`open` pieces, `missing` without a
  resting stop+TP, verified against live open orders). A missing backstop/TP is the existing CRITICAL line in
  `scripts/bot_health.py` (`unprotected`); after unplanned downtime confirm it is empty before touching anything.
- Tests: `tests/test_bot_maint.py` (fake clocks for the 30-min pre-window boundaries, `tests/mock_bybit_v5.py`
  for cycle/cancel/protection/carry behaviour).

## CHANGES (bot_reviewfix 2026-10-06: code-review F1-F7 + N1-N4, book/dip defaults bit-for-bit unchanged)
- F1: carry hedge-recovery / timeout-close / delivery spot-sale markets marked carry-recovery in `carry.guard_carry`
  (futures legs stay reduce-only where the exchange allows: timeout Buy + delivery Buy already are); `risk_guard`
  exempts carry-recovery from `market_not_reduce_only`, keeping 0.30x carry cap + single/per-coin/total caps.
- F2: `Bybit.executions/open_orders` take `category` (default linear); `_carry_sync` polls linear+spot+inverse and
  `have()` aggregates them (paper/old fakes fall back to one call, deduped); spot fills now mark `spot_filled`.
- F3: normal-cycle `equity_usdt()` / `have()` (+`sync_fills`) wrapped like the ledger-only path (fallback + local
  `op=cycle_error` log, still reaches `_store_cycle_timing`); one blip no longer aborts protection.
- F4: `mirror.desired` uses `.get` defaults for old dip pieces (`frac/dist/planned_qty/entry_px/phase/symbol`);
  pre-frac ledgers no longer raise `KeyError` (budget contribution 0, protection still emitted).
- F5: paper IOC with unknown ref price is cancelled (never rests), matching live IOC behaviour.
- F6: separate execution cursors (`last_exec_ms` book/dip vs `carry_last_exec_ms` carry, each advancing only past
  execs it processed); new race test proves a book fill between polls still reaches the ledger.
- F7: `Bybit.executions` paginates `nextPageCursor` until empty (cap 10 pages, limit<=1000); >100-exec restart gaps
  no longer silently drop the oldest.
- N1: no NEW carry entries inside the maintenance window (recovery/close/settlement still allowed; blocked entries
  logged `op=maint_cancel/carry_blocked`); `test_bot_maint` updated to the N1 behaviour. N2: `bear_now` fetch fallback
  logs `op=bear_fallback` once per outage. N3: empty carry contracts/quotes log throttled `op=carry_noquotes`
  (hourly). N4: open carry notionals (both legs) join the risk-guard baseline so the total-gross cap sees both sleeves.
- Tests: `tests/test_bot_review_carry_guard.py` (F1/F2/F5, category-aware fake), `tests/test_bot_review_runner_paths.py`
  (F3/F4 + F6 race + F7 pagination); full `tests/test_bot_*.py` green. Testnet: GO for carry-enabled runs (F1+F2 fixed;
  book/dip-only was already go-with-caution); live still needs a clean testnet run first.

## CHANGES (bot_carryslice 2026-10-06: sliced pre-delivery spot exit, default behaviour)
- `bot/carry.py`: from `delivery_ms - 30 min` the filled spot qty is sold in 6 equal slices, one per 5-minute
  bucket at the first cycle inside each bucket (market IOC on spot, `op=carry_slice` per slice; first five
  floored to the spot lot, the last slice = exact remainder). Emitted buckets + slice links + sold qty/proceeds
  persist in the carry position state, so a restart mid-window resumes without double-selling (same bucket never
  refires; missed buckets fall through to the post-delivery remainder). After delivery the futures leg settles as
  before and any unsold remainder is sold at market (fallback, logged in `carry_settle` as `slice_sold` /
  `spot_remainder`); settlement P&L uses the VWAP across slices + remainder. A fully-sliced position emits only
  the futures safety Buy and finalises on its fill (or from the slice VWAP after a 1h grace for auto-settled
  dated shorts). Paper/testnet/live share the decision path (venue only); slice markets pass `guard_carry` as
  carry-recovery like other delivery sales. Rationale: `research/tournament/oc_deliverytrack/REPORT.md` (single
  08:00 print misses the index by ~20-28bp avg, worst ~90bp; 6 slices 07:30-08:00 cut it to ~5bp / worst 20bp).
- Tests: `tests/test_bot_carry.py` (+5: six-bucket/remainder math, one-per-bucket + json-round-trip restart,
  guard passthrough + no slice outside the window, remainder fallback with VWAP, fully-sliced futures-only).

## CHANGES (bot_soakfix 2026-10-06: B1/B2/B3 protection gaps + cycle exceptions, defaults unchanged for valid plans)
- B3: `mirror.desired(..., on_reject=None)` skips any dip rung / book entry whose limit price, TP or stop is
  <= 0 or non-finite (plan_reject via on_reject when the runner passes its log; pure skip otherwise, never divides by
  the limit) and wraps each plan row so one bad row is logged and skipped instead of raising out of `Runner.cycle`;
  `Runner.cycle` passes its log as on_reject and falls back to ledger-only protection if `desired` ever still raises,
  so protection is still managed that cycle. Soak harness `tests/soak_bot.py::make_plan` clamps `buy_limit` to a
  positive tick (test-only; zero-limit rungs no longer emitted).
- B1: book protection is managed for EVERY open piece of each (phase, symbol), not only the first `next(...)` match:
  a side-flip second entry now gets its native stop + TP the next cycle; plan add / reduce / close stays on the first
  piece only (never duplicated). Covered by `tests/test_bot_soakfix.py::test_b1_two_book_pieces_both_protected_after_side_flip`.
- B2: (a) pre-entry dust guard: a book / dip entry whose filled qty could not carry its protection (qty below the lot
  minimum, or qty x TP / qty x stop below the symbol minimum notional) is not placed (logged `op=dust_skip`, kept in the
  legacy `skipped_below_minimum` set too); sizing itself is untouched. (b) fallback: an open piece with KNOWN TP + stop
  prices that cannot rest on the exchange (below lot / notional, or non-positive / non-finite) is closed with a
  reduce-only market order in the SAME cycle (logged `op=dust_close`, taker fee), never left unprotected; pieces with no
  plan levels yet (pending sub, no attached sl/tp) are not dust and stay with divergence / unprotected logic.
  Helpers `mirror.entry_is_dust / protection_is_dust`; tests in `tests/test_bot_soakfix.py` (8 tests).
  Full `tests/test_bot_*.py` (181 tests) green; 2h smoke `tests/test_bot_soak_smoke.py` passes with 0 violations.

## CHANGES (bot_reviewfix2 2026-10-07: review findings 1-6 + carry-slice weakness, defaults unchanged for valid plans)
- #1 dip native stop: `mirror._dip_native_stop` (backstop else stop5/stop/sl); `desired` + `Runner._protection_only` emit TP+stop for every dip piece, never TP-only (`mirror.py`, `run.py:_protection_only`).
- #2 restart-safe exits: `mirror._market_inflight` needs confirmed `exit_link` (set only after the exchange accepts); phantom `exit_sent` never suppresses protection; `Runner` sets `exit_sent/link` post-send, `_guard_phantom_cancels` keeps resting S/T (`op=exit_revalidate`).
- #3 `_protection_only(led, now)` respects in-flight + `finite_pos` (no raise on corrupt ledgers; dip native stop like the main path).
- #4 per-leg TP=0 fallback: a valid tightened plan SL survives a `tp=0` glitch (and vice versa); only invalid legs fall back to entry levels.
- #5 TP failures count in the unprotected counter like stops (both legs must rest; >2 failed cycles -> `op=unprotected_close`).
- #6 wrong-side guard: plan SL/TP on the wrong side of the mark (long `SL<px<TP`, short mirrored; mark = `last_close` else plan coin price) logs `op=plan_reject/book_protect_wrong_side` and falls back to entry levels.
- Carry slices: buckets go done only in `carry.note_exec` on the slice fill (`slice_link_bucket` map); unfilled buckets re-emit while active (same-bucket retry); dust/zero still done at decide; remainder fallback unchanged.
- Sizing/entry logic untouched. Tests: `tests/test_review_soakfix.py` (12: 3 demos now pass + 9 for #3-#6/carry); 3 pre-fix assertions superseded (2 exit_sent-only inflight, 1 no-retry slice) and fail as intended.

## Failure modes (tests/test_bot_resilience.py, fake exchange, no network)
- Restart mid-position: new Runner adopts state.json + exchange stops/TPs, no duplicate entries, filled rungs never re-placed.
- Partial dip fill: TP/stop size to the filled qty, remainder stays resting (same link), budget counts only the filled part.
- Stop placement errors: retried next cycle; unprotected > 2 cycles -> market reduce-only close, logged `op=unprotected_close`.
- Rejected orders (lot/min-notional): `to_exchange` returns None, logged `skipped_below_minimum`, at most one attempt per cycle per link.
- Late cycle (20 min): time exits fire on `now >= t_exit`, stale-plan still blocks entries, entries never wanted inside the first 5 min.
- Missing/corrupt plan: logged `op=plan_error`, no crash, cached plan keeps protection with no new entries (no cache: ledger-only TP/stop).
- Duplicate fills: `sync_fills` applies each execId once (`seen_exec`); fixed `last_exec_ms=0` falsy-start bug.
