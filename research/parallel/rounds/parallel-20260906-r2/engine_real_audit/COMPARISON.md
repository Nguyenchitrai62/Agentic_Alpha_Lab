# engine_real blind audit — comparison (part B)

Blind re-implementation (`audit_engine.py`, allowed imports only) matches
`engine_real/engine_real_v154_result.json` to rounding. Part A
`replication.json` was saved before opening `engine_real/`.

## Numbers

| row | monthly %/mo | full-path DD | intrabar bound |
|---|---|---|---|
| v154 reference | 3.515 | 19.15 | — |
| audit realism_off | 3.515 | 19.15 | 22.11 |
| leader v144_engine | 3.515 | 19.15 | 22.11 |
| audit real | 3.708 | 18.87 | 21.37 |
| leader engine_real | 3.708 | 18.87 | 21.37 |

Yearly nets match exactly, both modes:
off 18.38/40.66/97.79/54.30/56.34; real 19.17/45.40/96.18/60.37/63.04.
Components (% of start equity, sums over live span):
off gross 255.09 exec 23.38 funding -18.09 carry 12.81 cost 3.17;
real gross 255.93 exec 23.32 funding -8.13 carry 12.53 cost 2.47.
Audit diffs vs leader are <=0.01 (rounding) on every field.

## Thresholds

Spec: return diff >1pp or DD diff >0.5pp must be explained.
Real-vs-off: +0.193pp/mo monthly, -0.28pp DD. Both below thresholds,
so no mandatory explanation; the move is still attributable (leader
ablation): only_funding 3.711 (+0.196), only_carry 3.532 (+0.017),
only_budget 3.478 (-0.037), only_min_notional 3.515 (+0.000).
Funding (actual signed funding vs flat 5bps on longs) dominates:
funding leg -18.09 -> -8.13 (+9.96pp over 5y); gross +0.84, exec +0.06,
carry -0.28, carry_cost +0.70 net to +11.28pp total (~+0.19pp/mo).

## Timing review of `engine_real.py`

- `market()`: r_next = o.shift(-2)/o.shift(-1)-1 (holding bar t+1). lo/hi =
  kline low/high shifted -1 over open shifted -1 (same holding bar). fund =
  funding_at_bar_open shifted -2 (settlement at open of bar t+2). Correct:
  a decision at close t fills during t+1 (min 0..15) so it misses the t+1
  open settlement and is held at the t+2 open settlement.
- `carry_real()`: rp/rs shift(-2)/shift(-1), fund rate.shift(-2), same t+2
  timing; selection on [first+30d, anchor-EMBARGO] Sharpe, forward
  [anchor, +365d); causal (`position()` uses funding known at close,
  ffill). No decision uses future funding.
- `run()`: realized uses books.shift(2) and carry.shift(1) (2-bar/1-bar
  lags); vol rolling 360/min120; s = min(0.25/vol,2) else 1; governor uses
  eq[j]/peak540 with j=i-2 only. Budget cuts carry first then scales books;
  min-notional uses eq[i-1] with BTC100/ETH20/other5, keeps prev_w, skips
  w==0 (closes pass). Execution replays v135 10bps limit on bar t+1 1m
  data; no decision conditions on it. eq_lo uses adverse extreme of bar
  i+1 minus exec plus min(funding,0): conservative bound.
- No look-ahead found in any decision path. One immaterial nuance:
  leader normalises intrabar bound by eq at first live close
  (eq[full]/eq[full][0]); audit normalised by pre-live equity. Difference
  is one bar of net (<1bp on the bound; both round to 22.11/21.37).

## Binance funding semantics (independent check)

Binance USD-M funding settles every 8h (00:00/08:00/16:00 UTC); a position
open at the settlement timestamp pays/receives (longs pay positive, shorts
receive; closing before settlement avoids it). Engine charging the t+2
open settlement to a position filled during t+1, and excluding the t+1
open settlement, is exactly this rule applied to 4h-floored buckets
(zero buckets on 04/12/20 UTC contribute nothing). Carry sleeve uses the
same t+2 fund timing with real 0.001+0.0005 leg costs. Consistent.

## Verdict

PASS. Independent replication equals the leader result on both rows to
rounding; funding settlement-vs-holding timing is correct with no
look-ahead in decisions. `engine_real` is sound as the evaluation
standard. Standing caveats (documented, not blockers): close-sampled DD,
intrabar bound assumes all assets worst simultaneously, no maker queue
probability from OHLC/1m offsets, stop/timeout fills market-like.
