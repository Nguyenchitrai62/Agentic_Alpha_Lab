# v170 audit — Part B comparison

Part A `replication.json` was saved before `v170/` was opened.
Base: `engine_real_audit/audit_engine.py` (books/carry/funding/vol/loop);
only the execution arrays were replaced per assignment.

## Reproduction vs `v170/v170_result.json`

| Window | Audit monthly% | v170 monthly% | d return | Audit DD | v170 DD | d DD |
|---|---|---|---|---|---|---|
| W15 (baseline) | 3.708 | 3.708 | 0.00pp | 18.87 | 18.87 | 0.00pp |
| W60 (primary) | 3.802 | 3.802 | 0.00pp | 18.93 | 18.93 | 0.00pp |
| W120 (sensitivity) | 3.822 | 3.822 | 0.00pp | 18.90 | 18.90 | 0.00pp |

Yearly `net_pct` match exactly all 5 anchors for every W
(W15: 19.17/45.40/96.18/60.37/63.04; W60: 19.83/48.00/98.54/61.78/64.71;
W120: 19.55/48.70/99.24/62.21/65.18).
Component sums match to the reported 2dp
(W60: gross 256.29, exec 18.32, funding -8.13, carry 12.53, carry_cost 2.46).
No return diff exceeds 1pp, no DD diff exceeds 0.5pp — nothing to explain.

Maker-share note (definition, not a number mismatch):
v170 reports `mb[live].mean()` over all live bar-cells (including no-trade
cells): 0.636/0.644 (W15), 0.814/0.813 (W60), 0.871/0.870 (W120).
The audit reports maker share over live weight-change orders: 0.6328/0.6441
(W15), 0.8111/0.8114 (W60), 0.8682/0.8688 (W120).
Recomputing the all-cell mean from the audit's `fb/fs` masks gives
0.636/0.644, 0.814/0.813, 0.871/0.870 — identical to v170. Economic path is
unaffected; the ~0.003 gap is denominator only.

## Diagnostics (from audit)

- Gain is not concentrated in one year: max anchor-year share of live net
  sum is 0.302 (W15), 0.301 (W60), 0.301 (W120); all yearly `net_pct` > 0.
- Taker branch at W60 charges drift: max |rel_b-0.0002-drift| = 1.7e-18,
  max |rel_s+0.0002-drift| = 1.7e-18 over live taker orders (4058 buys,
  4179 sells); mean taker drift +0.51% buys / -0.51% sells, 99.7% of taker
  buys have nonzero drift — no free waiting.

## Look-ahead review of `v170/v170_exec_window.py`

- `bar_stats_w`: T = floor-4h of 1m `open_time`, offsets relative to T;
  p0 = open@0, lo/hi over 2..W-1, pW = open@W, all strictly inside holding
  bar T. `exec_costs_w` reindexes by `idx + 4h`, so decision at `t` uses
  only minutes in T = t+4h (after the decision). Offsets 0/1 excluded as
  latency, not look-ahead.
- Maker test `lo < p0*0.999` / `hi > p0*1.001` and taker fallback
  `pW/p0-1 ± 0.0002` use only T-internal minutes; `NaN pW -> p0` and
  `no p0 -> taker ±0.0002` are conservative missing-data rules.
- Books, carry, funding, vol scale, governor, budget, min-notional all come
  from `engine_real` unchanged (`er.context` + `er.run(..., er.FULL)`).
- `maker_share` is a post-hoc diagnostic mean, not an input to weights.
- No signal, weight, or return uses data before the decision bar close
  beyond what engine_real already does.

## Verdict

PASS — independent replication matches `v170_result.json` exactly on
return, drawdown, yearly splits, and components; execution logic is causal
(fill decision uses only minutes after the decision); taker drift is
charged; maker-share gap is a documented denominator difference.
