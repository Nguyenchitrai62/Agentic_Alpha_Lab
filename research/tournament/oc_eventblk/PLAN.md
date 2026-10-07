# oc_eventblk PLAN (pre-registered BEFORE any outcome is computed)

Idea #16: scheduled US-macro event blackout for dip bids.

## Hypothesis (fixed here)

Flushes on scheduled macro news (FOMC statement, US CPI) are
information-driven and trend, while the dip ladder's edge is
liquidity-driven mean reversion. Dip rungs whose 4h holding bar contains
a scheduled FOMC-statement or CPI release therefore have lower mean
outcome than other rungs. Sign is read from the data (negative
expected); consistency across anchor years is what matters (rule below).
ONE scored flag only (pooled FOMC+CPI blackout); per-series splits are
descriptive readouts, not variants.

## Data (fixed here)

- Fills: `research/tournament/ext/fills_U_ext.parquet`. Universe MAIN =
  majors {BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT} x R2 depths x1 in
  {2.5, 3.0, 3.5, 4.0, 5.0} (6876 rows; per-year T-counts 990/1045/1330/
  989/1144, verified from counts only, no outcomes inspected).
  T = t_fill - f minutes (all T on 4h boundaries). Outcome = y_dep only
  (exact net return at the DEPLOYED TP per rung from
  `research/parallel/rounds/parallel-20260906-r2/v376/tables_hidden/
  r2_table_s0.parquet` via `research/tournament/ext/harness5.py::load`,
  i.e. exactly as oc_idea7 loads it; fees + adverse funding already
  inside). TP unchanged by this idea.
- Calendar: `event_calendar.csv` in this folder (built by
  `build_calendar.py` from the raw pages in `raw/` + `manifest.json`;
  no market data, no outcome data). Sources: federalreserve.gov FOMC
  meeting calendars (statement = second meeting day, 14:00 ET) and the
  BLS CPI release schedule (08:30 ET), fetched 2026-10-05 (Fed live;
  BLS via web.archive.org snapshots — direct BLS fetch returns 403
  from this network; archived bytes are the same official pages).
  All release dates are scheduled far in advance (known before each
  anchor year), so using them is causal.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment
  override; all five years are research data; any finding needs
  prospective validation). This study loads NO 1m/hourly/dvol data:
  only fills_U_ext + the calendar (LIGHT: one process, RAM < 1 GB).

## Calendar (exact, fixed here)

Scope: 2020-08-01 .. 2026-09-24 00:00 UTC (events at/after the cutoff
are dropped: FOMC 2026-10-28/12-09, CPI releases at/after 2026-09-24).

Release times (standard, ET): FOMC statement 14:00 ET; CPI 08:30 ET.
UTC conversion by US daylight saving on the release date: EDT (UTC-4)
-> FOMC 18:00 UTC, CPI 12:30 UTC; EST (UTC-5) -> FOMC 19:00 UTC,
CPI 13:30 UTC. DST in effect from the second Sunday of March (02:00
local) to the first Sunday of November (02:00 local): 2020: Mar 8-Nov 1;
2021: Mar 14-Nov 7; 2022: Mar 13-Nov 6; 2023: Mar 12-Nov 5;
2024: Mar 10-Nov 3; 2025: Mar 9-Nov 2; 2026: Mar 8-Nov 1. A release
date strictly inside [start, end) is EDT, else EST.

FOMC statement dates (second meeting day; 2021+ as vetted by oc_macro
from federalreserve.gov; 2020 tail added here, verified against the
Fed 2020 calendar raw page):
2020 (scope tail): 07-29, 09-16, 11-05, 12-16.
2021: 01-27, 03-17, 04-28, 06-16, 07-28, 09-22, 11-03, 12-15.
2022: 01-26, 03-16, 05-04, 06-15, 07-27, 09-21, 11-02, 12-14.
2023: 02-01, 03-22, 05-03, 06-14, 07-26, 09-20, 11-01, 12-13.
2024: 01-31, 03-20, 05-01, 06-12, 07-31, 09-18, 11-07, 12-18.
2025: 01-29, 03-19, 05-07, 06-18, 07-30, 09-17, 10-29, 12-10.
2026 (before cutoff): 01-28, 03-18, 04-29, 06-17, 07-29, 09-16.

CPI release dates (08:30 ET; 2021+ as vetted by oc_macro from the BLS
schedule; 2020 tail added here, verified against archived BLS pages):
2020 (scope tail): 08-12, 09-11, 10-13, 11-12, 12-10.
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
2026 (before cutoff): 01-13 (Dec-25 ref), 02-13, 03-11, 04-10, 05-12,
  06-10, 07-14, 08-12, 09-11.

Cross-check rule (calendar construction, NOT outcome tuning — done
before any y_dep statistic is computed): `build_calendar.py` asserts
every listed date appears in the saved raw pages (Fed yearly calendars
for FOMC; archived BLS cpi.htm snapshots spanning 2020..2026 for CPI,
including a post-shutdown snapshot for the 2025 revisions). A listed
date missing from the officials is dropped and logged; an official
date missing above is added and logged. Either way the deviation is
disclosed in REPORT.md. Outcomes play no role in this step.

