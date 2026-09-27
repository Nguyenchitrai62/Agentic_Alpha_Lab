# pattern_lab W2: classical chart patterns (read OPENCODE_PATTERN_LAB_COMMON.md first)

Files you may write: `src/agentic_alpha_lab/patterns/chart.py`,
`tests/test_pattern_lab_chart.py`, `research/pattern_lab/chart_study.py`,
`artifacts/research/pattern_lab/chart/*`. Column prefix: `chp_`.

Pivots: implement causal swing detection (a) fractal high/low with k right-side
bars, available only at bar i+k, and (b) ATR-threshold zigzag whose last leg is
confirmed only when price reverses by the threshold. Test explicitly that a
pivot is not visible before its confirmation bar.
Patterns, each firing ONLY at the confirmation/breakout bar: double top and
double bottom (neckline break), triple top/bottom, head and shoulders and
inverse H&S (neckline break, shoulder symmetry tolerance), ascending /
descending / symmetric triangle breakouts, rectangle/range breakout, bull and
bear flag, rising/falling wedge, horizontal support/resistance break and retest
(levels from confirmed pivots), Donchian 20/55 breakout. Tolerances in ATR
units, recorded as constants; use at least two pivot scales (small and large).
compute(): distance of close to last confirmed pivot high/low and to active
neckline/support/resistance in ATR, bars since last pivot, pattern height in
ATR, trend of pivot highs/lows (higher-highs/lower-lows counts).
