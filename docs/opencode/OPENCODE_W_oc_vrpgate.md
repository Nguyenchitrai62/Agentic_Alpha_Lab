# OpenCode task oc_vrpgate - sell the weekly straddle only when the ex-ante volatility premium is high (POST-HOC INFORMED screen)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_vrpgate/` and `tests/test_oc_vrpgate.py`.
Copy code from research/tournament/oc_vrpstraddle (vrp.py, run_vrp.py) and, once it exists, research/tournament/oc_vrpconsistent (consistent
scaling); do not edit them. LABEL everything POST-HOC INFORMED: the idea comes from seeing V2's yearly IV-RV gaps (+0.10 in 2021/2022, ~0.01 in
2023/2024 when V2 lost).

## Pricing (fixed)
Consistent scaling with r = 0.87 (observed traded 7d-ATM / DVOL, research/tournament/oc_vrprobust/tmp/B.json): sale 0.97 x r x DVOL, SL marks
1.05 x r x DVOL, TP marks 1.0 x r x DVOL; everything else = V2 (oc_vrpstraddle PLAN.md). Reproduce oc_vrpconsistent's R087 row first if it is
already available (else implement the scaling and state that it could not be cross-checked).

## Gate (ex-ante, per coin per Friday, information <= 08:05)
gap = r x DVOL(08:00) - RV7, RV7 = annualised std of 1m log returns over the 7 days before 08:00 (sqrt(525600) scaling), both in decimals.
- G1: sell only if gap >= 0.05.   - G2: sell only if r x DVOL / RV30 >= 1.15 (RV30 over 30 days).
Rows: V2 ungated (R087), G1, G2 - standalone dev4 and G2 overlay f = 0.25 dev4; choose on dev4 with the robust criterion; most recent year once for
the chosen row. Report the share of weeks sold, mean gap of sold vs skipped weeks, and per-year results.
Verdict (Vietnamese 3 lines): does a gate turn the realistic-priced sleeve into a clear overlay gain (dev4 mean AND worst year above G2,
DD <= G2 + 0.5)?
