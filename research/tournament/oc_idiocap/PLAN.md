# oc_idiocap PLAN (pre-registered BEFORE any outcome is computed, 2026-10-05)

## Hypothesis
oc_ddanat17 found the 20 worst dip rungs of the deployment pick are all n = 0
(full size: no other major breached 2.5-sigma at the fill) single-coin news
crashes (SOL FTX 2022-11, BNB 2023-06, XRP 2024). Hypothesis: rungs where the
coin is flushing fast ALONE (own 30-min momentum deeply negative while BTC is
calm) are idiosyncratic crashes with bad stop/timeout payoffs; halving (or
x0.7) ONLY those n = 0 rungs cuts worst-day and drawdown at small cost to the
yearly sums.

## Universe and years (fixed)
- Rows: `research/tournament/ext/fills_U_ext.parquet` majors
  (BTC/ETH/SOL/BNB/XRP) R2 rungs (`x1` in {2.5,3.0,3.5,4.0,5.0}) inner-joined to
  `research/tournament/oc_b1shape/fills_n.parquet` on (sym, t_fill, x1 = k)
  (1-1 match, 6876 rows total; verified key uniqueness BEFORE outcomes).
- `T = t_fill - f minutes` (the 4h bar open; on the standard grid).
- Years: 5 walk-forward years Y0..Y4 = [anchor, anchor + 365d) for anchors
  2021-09-24 .. 2025-09-24, keyed by `T`. Rows with `T` outside are ignored.
- Outcome per row: `y1.0` (net return at TP 1.0 sigma, fees/funding included).
- Market data up to 2026-09-24 00:00 UTC. All five years are research data
  (assignment override of RULES.md hidden-year rule); findings need prospective
  validation. No refit, no selection, no tuning.
- LIGHT: one process, RAM < 1 GB, NO 1m data (only the two parquet inputs).

## Exact causal definitions (frozen)
- Fill-time state (known at minute f - 1, strictly before the fill at minute f;
  see v293 docstring): `x0` = own sp30 (30-min log return / (sigma_1m sqrt 30)),
  `x4` = BTC sp30 at the same minute, `x5` = dd24. `n` = `n25` from fills_n
  (detections among the 4 OTHER majors at minute f - 1 vs 4h opens/sigma at `T`).
- Baseline B0 `plain`: raw weight `w = 1/(1+n)`.
- Caps apply ONLY when `n == 0` (else cap factor = 1):
  - C1 `idio05`: cap factor 0.5 when `x4 > -1 AND x0 < -4`
    (coin crashing alone, fast; BTC calm), else 1.
  - C2 (1m-depth version: coin >= 3 sigma_4h further below its open than BTC is
    below its own open at f - 1): SKIPPED — needs 1m closes; assignment says
    "else skip C2", and this is a LIGHT no-1m job.
  - C3 `idio07`: SAME trigger as C1, cap factor 0.7 (softer cap), else 1.
- NaN guard (conservative): NaN `x0`/`x4` -> trigger FALSE (no cap). In the
  majors-R2 join both are finite, so the guard is a no-op.
- Capped raw weight: `w_cap = 1/(1+n) * cap`.

## Scoring (fixed, equal exposure per year)
- Per year: rescale raw weights to mean 1 (`w' = w / mean(w over that year)`),
  yearly sum `S = sum(w' * y1.0)`; daily sums group `w'*y1.0` by `T.floor('D')`.
- Per year: worst-day = min daily sum; maxDD_year = min(cumsum - running_max)
  of that year's daily sums in chronological order.
- Reference: overall worst-day (min over years) and full-path maxDD of the
  cumulative daily sum (all 5 years concatenated chronologically).
- Report per variant: yearly `S`, per-year worst-day, per-year maxDD, overall
  worst-day, full-path maxDD, trigger counts/share (n = 0 rows capped per year).
- No fitting, no thresholds learned (thresholds are the assignment's example
  values, frozen here), no rescaling across years.

## Decision rule (fixed)
- PRIMARY (assignment): PROMISING iff ALL THREE hold vs B0:
  (i) worst-day improves (strictly shallower, `wd_cap > wd_B0`) in >= 4/5 years,
  (ii) per-year maxDD improves (strictly shallower) in >= 4/5 years, AND
  (iii) yearly `S` keeps >= 95% (`S_cap >= 0.95 * S_B0`; if `S_B0 <= 0` require
  `S_cap >= S_B0`) in >= 4/5 years.
- SECONDARY (default tournament rule, reported as a side row): effect has the
  same sign in >= 4/5 anchor years AND holds leave-one-year-out in >= 4/5.
- One-line verdict in REPORT.md. A negative result is a valid result.

## Outputs
- Scripts: `score_idiocap.py` (single process, pandas only).
- `results.json` (per-variant yearly S / worst-day / maxDD, overall tails,
  trigger shares, decision flags).
- `REPORT.md` (tables + one-line verdict). Test: `tests/test_oc_idiocap.py`.
