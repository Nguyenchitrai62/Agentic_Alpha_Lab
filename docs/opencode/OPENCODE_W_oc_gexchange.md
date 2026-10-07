# OpenCode task oc_gexchange - CHANGES in the dealer-gamma proxy (not levels) vs dip-rung outcomes (descriptive, pre-registered)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_gexchange/` and `tests/test_oc_gexchange.py`.
Print progress at least every 10 minutes.

## Context
research/tournament/oc_gex (read REPORT.md, PLAN.md, gex_lib.py): the GEXn LEVEL proxy (gex_hourly_BTC/ETH.parquet in that folder) does not
predict dip rungs (right sign 2/4 dev years). Its own suggestion: test CHANGES. Reuse its hourly GEXn files and its dip-replica join unchanged.

## Feature and rule (fixed now)
dG(T) = GEXn(last full hour before T) - GEXn(24 h earlier), divided by the trailing 90-day std of 24 h changes (z). Hypothesis direction fixed
now: dealers getting SHORTER gamma fast (dG z < -1) -> worse rungs / more stops.
Descriptive per dev year: Spearman(dG, rung outcome), outcome and stop rate for z < -1, -1..1, > 1. Candidate only if the hypothesised sign
holds in 4/4 dev years with a spread > 5 bps per rung; THEN one tilt (rung x0.7 when z < -1) scored with the established dip gate (legs +
dSum5y >= +0.273, labelled 5-year calibration) + exposure-matched control. Otherwise stop after the descriptive table. Vietnamese 3 lines.
