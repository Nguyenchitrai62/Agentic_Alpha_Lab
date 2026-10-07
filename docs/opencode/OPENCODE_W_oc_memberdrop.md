# OpenCode task oc_memberdrop - which book member carries G2's timing, and how much does the bot lose if a live data feed dies?
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_memberdrop/` and `tests/test_oc_memberdrop.py`.
Print progress at least every 10 minutes. Heavy engine runs via heavy_slot.

## Context
research/tournament/oc_bookattrib: the deployed book's return is mostly TIMING (placebo >= 96.8 % every year, beta 0.05-0.14); book-only
net 2.53 %/month, DD 18.96. The deployed book is a blend of members (research/diagnostics/oc_bookoos/score_oos.py docstring: 0.8 x O1 +
0.2 x CB; O1 = order-level whale-flow member family (v240), CB = the Coinbase-premium blend (v285); read their scripts to confirm the exact
blend the v421 engine run used - research_books_d2 / pipe_setup in v421's worker()). Live, each member depends on a different feed
(Binance aggTrades order-level flow; Coinbase spot candles). Not known: how much of G2 survives if one feed is missing for days.

## Rows (4-phase engine exactly as v421 G2: rule inv, k 1.0, kd 1.7, bear True, G 2.0; reproduce 5.41 / 16.91 / 16.82 first)
- FULL: G2 as deployed.
- NO_FLOW: the book built WITHOUT the whale-flow member(s) (weights renormalised over the remaining members exactly as the blend code does
  when a member is absent; if the code has no such path, use the remaining members' blend with weights rescaled to sum to 1 - state it).
- NO_CB: the book without the Coinbase-premium member(s), same renormalisation.
- STALE_FLOW (outage stress): the flow member's prediction frozen at its last value for 72 h starting at 10 fixed, pre-registered UTC
  timestamps per year (every 36.5 days from the anchor + 10 days), then resumes; everything else unchanged.
Per year (dev4 + the most recent year, all labelled descriptive: NO selection is made here, the deployed config does not change): 4-phase
reset metric R, yearly DD, full-path DD, book-only share if separable. Vietnamese 3-line verdict: which feed is critical, and the expected
cost of a 3-day outage (for the runbook).
