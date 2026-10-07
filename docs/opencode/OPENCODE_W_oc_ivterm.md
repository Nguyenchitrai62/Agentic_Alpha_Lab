# OpenCode task oc_ivterm - option-implied TERM STRUCTURE (7-day ATM IV vs 30-day DVOL) as a state for the dip ladder and the book
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_ivterm/` and `tests/test_oc_ivterm.py`.
Print progress at least every 10 minutes.

## Why
oc_dvol (closed / diagnostic) found dip outcomes better when implied fear (DVOL level vs 90 d) is high, but as a size tilt it only added risk
(v414). The TERM STRUCTURE was never available: with strike-level trades we can measure short-dated ATM IV. Inversion (7-day IV > 30-day
DVOL) marks ACUTE stress (cascade risk) as opposed to elevated-but-calm fear; contango marks calm. oc_vrprobust found the ratio 7d/DVOL
~0.87 on Fridays on average (B.json), with p10 0.79 / p90 0.94.

## Feature (fixed; hourly, known at the end of each hour)
TS(h) = IV_7d_ATM(h) / DVOL(h), IV_7d_ATM = amount-weighted vwap_iv over the last 6 hours of instruments with 3..10 days to expiry and
|K / index - 1| <= 2 % (calls and puts), DVOL = last closed hourly DVOL (data/raw/deribit_dvol_20261005). If fewer than 0.5 coin traded in
the 6 h window -> NaN (carry the last value up to 24 h, then NaN). BTC and ETH; SOL / BNB / XRP use BTC's TS (disclose).
Data: data/raw/deribit_strike_20261007 (+ _b) (see docs/opencode/OPENCODE_W_oc_optflow.md for columns).

## Descriptive (dev years only)
- Distribution of TS per year; share of hours with TS > 1 (inversion).
- DIPS: dip replica of research/tournament/oc_placebo_dip (reproduce base 7.718 first): per year, rung outcome and stop rate by TS tercile and
  for TS > 1 vs <= 1, as of the last full hour before the bar open.
- BOOK: per year IC of TS vs next 24 h vol-normalised returns per coin.
Candidate rule only if the sign of (TS high -> worse dips) OR (TS high -> better dips) is the same in 4/4 dev years with a tercile spread
> 5 bps per rung; THEN (and only then) score ONE pre-registered tilt with the established dip gate: rung x0.6 when TS > its training p80 (if
high TS = worse) or x1.3 (if high TS = better), terciles / p80 from training rows before each anchor - 7 d; exposure-matched control; dip gate
legs + dSum5y >= +0.273 (labelled 5-year calibration). Vietnamese 3-line verdict.
