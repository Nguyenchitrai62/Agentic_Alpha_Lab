# OpenCode task oc_hlspread - Hyperliquid-minus-Binance funding DISAGREEMENT as a book signal (idea B1; SHORT-SPAN, descriptive + one tilt)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_hlspread/` and `tests/test_oc_hlspread.py`.
Print progress at least every 10 minutes. Read docs/opencode/IDEAS_20261007c.md (B1, D4) and research/tournament/data_hlfunding/REPORT.md.

## Data
`data/raw/hyperliquid_20261007/HL_<COIN>_funding_1h.parquet` (hourly funding 2023-05-12+, XRP 2023-06-18+) and Binance settled funding
(data/raw/binance_premium_20260928 - see data_hlfunding's analysis code for loading; it ends 2026-08-31: state the exact overlap end).
Only the anchor years 2023-09-24 and 2024-09-24 have usable history (and 2025-09-24 partially) - label everything SHORT-SPAN; no dev4 selection.

## Signal (fixed)
D(T) = HL 8h-summed funding minus Binance 8h funding, averaged over the last 7 days (21 settlements) as of bar T; z(T) = (D - trailing 1-year
mean) / std (min 120 days; NaN -> no signal). Hypothesis fixed now: |z| large = crowded / segmented tape -> the book's position in that coin
should be SMALLER (contrarian to crowding) - specifically z > +1.5 (HL longs paying much more) -> book LONG weights x0.5; z < -1.5 -> book
SHORT weights x0.5.

## Tests
1. Descriptive (2023-05..2025-09-23 only): per coin, Spearman IC of z vs next 24 h / 7 d vol-normalised return; share of bars with |z| > 1.5.
2. Engine (4-phase, heavy_slot) on top of G2 (v421 RUNS rule inv k 1.0 kd 1.7 bear True G 2.0; reproduce 5.41 / 16.91 / 16.82 first), with the
   per-(T, sym) book multiplier mechanism of research/parallel/rounds/parallel-20260906-r2/v426/v426_book_brake.py: rows H1 (the rule) and CTRL
   (exposure-matched constant multiplier); report per anchor year 2023, 2024, 2025 (the last labelled most-recent-year, scored once).
Vietnamese 3-line verdict: at best "log prospectively"; no deployment from this span.
