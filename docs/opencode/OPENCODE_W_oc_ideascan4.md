# OpenCode task oc_ideascan4 - published crypto anomalies vs what this program has tested (map + untested shortlist)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `docs/opencode/IDEAS4_20261007.md` and `research/tournament/oc_ideascan4/`
(notes; tiny probes < 5 MB). Public web pages only (papers / SSRN abstracts / arXiv / blog summaries); no paid APIs; no downloads > 50 MB.

## Task
1. Compile at least 25 documented crypto return / risk anomalies or trading effects from the academic and practitioner literature
   (examples to check: time-series momentum at 1-4 weeks, short-term reversal, intraday momentum (first vs last half-hour), overnight vs
   intraday (US hours), day-of-week / weekend, turn-of-month, funding-rate carry, basis carry, volatility-managed portfolios, max-effect /
   lottery, liquidity / Amihud, size, network / on-chain value (NVT, MVRV), exchange flows, stablecoin mint, Google attention, Twitter
   sentiment, options skew / VRP, jump risk, cross-exchange lead-lag, CME gap, halving cycle, BTC-dominance rotation, ETF flows).
   For each: one-line mechanism, the best source (title, year, URL), the reported effect size and holding period.
2. Map each to this program's record: docs/CLOSED_DIRECTIONS.md, .claude/skills/alpha-lab-leader/research-map.md ("Tried and rejected",
   "Honest status"), docs/opencode/IDEAS*_2026100*.md. Classify: TESTED-CLOSED (cite the item), TESTED-KEPT, PARTIALLY TESTED (say what was
   not), UNTESTED.
3. For every UNTESTED or PARTIALLY TESTED item that fits the rules (trade only BTC/ETH/SOL/BNB/XRP, 4h decisions for the book or the intrabar
   dip ladder, limit entries + SL + TP, no fill in the first 5 min, data available back to >= 2021-09 free), write a pre-registerable test
   (<= 3 variants, judgement method, expected effect vs costs, leakage risks, honest prior). Rank by expected value / cost.
