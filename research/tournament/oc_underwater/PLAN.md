# oc_underwater PLAN (pre-registered BEFORE any outcome is computed)

REPORTING task (no selection rule). Market data up to 2026-09-24 00:00 UTC may
be read (assignment override; all five years are research data; any finding
needs prospective validation). LIGHT job: one process, RAM < 1 GB, no 1m data
(hourly runs only).

## Question (fixed here, descriptive)

For R2B1D17BFG2 (`research/parallel/rounds/parallel-20260906-r2/v421/
v421_runs.pkl`) and R2B1D13BF (`.../v424/v424_runs.pkl`), on the CONTINUOUS
4-phase mix (1/4 each, no reset; `research/diagnostics/r2_decompose5` /
`v388.mix` conventions, hourly): list every drawdown episode deeper than 5 %
with start (peak), trough, recovery date, depth, days to trough, days under
water; distribution of time under water (median / p90 / max) and the share of
days spent > 5 % / > 10 % below the running peak. Plain Vietnamese summary for
the deployment doc (what a user will live through).

## Inputs (frozen)

- Rows: `R2B1D17BFG2` from `v421_runs.pkl`, `R2B1D13BF` from `v424_runs.pkl`
  (shifts s = 0..3, keys {t, eq, eq_min} only). No fills, no hourly_ext, no 1m.
- Code imported (not copied): `v388_bot_stop_distance.hourly` / `.mix`
  (`research/parallel/rounds/parallel-20260906-r2/v388/
  v388_bot_stop_distance.py`), grid g0 = 2021-09-24 04:00 UTC,
  g1 = Y1 + 12h = 2026-09-23 12:00 UTC, 1h frequency.
- Continuous mix: e, mn = v388.mix(runs, row, g1); analysis window =
  grid points with t > 2021-09-24 00:00 UTC (the 4h before the first anchor
  are warm-up, excluded from every count).

## Exact causal / accounting definitions (frozen)

- Running peak P(t) = max_{s <= t} e(s) (eq path ONLY, never eq_min).
- Conservative drawdown dd(t) = 1 - mn(t) / P(t) (same numerator/denominator
  convention as `reset_metric.year_reset` and `v388.year_stats`: peak from
  eq, trough from eq_min; mn <= e on the grid by construction of hourly()).
- An UNDERWATER excursion = maximal interval [t_peak, t_rec] where t_peak is
  an index with e(t_peak) = P(t_peak) (a new running peak; if the same peak
  level repeats, the LAST occurrence before the fall is the peak), e(t) <
  P(t_peak) for every t in (t_peak, t_rec), and t_rec is the FIRST index after
  t_peak with e(t_rec) >= P(t_peak) (close-price recovery on eq, not eq_min).
  If no such t_rec exists before the grid end, the excursion is UNCENSORED at
  the right: recovery = null, days_underwater measured to the grid end and
  flagged censored=true.
- A listed EPISODE = an underwater excursion whose max dd over the interval
  exceeds 0.05 (> 5 %). Nested 5 % crossings do NOT split an episode: one
  peak-to-recovery excursion = one episode even if dd dips back below 5 %
  mid-way (still under water). Depth = max dd in [t_peak, t_rec-or-end] x 100.
- Trough t_trough = FIRST index in the episode attaining max dd (ties -> first).
- days_to_trough = (t_trough - t_peak) total_seconds / 86400 (fractional days,
  rounded to 2 dp in REPORT; exact hours also stored).
- days_underwater = (t_recovery - t_peak) / 86400, or (grid_end - t_peak) /
  86400 when censored (flagged).
- Time-under-water distribution = over the listed > 5 % episodes only:
  median / p90 (linear interpolation, numpy default) / max of days_underwater.
- Share of time below peak = fraction of hourly grid points in the window
  with dd > 0.05 (resp. > 0.10) x 100; reported as "% of time" plus the
  equivalent calendar days (fraction x window_days) for intuition. Day counts
  use hours/24 (window has 24 grid points/day; no separate daily sampling, so
  there is exactly one number, no ambiguity).
- Cross-checks (must hold, else invalid): mn <= e everywhere (max viol <= 0);
  w = none (no combination); full-path conservative DD from the same e/mn
  must equal the official `full_path_dd` of each row (G2 16.82, D13BF 14.86)
  to 0.01 pp; episode max depth must equal that full-path DD.

## Decision rule (fixed here)

REPORTING ONLY: no PROMISING / NOT-PROMISING selection is made (post-hoc
informed rows picked after seeing five years; labelled). The header default
(4-of-5 same-sign + 4-of-5 LOYO) does NOT apply — there is no effect, no
variant comparison. The operative output is the episode table + the
Vietnamese "what you will live through" paragraph.

## Deliverables (fixed here)

`research/tournament/oc_underwater/`: PLAN.md (this file),
compute_underwater.py, results.json, REPORT.md (tables + one-line verdict +
Vietnamese summary). Test: `tests/test_oc_underwater.py` (episode logic on
synthetic series incl. hand cases + censored + nesting; mix-convention checks:
mn <= e, full-path DD reproduces official numbers, episode max = full-path DD,
recompute of durations/shares from stored series, no 1m data in the script).
One process, no 1m data, RAM < 1 GB. Post-hoc changes, if any, logged in
REPORT.md.

## Amendment log (append-only; original above frozen)

(none yet)
