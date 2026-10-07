# OpenCode task oc_kronosfeat - which Kronos features carry information on the CLEAN post-release year? (dips and book; descriptive only)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_kronosfeat/` and `tests/test_oc_kronosfeat.py`.
Print progress every 10 minutes. DIAGNOSTIC ONLY - nothing is selected; the post-release year has been scored once for K2 already.

## Inputs
research/tournament/oc_kronoshidden/kronos_features_4shift.parquet (sym, shift, T, er1, er6, vol1, vol6, rng1, low1, pdrop2, pdrop3, sigma,
C0; all four clock shifts, 2020-10 .. 2026-09-23). Dip replica: research/tournament/oc_placebo_dip/compute_placebo_dip.py (reproduce base 7.718).
Book: realised next-bar open-to-open returns on each shift's 4h bars (research/tournament/oc_kronoshidden/bars_4h_4shift.parquet).

## Tables (per year; dev years labelled "inside Kronos pretraining = upper bound"; post-release year = clean)
1. DIPS: Spearman of each feature (as of the rung's holding-bar open, same shift) vs the rung outcome; outcome by feature quintile; stop rate
   by quintile.
2. BOOK: Spearman IC of er1 / er6 / low1 / pdrop2 / vol1 vs the vol-normalised forward return at h = 1, 2, 6, 18 bars (yardstick of
   research/tournament/oc_bookichorizon: y = (open[t+h]/open[t] - 1)/sigma), pooled and per coin, with block bootstrap CIs; also the IC of
   those features vs |return| (volatility forecasting).
3. Correlation between Kronos features and the deployed book weights / the B1 flush count (is Kronos information new relative to G2?).
Key question in bold: on the clean year, which features carry dip and book information, and is any book IC positive at short horizons?
Vietnamese 3 lines.
