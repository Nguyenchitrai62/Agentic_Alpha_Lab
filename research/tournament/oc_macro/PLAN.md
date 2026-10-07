# oc_macro PLAN (pre-registered BEFORE any outcome is computed)

## Question

Do dip-rung fills exposed to scheduled US macro releases (FOMC statement,
CPI, NFP) perform worse than fills outside those windows, and would skipping
dip bids over macro windows (the bot can cancel resting bids) improve the
yearly daily-sum worst day without giving up > 5% of the yearly sum?

## Hypothesis (fixed here)

Scheduled macro releases inject volatility/whipsaw that the dip ladder is
not paid to hold through: fills whose 4h holding bar overlaps a release
window have lower mean y1.0 than fills outside. Sign is read from the data;
consistency across anchor years is what matters (PROMISING rule below).

## Data (fixed here)

- Fills: `research/tournament/ext/fills_U_ext.parquet`. Universe MAIN =
  majors {BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT} x R2 depths x1 in
  {2.5, 3.0, 3.5, 4.0, 5.0} (~6876 rows; per-year T-counts ~990/1045/1330/
  989/1144, verified from counts only, no outcomes inspected).
  T = t_fill - f minutes (all T on 4h boundaries). Outcome = y1.0 only (net
  return at TP 1.0 sigma, unit rung size; y0.5/y1.5 NOT scored). Reported in
  bps (1 bps = 1e-4); round-trip cost ~4-8 bps.
- Calendar: `macro_calendar.csv` in this folder (built by
  `build_calendar.py` from the hard-coded date lists below; no market data,
  no outcome data, no network at analysis time). Sources: FOMC statement
  dates = second day of each scheduled FOMC meeting from
  federalreserve.gov/meeting-calendars (fomccalendars.htm, fetched
  2026-10-05); CPI release dates = BLS "Schedule of Releases for the
  Consumer Price Index" + BLS "Schedule of Selected Releases" yearly pages
  (bls.gov/schedule); NFP/Employment Situation dates = BLS "Schedule of
  Releases for the Employment Situation" + ALFRED release-date history
  (rid 50) cross-checked against the BLS yearly schedules. All three
  calendars are published in advance (known before each anchor year).
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides
  the old RULES.md hidden-year cut; all five years are research data and any
  finding needs prospective validation). This study loads NO 1m data and NO
  hourly data: only fills_U_ext + the calendar (LIGHT: one process,
  RAM < 1 GB).

## Calendar (exact, fixed here)

Release times (standard, ET): FOMC statement 14:00 ET; CPI 08:30 ET;
NFP (Employment Situation) 08:30 ET. UTC conversion by US daylight saving
on the release date: EDT (UTC-4) -> FOMC 18:00 UTC, CPI/NFP 12:30 UTC;
EST (UTC-5) -> FOMC 19:00 UTC, CPI/NFP 13:30 UTC. DST in effect from the
second Sunday of March (02:00 local) to the first Sunday of November
(02:00 local): 2021: Mar 14-Nov 7; 2022: Mar 13-Nov 6; 2023: Mar 12-Nov 5;
2024: Mar 10-Nov 3; 2025: Mar 9-Nov 2; 2026: Mar 8-Nov 1. A release date
strictly inside [start, end) is EDT, else EST.

FOMC statement dates (8/yr, second meeting day):
2021: 01-27, 03-17, 04-28, 06-16, 07-28, 09-22, 11-03, 12-15.
2022: 01-26, 03-16, 05-04, 06-15, 07-27, 09-21, 11-02, 12-14.
2023: 02-01, 03-22, 05-03, 06-14, 07-26, 09-20, 11-01, 12-13.
2024: 01-31, 03-20, 05-01, 06-12, 07-31, 09-18, 11-07, 12-18.
2025: 01-29, 03-19, 05-07, 06-18, 07-30, 09-17, 10-29, 12-10.
2026 (up to cutoff 2026-09-24): 01-28, 03-18, 04-29, 06-17, 07-29, 09-16
  (10-28 and 12-09 excluded: at/after the cutoff).

CPI release dates (08:30 ET):
2021: 01-13, 02-10, 03-10, 04-13, 05-12, 06-10, 07-13, 08-11, 09-14,
  10-13, 11-10, 12-10.
2022: 01-12, 02-10, 03-10, 04-12, 05-11, 06-10, 07-13, 08-10, 09-13,
  10-13, 11-10, 12-13.
2023: 01-12, 02-14, 03-14, 04-12, 05-10, 06-13, 07-12, 08-10, 09-13,
  10-12, 11-14, 12-12.
2024: 01-11, 02-13, 03-12, 04-10, 05-15, 06-12, 07-11, 08-14, 09-11,
  10-10, 11-13, 12-11.
2025: 01-15, 02-12, 03-12, 04-10, 05-13, 06-11, 07-15, 08-12, 09-11,
  10-24 (September reference, delayed by the federal shutdown; October
  reference NOT published - no event), 12-18 (November reference).
2026 (up to cutoff): 01-13 (Dec-25 ref), 02-13, 03-11, 04-10, 05-12,
  06-10, 07-14, 08-12, 09-11.

NFP / Employment Situation dates (08:30 ET):
2021: 01-08 (Dec-20 ref), 02-05, 03-05, 04-02, 05-07, 06-04, 07-02,
  08-06, 09-03, 10-08, 11-05, 12-03.
2022: 01-07, 02-04, 03-04, 04-01, 05-06, 06-03, 07-08, 08-05, 09-02,
  10-07, 11-04, 12-02.
