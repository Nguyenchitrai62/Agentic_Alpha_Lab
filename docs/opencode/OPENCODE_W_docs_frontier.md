# OpenCode task docs_frontier - one return-vs-drawdown map of every G2 variant / dial measured so far (for the owner)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. EXCEPTION (docs task): write ONLY `docs/FRONTIER_MAP_VI.md`,
`research/diagnostics/docs_frontier/` (table CSV + PNG + the script that builds them). Copy numbers ONLY from the cited reports.

## Content
Collect, for every G2-family configuration with a 4-phase 5-year result on the gate cost model, the 5-year mean %/month (reset metric), the
dev4 mean and worst year, the most recent year, max yearly DD and full-path DD, and whether it passed the robust criterion / audit:
G2 (v421), D13BF (v424), D17BF (v411), G2K20 (v422), G2 + carry f 0.25 (oc_carrycompound), G2K20 + carry (oc_g2k20compound),
governor rows GV1 / GV2 / GV3 (oc_governor), ablation rows (oc_ablation: NO_GOV, NO_VT, NO_BEAR, NO_CAP, NO_B1, TOUCH), Amihud A1
(oc_lit_xs; and its S5 Bybit row from oc_amihudrobust), MVRV M1 (oc_lit_position / oc_mvrvrobust), A1 + M1 (post-hoc), Kronos K2
(oc_kronoshidden), VRP straddle overlay at traded prices (oc_vrpstrike FULL), frontier rows of oc_frontier if available.
Deliverables: a CSV, a scatter PNG (x = full-path DD, y = 5-year %/month; colour = kind: dial / signal / overlay; marker = adopted / not),
and `docs/FRONTIER_MAP_VI.md` (Vietnamese, <= 60 lines): the table, the picture, and 5 plain sentences: which points are pure risk dials on
one line, which moved off the line (if any), what is deployed and why, and what the owner trades off by choosing a point.
