# OpenCode task oc_k2manual - can the MANUAL product use the Kronos K2 multiplier (a human reads it at the bar open)?
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_k2manual/` and `tests/test_oc_k2manual.py`.
Print progress every 10 minutes. Engine via heavy_slot. LABEL: new product variant; dev years are inside Kronos pretraining (upper bound).

## Why
MANUAL (human-placeable bracket dip limits + book, research/diagnostics/manual_human, M5_human 3.728 %/month, floor 5) cannot use the
minute-level corr sizing. K2's multiplier (research/tournament/oc_kronoshidden: per (coin, clock, bar) x1.25 / x0.75 / x1 from Kronos low1)
is known at the bar open, so a human could scale the bracket sizes before placing them (published on the web plan).
## Rule (fixed)
KM_K2: every MANUAL dip bracket rung of (coin, bar) x the K2 multiplier of (coin, shift = phase, bar open) with the per-anchor fits of
oc_kronoshidden (fits.json); everything else exactly M5_human (reproduce 3.728 / 17.94 / 17.79 bit-exact first, as research/tournament/
oc_manualsplit and oc_kronosmanual did). Rows: M5_human, KM_K2, CTRL (constant multiplier = KM_K2's realised mean per year).
Report dev4 (upper bound), the post-release year (scored once; new product variant), 5y, full-path DD, win rates. Verdict: how much of the
MANUAL gap to 5 %/month does K2 close? Vietnamese 3 lines.
