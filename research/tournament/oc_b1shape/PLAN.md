# oc_b1shape PLAN (pre-registered 2026-10-05, BEFORE any outcome statistic)

## Hypothesis

The BOT (registry v399) shrinks each dip rung at its fill minute `f` by
`1/(1+n)`, where `n` = number of OTHER majors jointly deep at minute `f-1`.
Hypothesis: fills that fire while the rest of the majors board is also
limit-down mark correlated sell-offs (momentum continuation / weak bounces),
so shrinking them cuts left-tail exposure (worst day, drawdown) at little cost
to the yearly sums; a stronger shrink or a wider (2.0-sigma) detector may cut
tails further.

## Universe and years (fixed)

- Rows: `research/tournament/ext/fills_U_ext.parquet`, majors
  (BTC/ETH/SOL/BNB/XRP) R2 rungs only (`x1` in {2.5,3.0,3.5,4.0,5.0}).
  `T = t_fill - f minutes` (the 4h bar open; on the standard grid).
- Years: 5 walk-forward years `Y0..Y4 = [anchor, anchor+365d)` for anchors
  2021-09-24 .. 2025-09-24, keyed by `T`. Rows with `T` outside are ignored.
- Outcome per row: `y1.0` (net return at TP 1.0 sigma, fees/funding included).
- 1m klines: `data/raw/btc_intraday_20260924` (BTC),
  `data/raw/majors_intraday_20260924` (others); minutes `< 2026-09-24 00:00 UTC`
  only. One coin in memory at a time (float32), one process, RAM < 1.5 GB.

## Exact definitions (frozen)

- 4h grid: bar opens 00/04/08/12/16/20 UTC. `O_c(T)` = 1m `open` of coin `c`
  at minute `T`. Simple open-to-open returns `r_b = O_b/O_{b-1} - 1`.
- `sigma_4h(c,T)` = sample std (ddof=1) of the trailing 360 returns ending at
  bar `T` (i.e. `{r_{T-359}..r_T}`, min 120 non-NaN; else NaN = no detection).
  `O` and all returns use bars with open `<= T`, so sigma is known at `T`.
- `close_c(f-1)` = 1m `close` of coin `c` at minute `T + (f-1)` (the last fully
  closed minute before the fill minute `f`; `t_fill = T + f`).
- Detection (2.5-sigma): `close_c(f-1) <= O_c(T) * (1 - 2.5*sigma_c(T))`.
  Missing minute / NaN sigma or open -> NOT detected (conservative).
- `n` = detections among the 4 OTHER majors (`c != sym`), integer 0..4.

## Shapes (pre-registered, at most 3 extras + S0/S1 = 5 total)

- S0 `flat`: raw weight 1.
- S1 `inv1pn`: raw weight `1/(1+n)` (the deployed v399 rule).
- S2 `inv1pn2`: raw weight `1/(1+n)^2` (stronger shrink).
- S3 `btc2x`: raw weight `1/(1+n_w)`, `n_w` = detections with BTC weight 2
  (i.e. `n_w = n + btc_detected` for non-BTC fills; `n_w = n` for BTC fills).
- S4 `thresh20`: raw weight `1/(1+n2)`, `n2` = detections with a 2.0-sigma
  level (`close <= O*(1-2.0*sigma)`, same sigma).

## Scoring (harness5-style, equal exposure, fixed)

- Per year: rescale raw weights to mean 1 (`w' = w / mean(w over that year)`),
  yearly sum `S = sum(w' * y1.0)`; daily sums group `w'*y1.0` by `T.floor('D')`.
- Report per shape: yearly `S`, per-year worst-day, overall worst-day
  (min over years), full-path maxDD of the cumulative daily sum (all 5 years
  concatenated chronologically; `maxDD = min(cumsum - running_max)`), and the
  `n` histogram (share of fills with n = 0..4 per year + overall).
- No fitting, no thresholds learned, no rescaling across years.

## Decision rule (fixed)

The winner is the shape with the best (highest) overall worst-day AND the best
(shallowest) full-path maxDD among shapes whose yearly `S >= S1`'s yearly `S`
in >= 4 of the 5 years (S1 itself qualifies trivially; if no shape beats S1's
tails under the constraint, the verdict is "keep S1"). One-line verdict in
REPORT.md.
