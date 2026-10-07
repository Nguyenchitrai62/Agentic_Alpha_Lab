# OpenCode task oc_mvrvrobust - is the MVRV-z cycle gate M1 (halve book longs when BTC MVRV z > 2) real or one event?
Read docs/opencode/OPENCODE_W_COMMON_20261007.md and docs/opencode/OPENCODE_W_TEMPLATE_BOOKGATE_20261007.md first. Write ONLY
`research/tournament/oc_mvrvrobust/` and `tests/test_oc_mvrvrobust.py`. Print progress every 10 minutes. Engine runs via heavy_slot.

## Context
research/tournament/oc_lit_position (read REPORT.md, PLAN.md, code; copy, do not edit): M1 = all majors' book LONG weights x0.5 while
zM > 2.0, zM = (MVRV - mean) / std over the trailing <= 365 days (min 180) of BTC CapMVRVCur (data/raw/onchain_20260924/btc.csv), day D
usable from D+1 02:00 UTC. dev4 6.192 vs G2 5.601, DD 16.26 vs 16.91, beats its exposure control; worst dev year ties G2 (2.588) - under
the AGENTS.md robust criterion (ties -> higher mean) M1 would be preferred. Gains concentrate in 2023 (+1.78 pp). The most recent year was
not scored as a selection input.

## Tasks (robustness of the frozen M1; no re-selection)
1. Event table: every contiguous gated window (start, end, days, BTC return during the window, G2 book P&L during the window, M1 book P&L,
   difference) per year. How many independent episodes carry the dev4 gain?
2. Jitter rows (engine, one knob each): threshold 1.75 / 2.25; z window 270 / 450 days. Report dev4 and 5-year.
3. Leave-one-episode-out: the dev4 gain with each gated episode removed (vectorised from the engine equity paths if separable, else engine).
4. Frictions S1-S5 on M1 vs G2 (same implementations as research/tournament/oc_amihudrobust uses - coordinate by reading its PLAN once it
   exists, else copy from the v421 audit ROBUST rows).
5. Score the most recent year ONCE for M1, G2 and the control (labelled; M1 is a candidate under the robust criterion).
6. Interaction with the Amihud A1 tilt (research/tournament/oc_lit_xs): one row A1 + M1 combined (labelled post-hoc combination) - dev4 and 5y.
Verdict (Vietnamese 3 lines): robust (gain spread over >= 2 episodes, all jitters >= G2, positive under every friction) or single-event luck.