2023: 01-06, 02-03, 03-10, 04-07, 05-05, 06-02, 07-07, 08-04, 09-01,
  10-06, 11-03, 12-08.
2024: 01-05, 02-02, 03-08, 04-05, 05-03, 06-07, 07-05, 08-02, 09-06,
  10-04, 11-01, 12-06.
2025: 01-10, 02-07, 03-07, 04-04, 05-02, 06-06, 07-03, 08-01, 09-05,
  (October reference NOT published - shutdown; no event),
  11-20 (September reference, delayed), 12-16 (November reference).
2026 (up to cutoff): 01-09 (Dec-25 ref), 02-11, 03-06, 04-03, 05-08,
  06-05, 07-02, 08-07, 09-04.

Event window (fixed): for release instant R (UTC), window = [R, R + 5h)
half-open = the release hour plus the 4 h after. Overlapping windows from
distinct releases (rare; e.g. CPI day near FOMC day never shares the hour,
but CPI+NFP can fall days apart - overlap only if releases < 5h apart,
which never happens across these three series) are merged; flags below use
the union.

## Flags (exact, causal)

Primary SKIP flag (actionable at the bid time T; calendar known in
advance, NO market read): SKIP = 1 iff the holding bar [T, T + 4h)
overlaps ANY event window [R, R + 5h), i.e. T < R + 5h AND R < T + 4h.
A bid placed at T knows the calendar, so the bot can cancel/skip exactly
these bids. Rows with T >= 2026-09-24 00:00 UTC are excluded (none: fills
end 2026-09-23 12:00).

Descriptive-only flags (NOT part of the rule, NOT actionable at T):
FOMC_ONLY / CPI_ONLY / NFP_ONLY = holding-bar overlap with that series'
windows only; FILL_IN = t_fill inside any event window (uses the unknown
fill time; reported to show whether exposure concentrates at fills).

## Evaluation (fixed here)

- Anchor years (5): Y_k = [A_k, A_k + 365d) by T,
  A in {2021-09-24 .. 2025-09-24} (UTC).
- Per anchor year: n, n_in (SKIP=1), n_out; mean y1.0 in/out (bps) + win
  rates (y1.0 > 0) + min y1.0 in/out (bps); spread = mean_in - mean_out
  (bps; negative expected = macro worse). Minimum-n: a year's spread is
  valid only if n_in >= 10 AND n_out >= 10, else NaN = FAIL for the sign
  count (never imputed). Macro windows cover ~1.8% of clock time so small
  n_in is expected; the bar is 10, not 30, and is fixed here.
- Skip simulation per year (unit rung size, descriptive): S_full = sum
  y1.0 over year rows; S_skip = sum y1.0 over year rows with SKIP=0;
  cut = (S_full - S_skip) / S_full (NaN if S_full <= 0; a skip that cuts
  a non-positive sum is not a saving); daily sums grouped by T floor('D'):
  worst_day_full, worst_day_skip; tail_improves = worst_day_skip >
  worst_day_full. Useful-skip bar (descriptive, NOT the PROMISING rule):
  tail_improves AND 0 <= cut <= 5%.
- LOYO agreement for the fixed window (no cut-offs to learn, as in the
  LATE-window precedent): pooled_other4_h = mean_in - mean_out over rows
  of the other 4 anchor years pooled (NaN if either side < 10 rows);
  agree_h = sign(spread_h) == sign(pooled_other4_h), both nonzero.
- DECISION RULE (assignment default, for the pooled ALL-macro SKIP flag):
  PROMISING iff (a) sign(spread) is identical in >= 4 of 5 anchor years
  (NaN = fail), AND (b) agree_h holds in >= 4 of 5 held-out years
  (NaN = fail). Per-series FOMC/CPI/NFP spreads and the FILL_IN readout
  are descriptive ONLY (no decision).
- At most 3 variants: this study has ONE scored flag (pooled SKIP); the
  three per-series splits are descriptive readouts, not variants.

## Causality / correctness tests (tests/test_oc_macro.py)

- test_counts_and_grid: majors-R2 join yields 6876 rows, T on 4h
  boundaries, per-year T counts 990/1045/1330/989/1144; no T at/after
  2026-09-24.
- test_calendar_utc: spot-check UTC conversion (e.g. FOMC 2022-01-26 ->
  19:00 UTC EST; FOMC 2022-06-15 -> 18:00 UTC EDT; CPI 2024-01-11 ->
  13:30 UTC EST; CPI 2024-06-12 -> 12:30 UTC EDT; NFP 2023-03-10 ->
  13:30 UTC EST); windows are exactly 5h half-open; 2025 has no October
  CPI/NFP events; nothing at/after 2026-09-24.
- test_skip_causal: SKIP depends only on T + calendar (recompute from
  T and the CSV; shifting/removing any market column leaves it
  unchanged); holding-bar overlap predicate matches the definition on
  hand-checked cases (T just before / inside / just after a window).
- test_no_outcome_in_flags: flags carry no y-column information
  (recompute flags after dropping y-columns; identical).

## Deliverables

research/tournament/oc_macro/: PLAN.md (this file), build_calendar.py,
macro_calendar.csv, analyze_macro.py, results.json, REPORT.md (tables +
one-line verdict). tests/test_oc_macro.py. One process, RAM < 1 GB, no 1m
data. No tuning on results; any post-hoc change logged in REPORT.md. No
commits, no edits outside the two allowed paths.
