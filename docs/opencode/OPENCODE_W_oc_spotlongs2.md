# OpenCode task oc_spotlongs2 - re-run the spot-routed book longs with HONEST spot fees
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_spotlongs2/` and `tests/test_oc_spotlongs2.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome. Engine via heavy_slot (RAM tight: one engine job at a time).

## Why
research/tournament/oc_spotlongs (V1: every book long held as spot instead of perp, no funding) priced the spot legs at PERP fees (maker
0.0002). Bybit spot fees at VIP0 are ~0.1 % maker and taker; the program's convention for spot legs is 0.001 (the carry sleeve, AGENTS.md).
The +0.23 %/month funding saving may disappear.
## Rows (pre-registered; reuse oc_spotlongs code, change only the spot-leg fee constants)
REF (G2), SPOT_F10 (V1 with spot maker = taker = 0.001; the spot SL as a market sell pays 0.001), SPOT_F06 (sensitivity: 0.0006, a
higher-VIP tier, labelled), plus the book turnover per year and the fee / funding split per leg. Dev4 per year / mean / WORST / DD, robust pick
among REF / SPOT_F10 on dev4 ONLY, post-release year (labelled diagnostic: oc_spotlongs already scored this year once), 5y, full-path DD, and
the Bybit S5 row for the pick. Also check feasibility: Bybit spot TP / SL order types for an attached stop and take-profit on a spot long
(cite the public API docs only; no keys, no calls). Vietnamese 3-line verdict.
