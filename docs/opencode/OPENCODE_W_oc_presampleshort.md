# OpenCode task oc_presampleshort - re-score the stored pre-sample book-member predictions at SHORT horizons (4h..3d)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_presampleshort/` and `tests/test_oc_presampleshort.py`.
Print progress every 10 minutes. Light job (no training).

## Why
research/tournament/oc_bookichorizon: the DEPLOYED book's skill lives at short horizons h = 1, 2, 6, 18 four-hour bars in the time-series
dimension (pooled IC +0.02..+0.04, 4/4 dev years for all six members, also positive in the most recent year), not at the 7-day label (h = 42,
2022 flips). The pre-sample generality tests (research/tournament/oc_presamplebook: TV-only member; oc_presampleflow: FLOW, PREMIUM, BLEND)
scored only the 7-day label and found ~0 - possibly the wrong horizon. Their per-bar predictions are stored: preds_<anchor>.csv in both folders
(anchors 2019-03-01, 2019-09-24, 2020-03-01 pre-sample on spot; 2021-09-24 .. 2024-09-24 reference on spot / perp as each report says).

## Method (fixed; identical yardstick to oc_bookichorizon)
For every stored prediction series (presamplebook TV; presampleflow FLOW, PREMIUM, BLEND) and every test year: target
y(t, coin, h) = (open[t+h] / open[t] - 1) / sigma[t], sigma = trailing-360-bar std of 1-bar open returns (min 120, causal), opens from the SAME
price series the prediction file was built on (spot 4h for pre-sample; read each worker's code / PLAN to get the exact bars), h in
{1, 2, 6, 18, 42}. Report pooled IC with block bootstrap CI (block = h, min 6), TS mean (per-coin IC averaged) and XS mean, per year.
Key question in bold: in the pre-sample years 2019-2020, are the short-horizon (h = 1..18) ICs positive like the deployed book's 2021-2025
ICs (sign and rough size), for which member families? State plainly that these are rebuilt members (spot flow, TV-only), not the deployed
perp-flow blend. Vietnamese 3-line verdict.
