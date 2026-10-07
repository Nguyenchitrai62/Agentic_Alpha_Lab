# OpenCode task oc_ideascan3 - genuinely new ideas and NEW data sources (scan, no backtests)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `docs/opencode/IDEAS_20261007c.md` and `research/tournament/oc_ideascan3/`
(notes, small probe scripts, probe outputs < 5 MB). No downloads > 50 MB, no authenticated endpoints, no paid APIs.

## Context
The program is at a saturated return-DD frontier: everything on the existing data moves along one frontier (memory of the program:
docs/CLOSED_DIRECTIONS.md, .claude/skills/alpha-lab-leader/research-map.md sections "Tried and rejected" and "Honest status",
docs/opencode/IDEAS*_2026100*.md). Read all of them first. Deployed: G2 (book + corr-aware dip ladder, 5.41 %/month, DD ~17) + quarterly
cash-and-carry. Running now in parallel (do not propose these again): option put-writing, protective puts, delta-hedged short straddles,
Kronos dip tilt on the post-release year, intrabar rip-continuation sleeve, relative-flush dip allocation, Deribit strike-level data fetch.
Universe for TRADING: BTC/ETH/SOL/BNB/XRP only (other coins may be used as information). Rules: limit entries, every trade has SL + TP, a bot
reacting within minutes, 4h decision bars, no fill in the first 5 minutes after a 4h close.

## Deliverable
`docs/opencode/IDEAS_20261007c.md`:
A. NEW DATA (at least 8 candidates) that are NOT in docs/DATA_CATALOG.md / data/raw/: for each - what it measures, history start (need >=
   2021-09 for the 5 walk-forward anchors, or state the shorter span), free access method (URL / endpoint, verified with one small GET and the
   probe saved in your folder), update latency (usable live?), size, and the concrete hypothesis for the dip ladder or the book. Examples to
   check (verify, do not assume): Deribit per-instrument history and block trades, Bybit options public trades / delivery prices, Binance
   options (EAPI) history, Hyperliquid public archives (trades, liquidations, funding), Coinbase International perps, CME basis from public
   settlement files, spot BTC/ETH ETF daily flows, stablecoin supply / mint-burn (free APIs), exchange status / maintenance calendars,
   Binance "insurance fund" history, Bitfinex/OKX liquidation archives, Google Trends / GDELT tone.
B. NEW IDEAS (exactly 10) not covered by the closed lists: hypothesis, mechanism (why it should pay), data, an exact pre-registerable test with
   at most 3 variants, how it would be judged (the 4-phase engine for book ideas; the dip replica + placebo gate +0.273 for dip ideas; a
   standalone sleeve with placebo for new sleeves), expected effect size vs costs, leakage risks, prior probability of success (be honest).
   Rank them by expected value / cost.
C. A short list of ideas you considered and DROPPED because they duplicate closed directions (with the closed item they duplicate).
