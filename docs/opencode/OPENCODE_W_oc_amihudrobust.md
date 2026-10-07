# OpenCode task oc_amihudrobust - is the Amihud A1 book tilt real? frictions, jitter, timing placebo, "just overweight XRP?" control
Read docs/opencode/OPENCODE_W_COMMON_20261007.md and docs/opencode/OPENCODE_W_TEMPLATE_BOOKGATE_20261007.md first. Write ONLY
`research/tournament/oc_amihudrobust/` and `tests/test_oc_amihudrobust.py`. Print progress every 10 minutes. Engine runs via heavy_slot.

## Context
research/tournament/oc_lit_xs (read REPORT.md, PLAN.md and its code; copy, do not edit): A1 = book weights x (1 + 0.25 z), z = cross-sectional
z-score (across the 5 coins at the same bar) of each coin's trailing-30-day Amihud illiquidity (|daily return| / daily quote volume), applied
to both long and short weights on standard book rows (v426 mechanism). dev4 5.844 / worst 2.798 / DD 16.81 vs G2 5.601 / 2.588 / 16.91;
most recent year 4.750 / 11.14 vs 4.648 / 12.90. It was 1 of ~20 variants screened today -> multiple-testing risk. All rows below are
ROBUSTNESS of the frozen A1 (no re-selection); report dev4 and the 5-year path.

## Rows (4-phase engine, reproduce G2 and A1 to the digit first)
1. Frictions on A1 and G2 (copy the five friction rows of the v421 audit: research/parallel/rounds/parallel-20260906-r2/v421_audit/ROBUST.md
   or research/tournament/oc_carryfric for definitions: S1 doubled fees, S2 latency 15 min, S3 latency 30 min, S4 stop slip, S5 Bybit
   prices - use exactly the existing implementations; if one is not reproducible, say so).
2. Jitter (A1 only): K in {0.15, 0.35}; Amihud window in {20, 45} days (4 rows, one knob each).
3. Timing placebo: 50 runs where each coin's z series is block-shifted in time by a random offset (multiple of 30 days, within the same year,
   cross-sectional demeaning recomputed) - distribution of dev4 mean; report A1's percentile. If 50 engine runs exceed the compute budget,
   run the vectorised book-timing proxy of research/tournament/oc_bookattrib (analyze_bookattrib.py) for 500 placebos instead and say so.
4. "Static coin tilt" control: per coin a CONSTANT multiplier per year = that coin's mean A1 multiplier over the TRAINING window (the year
   before the anchor) - tests whether A1 is just a slow per-coin overweight (e.g. XRP) rather than time-varying.
5. Per-coin decomposition of A1's gain vs G2 (vectorised book timing per coin, as oc_coinattrib).
Verdict (Vietnamese 3 lines): robust (gain > 0 under every friction, all 4 jitters > G2, placebo pct >= 90, beats the static control) or not.
