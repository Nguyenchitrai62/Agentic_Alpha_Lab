# OpenCode task ops_carrygap - why are the two G2 + carry paper runners ~1.5 pp below their no-carry twins?
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/diagnostics/ops_carrygap/` and `docs/opencode/CARRYGAP_20261007.md`.
artifacts/bot/* READ-ONLY; never start / stop processes.

## Facts (docs/opencode/OOS_WEEK3_20261007.md)
raw paper returns: paper_d17bfg2 +0.59 %, paper_g2k20 +0.67 % vs paper_d17bfg2c -1.37 %, paper_g2k20c -1.46 % (the c runners = same bot flags
+ --carry-f 0.25; they started later: d17bfg2c 2026-10-06 07:19 UTC, g2k20c 14:15 UTC vs the twins 2026-10-05 ~17:40).
## Task
Decompose each c runner's equity change since its start into: dip P&L, book P&L, carry legs (spot buy fees 0.1 %, dated-future entry fees,
mark-to-market of spot vs short future, basis change), funding, fees; and compare with its twin OVER THE SAME WINDOW (twin's equity curve
restricted to the c runner's start). Use exchange.json / actions.jsonl / state.json (carry block) and bot/carry.py to understand the carry
accounting (read only). Is the gap (a) the window difference, (b) carry entry fees + basis MTM (expected to reverse at delivery), (c) different
dip/book fills, or (d) a bug (e.g. spot leg valued wrongly, double fee)? If (d), give a minimal reproduction (do not edit bot/). Vietnamese doc
<= 30 lines.
