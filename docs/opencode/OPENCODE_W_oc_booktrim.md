# OpenCode task oc_booktrim - is G2's book over-sized? (a uniform book trim frees gross-cap room for the more profitable dip sleeve)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_booktrim/` and `tests/test_oc_booktrim.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome. Engine via heavy_slot (RAM tight: one engine job at a time).

## Why (leader observation, 2026-10-08)
Several studies' exposure-matched constant controls (a uniform book scale < 1, e.g. ~0.8-0.95) beat G2 on dev4 mean: oc_memberagree C08
5.861, oc_spillgate 5.832 / 5.707, oc_volvolbrake 5.830 / 5.821, oc_decayexit 5.751 vs G2 5.601. Hypothesis: book and dip share the gross cap
2.0, so a smaller book leaves room for more dip fills, which earn more per unit of gross. CAUTION: those controls were built from each study's
realised scale; this task tests the trim directly with constants fixed in advance.
## Variants (exactly two, constants fixed now)
BT08: every book target x0.8. BT06: x0.6. Everything else exactly G2 (dip sleeve, caps, carry off).
## Report
Rows REF, BT08, BT06 on Binance (base) AND Bybit prices (S5, harness of research/tournament/oc_c2bybit): dev4 per year / mean / WORST / DD,
robust pick on dev4 ONLY (Binance base) among REF / BT08 / BT06, post-release year scored ONCE for the pick and REF, 5y, full-path DD; plus the
decomposition per year: book P&L, dip P&L, number of dip fills and how often the gross cap binds (REF vs variants) - does the dip leg actually
gain fills? Vietnamese 3-line verdict.
