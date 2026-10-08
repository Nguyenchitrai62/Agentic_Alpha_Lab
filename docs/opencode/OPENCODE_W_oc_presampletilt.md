# OpenCode task oc_presampletilt - do the vol / Chronos dip-size tilts work in the PRE-SAMPLE years 2017-2021? (is 2023-2026 the exception?)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_presampletilt/` and `tests/test_oc_presampletilt.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome. CPU for RV6 / GARCH; Chronos inference on GPU via heavy_slot
(reuse research/tournament/oc_chronos/pylib and its run script; model revision 772f3d25d38aec6d914c8949dab4462e2d46f5d8). RAM is tight.

## Why
oc_voltilt / oc_chronos / oc_toto / oc_timesfm / oc_kronoshidden: every "bigger dip rungs when downside vol is forecast high" tilt times dips
well in 2023-2026 and not in 2021-2022. Chronos-Bolt and RV6 / GARCH never saw crypto, so years BEFORE 2021 are genuinely unseen for them.
research/tournament/oc_presample + oc_presample2 already replay the frozen dip sleeve on 2017-2020 (pre-sample) - reuse that machinery.

## Method (fixed)
Pre-sample years = the yearly windows oc_presample2 used (2017 .. 2020-09-23, plus 2020-09-24..2021-09-23 if available), majors available on
Binance at the time (say which). Features at each 4h bar open T on the same 4 clocks: risk_RV6, risk_GARCH (oc_voltilt definitions; GARCH
parameters = the anchor-2021 fit frozen from oc_voltilt/garch_params.json), C2 risk = -ch_q10 (Chronos inference exactly as oc_chronos; needs
512 prior 4h bars, so the first usable bar is ~85 days after the data start). Multipliers with the EARLIEST frozen fits (oc_voltilt and
oc_chronos anchor-2021 entries: direction, q20, q80) - a fixed rule applied to unseen years, labelled "fit from later data, rule frozen".
Evaluate on the pre-sample dip replica ledger (same D0 + B1 replica as oc_k2placebo / oc_tiltgate): per year the normalised tilt gain
(sum mult x pnl / mean mult vs sum pnl) and the timing placebo percentile (1000 within-year permutations, + 42-bar block permutations).

## Report
Per pre-sample year x {V_RV6, V_GARCH, C2}: n fills, normalised gain, timing pct, block pct; plus the same numbers for 2021-2026 from the
existing reports side by side. Verdict (Vietnamese 3 lines): in how many of ALL available years (pre-sample + 2021-2026) does each tilt help,
and is 2023-2026 the rule or the exception?
