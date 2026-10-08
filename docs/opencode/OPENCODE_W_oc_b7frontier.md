# OpenCode task oc_b7frontier - B7 on the lower-risk D13BF base: >= 5 %/month with full-path DD <= 20 on BYBIT prices?
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_b7frontier/` and `tests/test_oc_b7frontier.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome. Engine via heavy_slot (RAM tight: one engine job at a time).
LABEL: B7 is contaminated (research/tournament/oc_cascadeboost) - post-release numbers are labelled diagnostics.

## Why
research/tournament/oc_cboostbybit: G2 + B7 on Bybit prices 5y 5.906 (G2 4.883) but full-path DD 20.31 > 20. research/tournament/oc_c2frontier
built D13BF (dip-mult 1.3, v424, Bybit S5 5y 4.482 / full DD 15.95). B7 on that base may keep >= 5 %/month with DD well under 20.
## Rows (pre-registered)
D13BF, D13BF + B7, G2 + B7 (copy oc_cascadeboost / oc_cboostbybit), each on Binance (base) and Bybit prices (S5, harness of oc_c2bybit /
oc_cboostbybit); plus each + quarterly carry f 0.25 as an account overlay exactly like research/tournament/oc_c2carry. Report dev4 per year /
mean / WORST / DD, 5y, full-path DD, worst 1m-marked episode, post-release year (labelled), the block-bootstrap expectation of oc_c2carry
(median %/month, P(month >= 5 %), P(DD > 20 % in a year), P(losing year)). Verdict (Vietnamese 3 lines): which row meets 5y >= 5 %/month and
full-path DD <= 20 on Bybit prices with carry?
