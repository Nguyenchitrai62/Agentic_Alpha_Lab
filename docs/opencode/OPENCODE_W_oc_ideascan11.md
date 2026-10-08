# OpenCode task oc_ideascan11 - 6 COST-SIDE ideas (fees, funding, borrow, venue mechanics) that need no fitting
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `docs/opencode/IDEAS11_20261008.md`. No code, no engine. Print progress every 10 minutes.

## Why
Signal-side ideas mostly fail out of sample (docs/CLOSED_DIRECTIONS.md 2026-10-08 rows). Cost-side changes are robust by construction (no
parameter fitted to returns): e.g. research/tournament/oc_spotlongs (book longs on spot to avoid the gate funding charge; re-run with honest spot
fees in oc_spotlongs2). The gate cost model (AGENTS.md): maker 0.0002, taker 0.00055 on Bybit USD-M perps, longs pay 0.0001 per 8h, shorts
earn nothing; spot fees 0.001; stops are market (taker); every position has a stop and a TP.
## Inputs
AGENTS.md, docs/CLOSED_DIRECTIONS.md (incl. oc_vipfees, oc_bybitgap, oc_bybitfill, oc_makerexit, oc_bookband, oc_carry*, oc_spotlongs),
research/tournament/oc_bookband/turnover.json (book turnover / fee drag), oc_bybitgap. Public Bybit fee / funding / borrow documentation
(web search allowed; no account access).
## Output (<= 70 lines)
6 cost-side ideas (where the fee / funding / borrow money goes today, quantified from existing results; what changes it; what the honest
gain is under the gate rules), each with the exact rule, the 1-2 pre-registered variants, data, harness, expected effect, prior, and the trap
(e.g. claiming queue position, ignoring spot fees, assuming rebates the account will not get). Rank by EV / cost.
