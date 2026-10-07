# OpenCode task oc_coinattrib - per-coin and per-side attribution of G2 (book timing + dip sleeve): concentration risk
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_coinattrib/` and `tests/test_oc_coinattrib.py`.
Print progress at least every 10 minutes.

## Why
oc_bookattrib established that the book earns by timing (all years). Unknown: is it concentrated in one or two coins (concentration risk if
that coin's microstructure changes, e.g. a listing / ETF regime), and which coins carry the dip sleeve.

## Method (descriptive; reuse code)
- Book: reuse research/tournament/oc_bookattrib/analyze_bookattrib.py (vectorised gross B = sum w r with the deployed book rows, bear filter,
  4 clocks) and split B, BETA, TIMING and the block-shuffle placebo PER COIN and per side (long / short) per year (dev years + the most recent
  year labelled). Report each coin's share of total timing per year and the Herfindahl index of the shares.
- Dips: from the dip replica (research/tournament/oc_placebo_dip, base 7.718) per coin per year: sum, DD contribution (coin P&L during the
  top-5 sleeve DD episodes), win, stop rate.
- Leave-one-coin-out (vectorised, labelled): book timing and dip sum without each coin.
Key question in bold: is any single coin > 40 % of G2's timing or dip P&L in most years? Vietnamese 3-line verdict with the live-risk note.