Raw provenance: `raw/` holds the fetched bytes
(Fed fomccalendars index + fomc2020..2026 yearly pages; ~8 archived
BLS cpi.htm snapshots 2020-08..2026-09) and `manifest.json` records
{file, url, fetched_at_utc, sha256, bytes} per file.

## Flags (exact, causal)

EVENTBAR(T) = 1 iff the 4h holding bar [T, T+4h) CONTAINS an event
instant R (FOMC or CPI release_utc), i.e. T <= R < T+4h (assignment
rule verbatim: "skip all majors' dip rungs whose 4h holding bar
contains an event time (no new bids that bar)"). A bid placed at T
knows the pre-published calendar, so the bot can skip exactly these
bids. FOMC_ONLY / CPI_ONLY use that series' instants only
(descriptive). No windows, no market read, no fill-time read.

## Evaluation (fixed here — one variant only)

- Anchor years (5): Y_k = [A_k, A_k + 365d) by T,
  A in {2021-09-24 .. 2025-09-24} (UTC).
- Per anchor year: n, n_in (EVENTBAR=1), n_out; mean y_dep in/out (bps;
  1 bps = 1e-4) + win rates (y_dep > 0) + min y_dep in/out (bps);
  spread = mean_in - mean_out (bps; negative expected = event bars
  worse). Minimum-n: a year's spread is valid only if n_in >= 5 AND
  n_out >= 30, else NaN = FAIL for the sign count (never imputed).
  (5, not 30: instant-in-bar covers ~1% of bars so ~10 event rungs/yr
  are expected; thinness is reported, not hidden.)
- Blackout translation (size-weighted, harness5 equal-exposure renorm):
  size_new = 0 on EVENTBAR rows else size_dep; per-year S_dep =
  sum(size_dep * y_dep), S_new = sum(size_new_renorm * y_dep),
  gain = S_new - S_dep (PASS_gain: gain > 0). Raw (no-renorm) S_skip vs
  S_full retention is descriptive.
- Tail per year on the RENORMALISED daily path (daily sums of
  size*y_dep grouped by floor(T) day UTC): worst_day with/without;
  PASS_tail: W_new >= W_dep (strictly not worse). maxDD of the cumsum
  daily-sum path with/without is reported per year + pooled
  (descriptive, not in the rule).
- LOYO agreement (fixed calendar: no cut-offs to learn; oc_macro /
  oc_expiry precedent): pooled_other4_h = mean_in - mean_out over rows
  of the other 4 anchor years pooled (NaN if either side < 5 rows);
  agree_h = sign(spread_h) == sign(pooled_other4_h), both nonzero.
- DECISION RULE (assignment default + tail clause): PROMISING iff
  (a) sign(spread) is identical (all nonzero, same sign) in >= 4 of 5
  anchor years (NaN = fail), AND (b) agree_h holds in >= 4 of 5
  held-out years (NaN = fail), AND (c) PASS_tail holds in >= 4 of 5
  years. Gain sign agreement is reported; a gain/spread sign conflict
  in >= 2 years is logged as a caveat. Otherwise NOT PROMISING.
- Cost context: y_dep already nets ~4-8 bps round-trip cost + adverse
  funding; sums in native units, means also shown in bps.

## Causality / correctness tests (tests/test_oc_eventblk.py)

- test_universe_counts: majors-R2 join yields 6876 rows with
  990/1045/1330/989/1144 per anchor year; every T < 2026-09-24 and on
  a 4h boundary; outcome column is y_dep from harness5.load.
- test_calendar_utc: spot UTC conversion (FOMC 2022-01-26 -> 19:00
  EST; FOMC 2022-06-15 -> 18:00 EDT; CPI 2024-01-11 -> 13:30 EST;
  CPI 2024-06-12 -> 12:30 EDT; FOMC 2020-09-16 -> 18:00 EDT;
  CPI 2020-08-12 -> 12:30 EDT); no event at/after 2026-09-24;
  expected row count = 50 FOMC + 73 CPI; manifest sha256 re-verified.
- test_eventbar_causal: EVENTBAR from T + calendar only (market/y
  columns droppable without change); hand-checked boundaries on a
  CPI day (T=R-4h+epsilon inside/outside; bar containing R vs next
  bar); instant-in-bar predicate, NOT window overlap (a bar starting
  after R+0 is excluded even if within 5h of R).
- test_decision_counts_match: results.json counts recomputed from
  yearly passes equal the stored decision strings.

## Deliverables

research/tournament/oc_eventblk/: PLAN.md (this file), fetch_raw.py,
raw/*, manifest.json, build_calendar.py, event_calendar.csv,
analyze_eventblk.py, results.json, REPORT.md (tables + one-line
verdict). tests/test_oc_eventblk.py. No commits, no edits outside
these two paths. One process, fills + calendar only, RAM < 1 GB.
