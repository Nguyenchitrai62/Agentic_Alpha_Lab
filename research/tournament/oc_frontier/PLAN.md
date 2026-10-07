# oc_frontier PLAN (pre-registered BEFORE any outcome is computed)

## Hypothesis
The 5-year 4-phase reset-metric versions v399..v423 (research/parallel/rounds/
parallel-20260906-r2/vNNN/) can be summarised in one auditable table plus two
Pareto frontiers: (R up, max-yearly-DD down) and (R up, full-path-DD down),
with the deployment pick R2B1D17BF (v411) marked and stretch-DD<15 rows flagged.
This is a REPORTING task (no selection): no variant is chosen here.

## Exact causal / definitional rules (fixed here)
- Source rows: `research/parallel/rounds/parallel-20260906-r2/vNNN/vNNN_result.json`
  key `rows` (4-phase reset metric, 5 walk-forward years, anchors 2021-09-24 ..
  2025-09-24, each +365 d). All five years are research data; findings still need
  prospective validation. No 1m data is loaded; one process; RAM < 1 GB.
- Per (version, row): R = rows[row].R (5y geometric %/month, net, gate costs);
  W = rows[row].W (worst single-year %/month); DD_yearly = rows[row].DD, defined
  as max over years[i][1]; years = rows[row].years (list of 5 [R_i, DD_i]);
  most-recent-year R = years[4][0] (anchor 2025-09-24 year).
- full_path_dd: parsed from `vNNN/run.log` lines matching
  `^(\S+) full-path DD ([0-9.]+)`; the value for the same row must equal
  `rows[row].full_path_dd` in the result JSON when both exist (mismatch = FAIL
  and is reported). If absent in BOTH log and JSON, record null (expected for
  v399/v400, which predate full-path logging).
- audited: `vNNN/result_manifest.json` key `audit.passed` (boolean).
- Pareto (maximisation of R, minimisation of DD): point A dominates B iff
  R_A >= R_B AND DD_A <= DD_B with at least one strict inequality. The frontier
  is the set of non-dominated points. Computed twice: once on
  (R, DD_yearly) over rows with non-null DD_yearly, once on (R, full_path_dd)
  over rows with non-null full_path_dd. Ties on identical (R, DD) are both kept.
- Stretch flag: DD < 15 (checked separately on DD_yearly and on full_path_dd).
- Deployment pick to mark: row R2B1D17BF from v411.

## Decision rule (fixed here)
REPORTING only: no PROMISING / NOT-PROMISING selection is made. The default
4-of-5 anchor-year + 4-of-5 LOYO rule from the assignment header is NOT applied
(no effect is estimated). REPORT.md ends with a one-line descriptive verdict
(best-R rows, frontier members, DD<15 count, audit state). Any post-hoc change
after first computation is logged in REPORT.md caveats.

## Outputs (fixed here)
- `research/tournament/oc_frontier/build_frontier.py` (single script),
  `results.json` (rows table + both frontiers + meta), `frontier.png`
  (matplotlib scatter R vs max yearly DD, frontier highlighted, v411 pick marked),
  `REPORT.md` (tables + one-line verdict). Test: `tests/test_oc_frontier.py`.
