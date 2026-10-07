# oc_kellydip PLAN (pre-registered 2026-10-05, BEFORE computing any Kelly/DD optimum)

## Goal (descriptive; no rule)

Analytical sizing of the dip sleeve: from the majors R2 rung outcomes (`y1.0`)
per walk-forward year, compute (a) the growth-optimal (Kelly) fraction of a
fixed-fraction-per-rung bet and (b) the fraction at which the daily-sum max DD
reaches 15 % / 20 %, with and without the correlation shrink `1/(1+n)`.
Report where the deployed dip size (x1.7 of the R2 base) sits vs these optima
per year. No trading rule is selected; no PROMISING verdict is registered.

## Universe and years (fixed)

- Rows: `research/tournament/ext/fills_U_ext.parquet`, majors only
  (`BTCUSDT/ETHUSDT/SOLUSDT/BNBUSDT/XRPUSDT`), R2 rungs only
  (`x1` in {2.5, 3.0, 3.5, 4.0, 5.0}).
- `T = t_fill - f minutes` (the 4h bar open; standard grid). Year `Yi`
  (anchors 2021-09-24 .. 2025-09-24) = rows with
  `T in [anchor, anchor + 365 d)`, keyed by `T`. Rows with
  `t_fill >= 2026-09-24 00:00 UTC` are dropped (market data up to 2026-09-24
  00:00 UTC per the assignment; all five years are research data and any
  finding needs prospective validation — disclosed against RULES.md 2 /
  VF_COMMON hidden-year conventions).
- Outcome per row: `y1.0` (exact net return at TP 1.0 sigma, fees/funding
  included in the replica). Unit = R2 base per-rung notional (flat weight 1);
  the deployed size is `f_dep = 1.7` in these units (x1.7 of the R2 base;
  with shrink: `1.7/(1+n)` per rung, cf. v411 `kd=1.7` on top of `1/(1+n)`).
  `y_dep`/`size_dep`/TP variants are NOT used here.

## Correlation shrink n (frozen, timestamp-only, no 1m data)

For each universe row `i` (majors R2 fill), let `S(i)` = distinct OTHER symbols
(`sym_j != sym_i`) having >= 1 majors-R2 fill `j` with the same bar open
`T_j == T_i` and `|t_fill_j - t_fill_i| <= 15 minutes` (both from `fills_U_ext`
timestamps). `n_i = |S(i)|`, integer 0..4 (coins, not fills). Two weightings per year:

- A `flat`: `w_i = 1`, effective return `z_i = y1.0_i`.
- B `shrunk`: `w_i = 1/(1+n_i)`, effective return `z_i = w_i * y1.0_i`.

Rung order for Kelly compounding: chronological by `t_fill`
(ties by `sym`, then `x1`). Daily sums group `z_i` by `T.floor('D')` (UTC).

## Kelly optimum (frozen)

Per year and per weighting, over that year's `z_1..z_N` in fill order:

- Growth rate `G(f) = (1/N) * sum_i log(1 + f*z_i)`, defined only where
  `1 + f*z_i > 0` for every `i` (else `G = -inf`, infeasible).
- `f*` = argmax of `G` on `f >= 0`, solved by bisection (200 iterations) on
  `G'(f) = mean(z/(1+f*z))`: if `G'(0) <= 0` then `f* = 0`; else bisect
  `[0, Fmax]` where `Fmax = 0.999 / max(-min(z), tiny)` capped at 20
  (if `G'(Fmax) >= 0` the optimum is reported as `>=Fmax`, capped flag).
- Report per year/weighting: `N`, `f*`, `G(f*)`, `G(1.0)`, `G(1.7)`,
  feasibility of `f=1.7` (`min_i(1+1.7*z_i)`), full-Kelly DD note below.

## Daily-sum DD fractions (frozen)

Per year and per weighting, at unit fraction (`f=1`):

- Daily sums `D_d = sum_{i: T.floor('D')=d} z_i`, days sorted chronologically;
  cumulative `C_k = sum_{d<=k} D_d` from 0;
  `maxDD1 = min_k(C_k - max_{l<=k} C_l)` (<= 0, same convention as oc_b1shape).
- Linearity: `maxDD(f) = f * maxDD1`, so the fractions hitting 15 % / 20 %
  are `f_DD15 = 0.15 / (-maxDD1)`, `f_DD20 = 0.20 / (-maxDD1)`
  (`null` if `maxDD1 == 0`). DD at deployed: `DD_dep = 1.7 * maxDD1`.
- Report per year/weighting: `maxDD1`, `f_DD15`, `f_DD20`, `DD_dep`,
  ratios `1.7/f*`, `1.7/f_DD15`, `1.7/f_DD20`.

## Outputs (fixed)

- Script `compute_kelly.py` (stdlib + pandas + numpy, one process, no 1m
  data, fills file only, < 1 GB RAM): builds `n`, runs the Kelly/DD math
  per year x weighting, writes `results.json` (schema: `universe` counts,
  `n_hist` shares/counts per year, `years` rows with the A/B
  `f*/G/maxDD/f_DD/DD_dep/ratios`, `deployed` note `f_dep=1.7`).
- `REPORT.md`: n-histogram table, per-year Kelly table (A/B), per-year
  DD table (A/B), one-line verdict describing where x1.7 sits.
- `tests/test_oc_kellydip.py`: synthetic unit checks (Kelly solver on
  known bets, DD linearity, n-window counting on toy timestamps) plus
  artifact consistency (results.json reproduces its own ratios/tables).

## Decision rule (fixed)

Descriptive; no rule: there is NO PROMISING/NOT-PROMISING selection and no
leave-one-year-out gate (assignment task body overrides the default
PROMISING rule). The one-line verdict in REPORT.md only states, per year,
whether x1.7 sits below/near/above the Kelly optimum and the 15 %/20 % DD
fractions, with and without shrink.

## Protocol / resources (fixed)

- PLAN.md written before any Kelly/DD optimum is computed. (Pre-PLAN peeks
  were limited to file columns, row counts and per-year size means to fix the
  definitions above; no `f*`/`f_DD` value was computed before this PLAN.)
- Write ONLY `research/tournament/oc_kellydip/` (+ `tests/test_oc_kellydip.py`);
  no commits; no edits of leader files, other folders, configs, or `../Kronos`.
