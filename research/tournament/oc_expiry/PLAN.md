# oc_expiry PLAN (pre-registered BEFORE any outcome is inspected)

Question: does the known Deribit options-expiry calendar separate good from
bad dip-fill outcomes or book P&L? Deribit expires monthly options on the
LAST FRIDAY of each month at 08:00 UTC (quarterlies = Mar/Jun/Sep/Dec) —
a pure calendar, known years in advance, hence zero leakage by construction.

## Hypothesis (fixed here)

Expiry weeks (and the hours around the expiry) show systematically different
dip-fill outcomes y1.0 (sign read from the data; consistency is what matters).
A window effect is PROMISING only under the sign-consistency rule below.

## Data (fixed here)

- Fills: `research/tournament/ext/fills_U_ext.parquet` (rows with
  t_fill < 2026-09-24 00:00 UTC only). Universe MAIN = majors
  {BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT} x R2 depths x1 in
  {2.5, 3.0, 3.5, 4.0, 5.0}. T = t_fill - f minutes (4h bar open).
  Outcome = y1.0 only (net return at TP 1.0 sigma, unit rung size).
- Books: rebuilt EXACTLY as `scripts/forward_v205.py::research_books_d2`
  from `artifacts/research/engine_real/` (same files, same math as
  oc_bookvol/oc_bookic). Opens: `opens_v154.parquet` (4h opens).
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides
  the old RULES.md hidden-year cut; findings still need prospective
  validation). No 1m data, one process, RAM < 1 GB (fills + two 4h frames).

## Exact causal definitions (fixed now)

- Expiry calendar (pure function of year/month, no market input):
  E(y, m) = last Friday of month m, 08:00 UTC. Quarterly iff m in
  {3, 6, 9, 12}. Expiries generated for 2021-01 .. 2026-09.
- Windows per expiry E (half-open [start, end), T is the bar-open / fill T):
  * WEEK:  [Monday 00:00 of E's week, E) = [E - 4d8h, E).
  * PRE24: [E - 24h, E) (subset of WEEK, evaluated separately).
  * POST24: [E, E + 24h).
  A fill/bar with time T is inside window W iff T in W for some expiry.
  Windows are known before the year starts; assignment uses only T.
- Anchor years (5): Y_k = [A_k, A_k + 365d) by T,
  A in {2021-09-24 .. 2025-09-24} (UTC).
- Dip per (year, window): mean y1.0 inside vs outside in bps (1 bps = 1e-4),
  n each; spread_W,y = mean_in - mean_out. NaN if < 30 fills inside
  (counts as FAIL for the sign count, never imputed).
- Dip daily worst (descriptive only): sums of y1.0 over inside fills grouped
  by day-floor(T) -> worst inside day; same over outside fills. Not in rule.
- Book per (year, window): grid = inner join of books/optens index; weight
  w_c[t] known at close of bar t; next-bar return r_c[t] = open[t+1]/open[t]-1;
  gross u[t] = sum_c w_c[t]*r_c[t] (no costs). Bar assigned by its open T.
  Mean u per bar inside vs outside (bps), sums, n. Descriptive only.
- Quarterly vs monthly split (descriptive only): pooled 5y WEEK spread for
  quarterly-expiry weeks vs non-quarterly-expiry weeks.
- LOYO stability for the WEEK dip spread: pooled spread of the other 4 years
  S_{-h}; LOYO_h passes iff sign(spread_h) == sign(S_{-h}) and both non-zero
  (NaN -> fail).
- DECISION RULE (assignment default, on the WEEK dip spread only): PROMISING
  iff (a) sign(spread_WEEK,y) identical in >= 4 of 5 anchor years, AND
  (b) LOYO_h passes in >= 4 of 5 held-out years.
- At most one rule proposal: a skip/reduce rule is proposed ONLY if
  PROMISING (direction follows the pooled sign); otherwise no rule.

## Causality / alignment tests (tests/test_oc_expiry.py)

- test_expiry_calendar_hand_checked: explicit dates: Sep 2025 -> Fri
  2025-09-26 08:00 UTC; Feb 2024 (leap) -> Fri 2024-02-23 08:00 UTC;
  Jun 2026 -> Fri 2026-06-26 08:00 UTC; quarterly flags Mar/Jun/Sep/Dec
  only; every expiry is a Friday 08:00 UTC.
- test_windows_need_no_market_data: window flags from timestamps alone;
  shifting/dropping market inputs leaves flags unchanged; WEEK starts Monday
  00:00 and PRE24 is a subset of WEEK.
- test_cutoff_and_universe: every analysed T < 2026-09-24; universe =
  majors x R2 only; each year has > 300 fills and inside-WEEK share in
  5..25% (12 monthly weeks x ~4.3d / 365d ~= 14%).

## Deliverables

research/tournament/oc_expiry/: PLAN.md (this file), analyze_expiry.py,
results.json, REPORT.md (tables + one-line verdict). No tuning on results;
any post-hoc change logged in REPORT.md. No commits.
