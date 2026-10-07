# OpenCode task oc_kronosbookvol - book exposure scaled by Kronos' forecast volatility (4-phase engine)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_kronosbookvol/` and `tests/test_oc_kronosbookvol.py`.

## Why
research/tournament/kronos/REPORT.md: Kronos-small's zero-shot volatility forecast is much better than trailing sigma (rng1 IC 0.19-0.28 vs
360-bar sigma 0.05-0.12; only +0.01..+0.06 over a 42-bar trailing std). Earlier vol-sizing of the book (v129 small gain; v251 strategy vol
targeting rejected) used trailing estimators. CAVEAT: the dev years are probably inside Kronos' pretraining data (released 2025-08) -> dev =
upper bound; the most recent year 2025-09-24 .. 2026-09-23 is post-release = the clean test.

## Inputs
Kronos features for all four clock shifts: `research/tournament/oc_kronoshidden/kronos_features_4shift.parquet` (sym, shift, T, sigma, C0, er1,
er6, vol1, vol6, rng1, low1, pdrop2, pdrop3; produced by the oc_kronoshidden worker; check that all 20 (shift, sym) groups are complete before
starting - if not, wait / poll every 10 minutes, at most 2 hours). Feature at bar open T uses only bars closed <= T.

## Rule (fixed; 4-phase engine on top of G2)
Copy the per-(T, sym) book-long/short multiplier mechanism of research/parallel/rounds/parallel-20260906-r2/v426/v426_book_brake.py BUT apply it
per clock shift with that shift's own Kronos row (shift s rows feed phase s; if the v426 mechanism only acts on standard rows before the
shifted-clock forward fill, implement the per-shift application in your copy and prove with a test that phase s only sees features with T <= its
bar open). Reproduce G2 (v421 RUNS: rule inv, k 1.0, kd 1.7, bear True, G 2.0; 5.41 / 16.91 / 16.82) first.
- KV1: book weight x m, m = clip(median_train(vol1) / vol1, 0.6, 1.4), median over the training rows of that anchor (all T < A - 7 d, same sym)
  - inverse forecast-vol scaling, both long and short.
- KV2: same with rng1 instead of vol1.
- CTRL: the same formula with the trailing 42-bar realised std ratio (sigma42 / sigma) instead of Kronos (the cheap baseline the Kronos report
  compared against) - Kronos must beat CTRL to claim value.
Score dev4 (4-phase reset metric, yearly DD, full-path DD), choose KV1 vs KV2 on dev4 by the robust criterion, then the most recent year ONCE for
the chosen row, CTRL and G2. Verdict (Vietnamese 3 lines) uses the most recent year as the clean evidence.
