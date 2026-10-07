# oc_crashfreq PLAN (pre-registered BEFORE any outcome is computed, 2026-10-05)

## Hypothesis / scope
REPORTING only (no PROMISING rule, no selection, no tuning). Using the four
R2B1D17BF engine replicas in research/tournament/oc_ddanat4p
(events_s0..s3.parquet, rungs_s0..s3.parquet, raw_s0..s3.pkl, live
2021-09-24..2026-09-23), list every 4h bar in which a phase's dip sleeve lost
>= 3% of that phase's equity from realised rung exits, and summarise the
frequency/concentration of one-bar dip crashes for risk planning. The
2024-01-03 flash crash (s1/s2/s3 -17/-22/-21% in one bar, oc_ddanat4p) is the
reference tail event.

## Inputs (fixed)
- ONLY research/tournament/oc_ddanat4p/{rungs_s0..s3.parquet} for dip losses
  (events/raw pkls used only for cross-check counts, not for numbers), plus
  research/tournament/ext/hourly_ext.parquet BTCUSDT hourly closes for BTC 4h
  returns. Market data read only to 2026-09-24 00:00 UTC. All five years are
  research data (assignment override of RULES.md hidden-year rule); findings
  need prospective validation. No refit, no thresholds fit, no selection.
- Resources: ONE process, RAM < 3 GB (rungs ~5k rows/phase + hourly BTC only;
  no 1m data).

## Exact causal definitions (fixed before running)
- Phase 4h bar grid: phase s bar_ends T at UTC hours with hour % 4 == s % 4
  (s0: 00/04/08/12/16/20; s1: 01/05/09/13/17/21; s2: 02/06/10/14/18/22;
  s3: 03/07/11/15/19/23), live T in (2021-09-24 00:00, 2026-09-24 00:00].
  Bar interval = (T-4h, T].
- Per-bar dip loss: dip_loss(s,T) = 100 * SUM(loss) over rungs_s rows with
  exit_t in (T-4h, T], where loss = weight*ret as stored (fraction of
  fill-bar-start equity; engine worst20_note convention). Breakdowns by exit
  kind: sl/tp/timeout sums (pp) + counts; n_stops = count(rung_sl);
  per-coin sums (pp). A ">= 3% loss" bar means dip_loss <= -3.0.
- Exit bucketing edge: T = smallest grid time with T >= exit_t (exits exactly
  on a grid hour belong to that bar; exits carry minute granularity so this is
  measure-zero).
- BTC 4h return per bar: btc_ret(T) = C(T-1h)/C(T-5h) - 1 from BTCUSDT
  hourly_ext closes, where C(H) = close of hourly row starting at H (the last
  hourly close at or before T-0s / T-4h). Causal (uses only data <= T).
  Missing hours -> ffill/backfill within hourly series; else null. Reported
  in %.
- Coincidence ("other phases also >= 3% in the same 4h window"): wall-clock
  window W = (T-4h, T]. For each other phase p, wall_loss(p,W) = 100 *
  SUM(loss) over rungs_p exits in W. Flag p if wall_loss <= -3.0. Report
  flagged phases + their wall losses. (Phase grids are offset by 1h so own
  bars never align; wall-clock is the risk-relevant coincidence.)
- Years: anchor years Y0..Y4 = [2021-09-24,2022-09-24), [2022-09-24,
  2023-09-24), [2023-09-24,2024-09-24), [2024-09-24,2025-09-24),
  [2025-09-24,2026-09-24). Event assigned by bar_end T. Counts per year =
  number of (s,T) bars with dip_loss <= -thr for thr in (3,5,10,15),
  pooled over phases, plus per-phase totals and total bars scanned.
- Largest 15: all (s,T) with dip_loss <= -3 sorted ascending, take 15.
- Concentration: sum_neg = SUM(dip_loss) over all (s,T) with dip_loss < 0
  (negative pp); top10_sum = SUM of 10 most negative bars; fraction =
  top10_sum / sum_neg (reported as %). Also report negative-bar count.
- 2024-01-03-type: fixed threshold dip_loss <= -15% (just below the smallest
  of the three gate crash bars -17/-22/-21%; no change after seeing data).
  Frequency = count of such (s,T) bars in 5y, count of distinct wall dates
  with >= 1 such bar, calendar rate, and Poisson waiting-time estimate.
  One paragraph for risk planning; no tuning.

## Decision / verdict rule
None (diagnostic). REPORT.md gives: full >= 3% event list; per-year
>= 3/5/10/15 counts; largest 15; top-10 concentration fraction; one
frequency paragraph for a 2024-01-03-type event. One-line VERDICT names the
frequency/concentration mechanism. No PROMISING claim.

## Outputs
- scripts: compute_crashfreq.py (light, parquet-only, one process).
- results.json (event list, yearly counts, top15, concentration, checks).
- REPORT.md (tables + one-line verdict).
- Test: tests/test_oc_crashfreq.py (files exist, PLAN predates results,
  schema/counts/top15/concentration consistency, crash bars reproduced).
