# OpenCode task oc_cboostmanual - can the MANUAL product use the cascade boost (a human scales bracket sizes x1.5 for 7 days after a cascade)?
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_cboostmanual/` and `tests/test_oc_cboostmanual.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome. Engine via heavy_slot (RAM tight: one engine job at a time).
LABEL: new product variant; CONTAMINATED like oc_cascadeboost (the idea was formed after a replica that covered all five years) - the
post-release year is a labelled diagnostic.

## Why
MANUAL (M5_human 3.728 %/month 5y, floor 5) lacks ~1.1-1.3 pp. research/tournament/oc_cascadeboost: on the BOT, B7 (dip budget x1.5 for
7 days after a > 4 sigma 4h move) lifted dev4 from 5.60 to 6.74 with a better worst year (2.96 vs 2.59). A cascade bar is known at its 4h
close and is a single checklist line for a human ("a 4h candle moved more than 4 sigma -> use 1.5x bracket sizes for 7 days").
## Rule (fixed; harness of research/tournament/oc_k2manual / oc_c2manual, reproduce M5_human 3.728 / 17.94 / 17.79 bit-exact first)
KM_B7: every MANUAL dip bracket rung whose bar opens inside a 7-day window after a cascade bar (oc_cascadedelay's definition, frozen; the
human acts from the next bar after the cascade bar closes, respecting the M5_human schedule: 15-minute reaction, night bar skipped) is sized
x1.5; KM_B3: the same with 3 days. Everything else exactly M5_human (order caps, budgets, protection).
## Report
Rows M5_human, KM_B7, KM_B3: dev4 per year / mean / WORST / DD / full-path DD / win rates (book and all), robust pick on dev4 ONLY, post-release
year (labelled diagnostic), 5y. Verdict (Vietnamese 3 lines): how much of the MANUAL gap to 5 %/month does the cascade boost close?
