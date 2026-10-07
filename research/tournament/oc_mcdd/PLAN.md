# oc_mcdd — PLAN (pre-registered before computing outcomes)

Deployment-risk study, information only. No new trading rule, no selection.

## Question
What is the sampling distribution of the 12-month return and max drawdown of
the deployment pick R2B1D17BF (plus reference R2B1D16), given the 5 years of
walk-forward history 2021-09-24..2026-09-23?

## Inputs (read-only, no edits)
- `research/parallel/rounds/parallel-20260906-r2/v411/v411_runs.pkl`:
  4 phase shifts x strategies (`R2B1D17BF`, `R2B1D16`), each with 4h-spaced
  `t` (run equity time = bar close + 8h), `eq` (close equity), `eq_min`
  (trailing intrabar marked low). `R2B1D16` cross-checked byte-identical vs
  `research/parallel/rounds/parallel-20260906-r2/v406/v406_runs.pkl`.
- Anchor dates: 2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24, 2025-09-24
  (00:00 UTC); evaluation window ends 2026-09-23 00:00 UTC.
- Method reference: `research/diagnostics/r2_decompose5/reset_metric.py`
  (`year_reset`: each phase rebased to its anchor value, mean of 4 phases)
  and `v388_bot_stop_distance.py` (`hourly`, `mix`, `year_stats`).

## Exact causal definitions
1. Daily grid: `D = date_range(2021-09-24, 2026-09-23, freq=1D, tz=UTC)`
   (00:00 UTC marks). All series are right-continuous holdings: value at `D[d]`
   uses only run points with `t <= D[d]` (ffill; no look-ahead).
2. Per phase `s`, strategy `k`: close series `E_s` = `eq` reindexed to `D`
   with ffill (seed 1.0 before first point); marked-low series: build the
   4h `eq_min` series, ffill to an hourly grid, then `M_s[d] = min(hourly
   marked low over (D[d-1], D[d]])`, floored at ffill logic of `v388.hourly`
   (`min(lo, e)`), so `M_s <= E_s` at each day.
3. Year-reset chained mixed equity (the object of study): at each anchor
   `a_y`, phase `s` weight is reset to 1/4 of capital:
   `shares_{s,y} = (C_y / 4) / E_s(a_y)`, where `C_y` is total capital at the
   anchor (`C_0 = 1.0`, `C_{y+1} = C_y * mean_s(E_s(a_{y+1}) / E_s(a_y))`).
   Daily mixed close `E[d] = sum_s shares_{s,y(d)} * E_s[d]` within year `y`;
   daily mixed low `M[d] = sum_s shares_{s,y(d)} * M_s[d]`. This equals
   concatenating the five `reset_metric.year_reset` segments multiplicatively.
   The fifth segment ends 2026-09-23 (365th day is 2026-09-23; the runs end
   2026-09-23 04:00, so the last daily close uses `t <= 2026-09-23 00:00`).
4. Daily close simple returns `r[d] = E[d] / E[d-1] - 1` for `d >= 1`
   (length N ~ 1825); daily low factor `l[d] = M[d] / E[d-1]` (<= ~1+r).
   Per historic year `y`: net `R_y = E(a_{y+1}-side) / E(a_y) - 1`
   (= `E_seg[end] - 1` of the rebased segment starting at 1.0),
   monthly geo `m_y = (1 + R_y)^(1/12) - 1`, close maxDD and marked maxDD
   (`1 - min(M_seg / running peak of E_seg)`) reported empirically.
5. Stationary (Politis-Romano) block bootstrap on the daily pairs
   `(r[d], l[d])`: mean block 20 days (`p = 0.05`, `L ~ Geometric(p)`),
   10000 paths of 365 days, seed 0 (`numpy.default_rng(0)`), circular
   wrapping (indices modulo N). Path reconstruction: `P_0 = 1`,
   `P_k = P_{k-1} * (1 + r[i_k])`, `L_k = P_{k-1} * l[i_k]`;
   `R12 = P_365 - 1`, `m = (1 + R12)^(1/12) - 1`,
   close maxDD `D_c = max(1 - P_k / max_{<=k} P)`,
   marked maxDD `D_m = max(1 - min(P_k, L_k) / max_{<=k} P)`.
   Primary DD = marked (gate-relevant: max of close and marked); close DD
   reported alongside.
6. Summaries per strategy: `P(R12 < 0)`, `P(m < 5%)`, median / 5th / 95th
   percentile of `m`, `P(D_m > 15% / 20% / 25%)`, median `D_m`
   (plus median close DD and `P(D_c > ...)` as secondary rows).

## Decision rule
None. This is information for the deployment doc, not a candidate screen:
no PROMISING/REJECT verdict, no variant comparison, no threshold tuning.
The default tournament ">= 4 of 5 years" rule does not apply.

## Leakage / validity notes
- Descriptive use of all five years (2021-09-24..2026-09-23) is permitted by
  the assignment (former hidden year is now research data); nothing is fitted
  or selected on it — no model, no parameters, no thresholds.
- Bootstrap assumes approximately stationary daily returns; reported
  alongside the raw per-year empirical table so non-stationarity is visible.
- Block mean 20 days preserves short autocorrelation; it does not preserve
  annual regime structure — the per-year table covers that gap.

## Resources
LIGHT: one process, RAM < 1 GB, no 1m data, only the two runs pkls.
Script: `mcdd_bootstrap.py` -> `results.json` + `REPORT.md`. Seed fixed.
