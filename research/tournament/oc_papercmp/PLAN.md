# oc_papercmp — PLAN (pre-registered before computing outcomes)

## Hypothesis
The live paper bots (`artifacts/bot/paper`, `artifacts/bot/paper_d18`) and the
frozen v376 R2-4P plan (`artifacts/research/advisor_shadow/trade_plan_v376.json`)
can be compared on identical definitions: hourly equity return %, max drawdown,
fill counts by kind, and piece win rate. The R2-4P bot (paper) should track the
plan within a small return gap; any gap is explained by fills present in one
source but not the other (unfilled dip ladder / extra book fills / timing).

## Inputs (read-only, no market data)
- `artifacts/bot/paper/exchange.json` — R2-4P bot: `equity_curve`, `execs`,
  `orders`, `fees`, `funding_paid`, `cash`, `equity0`.
- `artifacts/bot/paper_d18/exchange.json` — second bot source, same schema.
- `artifacts/bot/paper/runner.log` (= `actions.jsonl`) and
  `artifacts/bot/paper_d18/runner.log` — action counts (`place`/`cancel`/
  `fill`/`amend`/`cycle_error`).
- `artifacts/bot/paper/state.json`, `artifacts/bot/paper_d18/state.json` —
  link `kind` (`entry`/`stop`/`tp`) and piece `meta.kind` (`book`/`dip`).
- `artifacts/research/advisor_shadow/trade_plan_v376.json` — plan:
  `equity_curve` (indexed to 1.0), `events`, `net_return_pct`.
- No 1m/market klines are loaded, so the 1.5 GB / one-coin-at-a-time / one-process
  rule is trivially satisfied; the tool runs single-process with only JSON I/O.

## Exact definitions
- **Equity curve since start**: raw `equity_curve` list copied per source
  (`[timestamp, equity]` pairs, hourly).
- **Return %**: `100 * (last - first) / first` on that source's own curve.
- **Max DD %**: `100 * max over t of (peak_before_t - eq_t) / peak_before_t`
  on the same curve (0 if curve never falls).
- **Fill kinds** (bot execs, from `execs[].orderLinkId`, resolved with
  `state.json` links when available, else by naming rule):
  - `book_entry`: piece kind `book` + entry (link `b*E`).
  - `dip`: piece kind `dip` + entry (link `d*E`).
  - `tp`: exit kind `tp` (link `*T`).
  - `stop`: exit kind `stop` (link `*S`).
  - `market_exit`: exit kind market without trigger (link `*M`/`*X`, or
    `orderType==Market` + `reduceOnly` + no trigger). Counted separately.
  - Plan fills: `events[].kind` counts (`book_fill`, `order_issue`,
    `order_expire`, `order_cancel`); plan `book_fill` maps to `book_entry`.
- **Closed pieces + win rate** (bots only): `piece` = `orderLinkId` minus the
  final `E/T/S/M/X` char (exactly how `state.json` stores `piece`). A piece is
  **closed** when it has >= 1 entry exec AND >= 1 exit exec (`tp`/`stop`/
  `market_exit`). `win` = exit notional > entry notional for the piece
  (LONG pieces: Buys are entries, Sells are exits; quantities summed;
  fees excluded, noted as caveat). `win_rate` = `wins / closed`
  (`null` when `closed == 0`).
- **Divergence (R2-4P bot vs plan)**:
  - `return_diff_pp` = `paper.return_pct - plan.return_pct` (percentage points).
  - `fills_only_in_bot`: bot piece ids with no matching plan fill
    (matched loosely by symbol; exact id spaces differ, so the count and the
    id lists are reported with the matching rule stated).
  - `fills_only_in_plan`: plan `book_fill` events (by `t/symbol/price`) with no
    bot entry exec at the same symbol within the window.
  - R2-4P bot = `artifacts/bot/paper` (book + dip ladder); the plan is v376 R2-4P.

## Decision rule
`scripts/paper_compare.py` prints per-source tables to stdout and saves
`artifacts/research/paper_compare.json` with the curves, metrics, and divergence
above. `research/tournament/oc_papercmp/results.json` stores the same metrics
object; `REPORT.md` renders the tables plus exactly one verdict line naming the
return/DD/fill-gap outcome. No trading decision is made; this is evidence only.
A correctness test with synthetic inputs (`tests/test_oc_papercmp.py`) must pass.
