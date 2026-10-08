# OpenCode task oc_fmbookic - do Chronos / Toto / TimesFM median forecasts carry BOOK direction information? (descriptive, clean year)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_fmbookic/` and `tests/test_oc_fmbookic.py`.
Print progress every 10 minutes. DIAGNOSTIC ONLY - nothing is selected. Light (no engine, no GPU).

## Method
Exactly like research/tournament/oc_kronosfeat Table 2 (book part; its compute_book.py is the template; its yardstick starts at the bar open T
at which the features are known - keep that timing): for the q50 forecasts of research/tournament/oc_chronos (ch_q50), oc_toto and oc_timesfm,
and their spread (q90 - q10), the pooled and per-coin Spearman IC vs y_h = (open[T+h]/open[T] - 1)/sigma for h = 1, 2, 6, 18, with week-block
bootstrap CIs, per year (dev years labelled; post-release year clean for all three), plus the IC vs |y_h| (vol forecasting) and the
correlation with the deployed book weights (research_books_d2). Vietnamese 3 lines: does any FM median carry book direction on the clean year?
