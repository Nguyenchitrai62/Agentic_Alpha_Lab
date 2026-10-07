# OpenCode task oc_tiltgate - can a parameter-free walk-forward gate keep the vol-timing dip tilt only in regimes where it works?
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_tiltgate/` and `tests/test_oc_tiltgate.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome. Engine via heavy_slot (RAM tight: one engine job at a time).

## Why
research/tournament/oc_voltilt: the dip-size vol tilts (V_RV6, V_GARCH; same signature as the foundation-model tilts K2 / C2 / Toto / TimesFM)
time dips well in 2023-2026 (placebo pct 97-100) but not in 2021-2022 (pct 2-19), so they lose the robust dev pick on the 2021 worst year.
Question: does a PARAMETER-FREE "follow last year" gate, decided at each anchor from data before A - 7 d only, keep the good regimes and skip
the bad ones?

## Rule (pre-registered, no free parameter)
For anchor A (2021..2025): tilt ON for the whole year [A, A+365d) iff the tilt's effect on the dip-rung replica over the 12 months
[A - 372 d, A - 7 d) is > 0, where effect = sum over fills of (mult - 1) x net rung P&L divided by the number of fills, with the multiplier
computed by the anchor-(A - 1 year) fit... (use exactly the fit that WAS live in that prior year: anchor A-1's fits.json entry; for A = 2021 the
prior year 2020-09-24..2021-09-17 needs a 2020 fit: fit it like make_fits.py on harness rows t_exit < 2020-09-17 if the harness has enough
rows (>= 1000), else gate = OFF for 2021 and say so). Replica: research/tournament/oc_placebo_dip / oc_k2placebo ledger (extend it to
2020-09-24 .. 2021-09-23 with the same code if needed - research/tournament/oc_presample2 has the pre-sample dip machinery).
Variants (exactly two): G_RV6 (V_RV6 gated), G_GARCH (V_GARCH gated). Features / fits from research/tournament/oc_voltilt (frozen).

## Report
Gate decision per anchor for each variant (with the effect value and n fills), engine rows REF / G_RV6 / G_GARCH (an OFF year is exactly REF;
reuse oc_voltilt's runs for ON years when bit-identical), dev4 robust pick among REF / G_RV6 / G_GARCH (DD <= 20, no losing year, highest
WORST, ties -> mean), post-release year scored ONCE (labelled), 5y, full-path DD. Vietnamese 3-line verdict.
