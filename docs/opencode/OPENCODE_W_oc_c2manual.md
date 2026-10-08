# OpenCode task oc_c2manual - can the MANUAL product use the Chronos C2 multiplier (a human reads it at the bar open)?
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_c2manual/` and `tests/test_oc_c2manual.py`.
Print progress every 10 minutes. Engine via heavy_slot (RAM tight: one engine job at a time). LABEL: new product variant.

## Why
research/tournament/oc_k2manual put the Kronos K2 multiplier on the MANUAL bracket dip rungs: +0.112 %/month 5y but a worse 2021 worst year.
C2 (research/tournament/oc_chronos) is the most consistent tilt across 9 years (oc_presampletilt: helps 7/9) and the dev4 robust pick on the BOT.
## Rule (fixed; copy oc_k2manual's harness exactly, swap the multiplier)
KM_C2: every MANUAL dip bracket rung of (coin, bar) x the C2 multiplier of (coin, shift = phase, bar open) with oc_chronos fits.json; everything
else exactly M5_human (reproduce 3.728 / 17.94 / 17.79 bit-exact first). Rows: M5_human, KM_C2, CTRL (constant multiplier = KM_C2's realised
mean per year), plus KM_K2 copied from oc_k2manual. Report dev4, post-release year (scored once; new product variant), 5y, full-path DD, win
rates. Verdict (Vietnamese 3 lines): how much of the MANUAL gap to 5 %/month does C2 close?
