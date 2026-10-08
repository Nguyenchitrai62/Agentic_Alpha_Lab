# OpenCode task oc_levfrontier - the deployable return / drawdown frontier on BYBIT prices with carry (leverage x C2 x B7)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_levfrontier/` and `tests/test_oc_levfrontier.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome. Engine via heavy_slot (RAM tight: one engine job at a time).
LABELS: C2's dev years nearly clean, B7 contaminated (see oc_cascadeboost / oc_cboostctrl: B7 is ~70 % extra exposure); the post-release year
is a labelled diagnostic for every row that contains C2 or B7.

## Why
oc_cboostctrl: most of B7's gain is exposure, so the real question for the owner is the frontier: at full-path DD <= 20 on Bybit prices (the
owner's venue) with the quarterly carry overlay f 0.25, which exposure level and overlay give the best return, and does any row reach >= 5 %/month
in the most recent year?
## Rows (pre-registered; all with G2's gross cap 2.0, everything else G2)
dip-mult in {1.7 (G2), 2.0 (G2K20)} x overlay in {none, C2, B7, B7xC2}: 8 rows. Reuse every stored run that already exists bit-exactly
(v421 / v422, oc_chronos, oc_c2bybit, oc_cascadeboost, oc_cboostbybit, oc_b7c2, oc_b7frontier, oc_c2frontier) and run only the missing ones,
each on Binance prices (base) AND Bybit prices (S5, harness of oc_c2bybit). Then the carry overlay exactly as research/tournament/oc_c2carry.
## Report
Per row x venue: dev4 per year / mean / WORST / DD, 5y, full-path DD, worst 1m-marked episode, most recent year (labelled), and the block
bootstrap of oc_c2carry (median %/month, P(month >= 5 %), P(DD > 20 % in a year), P(losing year)). Robust pick on dev4 ON BYBIT PRICES among rows
with full-path DD <= 20 (highest WORST year, ties -> mean). Plain table of (5y, full DD) for all 16 points. Vietnamese 5-line summary for the owner:
the best deployable row on Bybit and its honest expectation.
