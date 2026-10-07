# OpenCode task oc_governor - does the PER-PHASE drawdown governor cost G2 return? (descriptive + 3 pre-registered rows)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_governor/` and `tests/test_oc_governor.py`.
Print progress every 10 minutes. Engine runs via heavy_slot.

## Why
research/tournament/oc_mvrvmech: the MVRV gate's apparent gain came from interaction with the drawdown governor, not from MVRV timing - in
G2 phase 3 the governor sat at 0 during the early-2024 rally (shutdown), and a smaller book avoided it. The governor
(research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py, `gov` = (dd_zero 0.20, width 0.10): size g = clip((0.20 - dd) /
0.10, 0, 1) with dd from the trailing 90-day peak of THAT PHASE's sub-account equity, lagged 2 bars) acts per clock phase, while the real
account is ONE pooled account whose drawdown is the 4-phase mix (much smaller than single-phase DDs, e.g. phase 3 2023 single-phase DD 43 %).
First check how the LIVE plan computes the governor (scripts/forward_trade_phase.py, backend/multiphase.py) and say whether live also uses
per-phase sub-account equity.

## Tasks
1. Descriptive (G2 v421 runs; recompute g per phase if not stored): per phase and year, share of bars with g < 1 and g = 0, the longest
   g = 0 spell, and the P&L the phase missed (counterfactual ungoverned phase path with the same fills is not available - estimate with the
   vectorised book proxy of research/tournament/oc_bookattrib + dip replica, labelled).
2. Engine rows on G2 (one knob each, pre-registered; DD gate stays the 4-phase-mix max of close / 1m-marked):
   GV1 gov = (0.25, 0.10); GV2 gov = (0.30, 0.15); GV3 = governor driven by the COMBINED 4-phase equity (dd of the mean of the four phase
   equity paths): implement as a two-pass approximation (pass 1 = G2 phase paths -> combined dd -> g for every phase in pass 2; label it an
   approximation and report the difference between pass-1 and pass-2 combined dd).
   Report dev4 (selection) + the most recent year ONCE for any row that beats G2 on dev4 mean with worst year >= G2 and max yearly DD <= 20
   (the user's hard cap; also report vs G2's 16.91).
3. Verdict (Vietnamese 3 lines): is the per-phase governor a structural drag, and would a pooled-account governor be the honest live design?
