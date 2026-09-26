# v176 blind audit — Part B comparison

Blind: `research/parallel/rounds/parallel-20260906-r2/v176_audit/replication.json`
was saved before opening `v176/` (see Part A script header assumptions B1–B7).
Base: v175 audit sleeve replication + engine_real FULL + v170 W=60 execution.

## Primary row (total-portfolio vol target, target 0.25, cap 2, governor on)

| row | monthly % | full-path DD % | mean s | 2021 net/DD | 2022 net/DD | 2023 net/DD | 2024 net/DD | 2025 net/DD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v176 reported | 5.239 | 20.72 | 1.492 | 28.58 / 20.72 | 44.17 / 15.90 | 147.27 / 14.05 | 109.17 / 11.85 | 123.27 / 10.90 |
| audit replication | 5.109 | 20.72 | 1.493 | 28.58 / 20.72 | 44.17 / 15.90 | 147.27 / 14.05 | 104.28 / 14.35 | 112.32 / 11.28 |
| diff (audit − reported) | −0.130pp | 0.00pp | +0.001 | 0.00 | 0.00 | 0.00 | −4.89pp / +2.50pp | −10.95pp / +0.38pp |

Fills (books weight changes, live bars) match exactly:
2036 / 2178 / 2189 / 2190 / 2184 in both rows.
2021–2023 yearly nets match to 0.01pp; full-path DD matches to 0.01pp.
The vol-target loop (realized_total → vol → s → w=0.8·s·B·g, c=0.6·s·g,
net+=s·g·sleeve_unit, governor/budget/min-notional/funding/carry/W60 exec)
is reproduced.

## Why 2024/2025 differ: walk-forward k only

| anchor | audit best_k (score) | v176 chosen k (train Sharpe) |
| --- | --- | --- |
| 2021-09-24 | 2.5 (0.05956) | 2.5 (0.0601) |
| 2022-09-24 | 4 (0.05227) | 4.0 (0.0517) |
| 2023-09-24 | 4 (0.04450) | 4.0 (0.0440) |
| 2024-09-24 | 3 (0.045049) vs 3.5 (0.044800) vs 4 (0.044684) | 3.5 (0.0456) |
| 2025-09-24 | 4 (0.044470) vs 3.5 (0.044321) vs 3 (0.043768) | 3.5 (0.0451) |

The 2024/2025 gaps are ~2–5e-4 in Sharpe (audit 0.045049 vs 0.044800;
reported 0.0456 for k=3.5). Same pattern already existed between the
v175 audit replication (3, 4) and `v175_result.json` (3.5, 3.5); v176
inherits `v175.limit_returns` + `v171.sleeve_walk_forward`, the audit
inherits the v175-audit grid. Known implementation deltas that move such
close calls: selection window half-open `[start, anchor−1d)` (audit) vs
closed `<= anchor−1d` (v171 code, one extra 4h bar); float32 cube
(`v172.cube_ohlc`, keep-first dedup) vs float64 ffilled grids (keep-last);
pct_change vs open/open−1 sigma paths. With v176 k's forced, the loop
matches (2021–2023 proof above); no other return/DD gap remains.

## Look-ahead check

`v176_total_vol_target.py:54`:
`realized = 0.8*(books.shift(2)*(o/o.shift(1)-1)).sum + 0.6*carry.shift(1) + su.shift(1)`;
`:82` `net[i] += s[i]*g[i]*sl[i]` on live bars.
- `sl[i]` as a payoff is causal: weight `s[i]*g[i]` is decided at bar-close
  `i`, return realized over bars `i+1/i+2` (same timing as books `r_next[i]`).
- `su.shift(1)` (`sleeve_unit[i-1]`) in `s[i]` is **not strictly known** at
  decision `i`: sleeve `i-1` exits at open of bar `i` with
  `s_out=max(0.0002,0.25*(H−L)/O)` of 1m minute 0 of bar `i`. At the
  decision instant (open of bar `i`, before minute 0 completes) that range
  is unobserved — a ~1-minute look-ahead into the vol estimate. Funding at
  the bar-open settlement is known at the open; the `s_out` minute-0 range
  is the only forward piece (a few bps on a sleeve that is already divided
  by 1.657, hence <1bp on `s`). Fix: use `su.shift(2)` or minute-0-unknown
  `s_out=0.0002` fallback for the vol leg; the payoff leg `sl[i]` is fine.
- Sleeve `L=open(T)*(1−kσ)`: `open(T)` is the next-bar open, known at the
  decision instant up to the usual close→open continuity (same convention
  as engine_real execution base `p0`); no additional look-ahead beyond that.
- Governor/budget/min-notional/funding/carry/W60 all use `i−2`/past-only
  state as engine_real. No other forward use found.

## Diagnostics (audit-only, not in v176_result.json)

- Cost stress (B5: books maker 0.0004/taker 0.0007 +5bps taker slippage;
  sleeve entry 0.0004/exit 0.0007+5bps; vol/s recomputed):
  monthly 4.507%, full-path DD 22.27%, mean_s 1.494.
  Yearly nets: 20.23 / 34.52 / 134.33 / 85.99 / 99.80.
  The sleeve survives stressed costs but DD widens by ~1.5pp.
- 1m mark (B6: books w + open sleeve from fill minute at close/L−1 every
  minute vs 4h open(T); minute eq=prev*(1+R−exec+min(funding,0))):
  full-path DD 26.12% vs close-sampled 20.72%, worst minute cluster at
  2022-11-08 12:00 UTC (FTX crash window). Close-sampled DD understates the
  intrabar path by ~5.4pp on this row.

## Verdict

- Loop/engineering: **reproduced**. Execution, funding, carry, budget,
  min-notional, governor, S_REF=1.657, vol/s formula, and sleeve payoff all
  match (fills exact, 2021–2023 nets exact, DD exact, mean_s within 0.001).
- k-selection: **differs on close calls** (2024: 3 vs 3.5; 2025: 4 vs 3.5)
  for the documented window/dtype/dedup reasons; this fully explains the
  −0.13pp monthly and 2024/2025 yearly gaps. Not a new economic finding.
- Look-ahead: one minor ~1-minute forward use (`s_out` minute-0 in
  `sleeve_unit[i-1]` for `s[i]`); payoff timing is causal. Recommend the
  `shift(2)`/fallback fix before any live use.
- Gate: both rows fail the DD<=20% gate on 2021 (20.72); monthly passes.
  Manifest `rejected` stands. Do not promote without the vol look-ahead fix
  plus mark-price/queue/slippage robustness.
