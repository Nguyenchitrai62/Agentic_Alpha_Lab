# OpenCode task oc_beargate - apply the dip-size tilt only when G2's OWN frozen bear filter says "not bear" (no new parameter)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_beargate/` and `tests/test_oc_beargate.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome. Engine via heavy_slot (RAM tight: one engine job at a time).

## Why
The vol / foundation-model dip tilts (oc_voltilt, oc_chronos) help in 2023-2026 and hurt or do nothing in 2021-2022 (bear market). G2 already
contains a frozen bear filter (bear True in v421 R2B1D17BFG2 / bot --bear-book, op bear_state). Conditioning the tilt on that EXISTING state
adds no free parameter.

## Variants (exactly two)
C2_B: C2 multiplier (research/tournament/oc_chronos, frozen fits) when the bear state of that bar is False, else 1.0.
GARCH_B: V_GARCH multiplier (research/tournament/oc_voltilt, frozen) when not bear, else 1.0.
The bear state must be the exact causal definition the engine / bot uses (find it in the v421 engine code; cite file:line), evaluated at the
holding-bar open from data available then.

## Report
Share of bars / fills in bear state per year; engine rows REF, C2 (copied from oc_chronos), V_GARCH (copied from oc_voltilt), C2_B, GARCH_B:
dev4 per year, mean, WORST, DD; robust pick among REF / C2_B / GARCH_B on dev4 ONLY; post-release year scored ONCE for those three (labelled);
5y; full-path DD; timing placebo per year for the two gated variants. Vietnamese 3-line verdict.
