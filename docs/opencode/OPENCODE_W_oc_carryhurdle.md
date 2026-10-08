# OpenCode task oc_carryhurdle - IDEAS11 #1: quarterly carry entered only if the basis covers H x the round-trip fees
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_carryhurdle/` and `tests/test_oc_carryhurdle.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome. Light (overlay only, no engine).

## Task
Implement idea #1 of docs/opencode/IDEAS11_20261008.md exactly: with the frozen oc_cashcarry pair list and the oc_carrycompound overlay
(f = 0.25, reproduce 5.634 / 16.75 / 16.66 on Binance and the Bybit S5 row of oc_c2carry first), enter a quarterly pair only if the annualised
basis at entry >= H x round-trip cost (spot 2 x 0.001 + perp taker 0.00055 + maker 0.0002), V1 H = 2.0, V2 H = 1.5 (H from the fee schedule,
never tuned). Report per year the skipped pairs and their realised P&L, dev4 / 5y / full-path DD on Binance and Bybit, robust pick on dev4 only,
post-release year scored once for the pick and REF. Vietnamese 3-line verdict.
