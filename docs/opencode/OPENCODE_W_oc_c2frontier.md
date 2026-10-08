# OpenCode task oc_c2frontier - does the C2 tilt move the BOT return / drawdown frontier outward (DD < 15 goal)?
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_c2frontier/` and `tests/test_oc_c2frontier.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome. Engine via heavy_slot (RAM tight: one engine job at a time).

## Why
docs/FRONTIER_MAP_VI.md / memory: BOT overlays move along one frontier; DD < 15 only at ~4.97 %/month (D13BF, dip-mult 1.3). C2
(research/tournament/oc_chronos) lowered G2's full-path DD by 1.4 pp at +0.13 %/month. If the frontier shifts, a lower dip-mult + C2 might give
>= 5 %/month with DD < 15 (BOT goal step).

## Rows (pre-registered)
D13BF (the v421-family row with dip-mult 1.3, as in the frontier map), D13BF + C2, G2 (= D17BFG2), G2 + C2 (copy oc_chronos), G2K20
(dip-mult 2.0) + C2. C2 multipliers frozen from oc_chronos. Report dev4 per year / mean / WORST / DD, 5y, full-path DD, post-release year
scored ONCE (labelled), and the same on Bybit prices (S5, as oc_c2bybit) for D13BF and D13BF + C2. Table of (5y return, full-path DD) for all
rows next to the known frontier points. Verdict (Vietnamese 3 lines): is there a row with 5y >= 5 and full-path DD < 15 on Bybit prices?
