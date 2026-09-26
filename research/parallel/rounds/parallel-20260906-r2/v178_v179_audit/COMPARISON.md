# v178 + v179 blind audit — Part B comparison

Blind: `research/parallel/rounds/parallel-20260906-r2/v178_v179_audit/replication.json`
was saved before `v178/` or `v179/` was opened (see Part A script header
assumptions C1–C11). Base: v175/v176 audit replications (limit-dip sleeve,
W=60 execution, engine_real FULL loop).

## A. v178 ladder (A1)

Audit sleeve: resting bids at k in (2.5,3,3.5,4) sigma below open(T),
minutes 16..238, maker 0.0002 at bid on trade-through, taker exit at
open(T+4h) with crash-aware slippage s_out + funding; per-bar sleeve =
sum over 5 assets x 4 rungs of 0.0625*r; sleeve_unit = sleeve/1.657;
vol leg realized = 0.8*books[i-2]*ret + 0.6*carry[i-1] +
sleeve_unit_uncapped[i-2] (shift-2 fix); payoff s*g*sleeve_unit on live bars.

| row | monthly % | full-path DD % (4h) | 1m-marked DD % | mean s |
| --- | --- | --- | --- | --- |
| v178 primary_ladder (unfixed vol shift-1) | 5.481 | 18.34 | — | 1.497 |
| v178 fixed_normal (shift-2 diagnostic) | 5.508 | 18.57 | 27.79 at 2025-10-10 16:00 | — |
| audit v178_normal (shift-2) | 5.508 | 18.57 | 27.79 at 2025-10-10 16:00 | 1.486 |
| v178 fixed_stress | 4.788 | 19.23 | 27.81 at 2025-10-10 16:00 | — |
| audit v178_stress | 4.789 | 19.23 | 27.81 at 2025-10-10 16:00 | 1.484 |

Yearly (audit vs fixed_normal): 43.88/48.55/179.68/102.63/106.03 on both;
DD 18.57/15.64/16.57/11.14/12.31 on both; fills 2038/2180/2190/2190/2184
on both. Stress yearly within +0.01..+0.03pp
(37.41 vs 37.40, 36.42 vs 36.41, 156.34 vs 156.31, 83.57 vs 83.54,
87.68 vs 87.65); monthly +0.001pp. MATCH up to the documented stress-
slippage accounting delta (leader adds +5bps into s_out;
audit deducts 5bps as exit fee — base/L differs from 1 by k*sigma,
~0.3bps) plus float32-cube/keep-first vs float64-ffilled/keep-last and
sigma-seeding conventions already known from v175–v177.

Ladder fills (full grid): audit 2.5/3/3.5/4 = 3024/1900/1259/869,
total 7052. Leader applied-window fills_per_rung sum to the same ladder
(2021: 408+245+160+119=932; audit live total taken+cancelled for v179
is 5184 on both rows — same fill universe; see v179 below).
No walk-forward k choice exists, so the v175 knife-edge k-flip source is gone.

Worst bar (audit, single-bar net among live): 2024-03-05 12:00 UTC
(net -0.1657 normal, -0.1667 stress). 1m worst minute cluster at
2025-10-10 16:00 UTC (liquidation-crash window, as the v179 header notes).

## B. v179 budget ladder (A2)

Leader rule (`v179_stress_budget_ladder.py:30-31,106-120`): N_MAX =
0.05/0.30 = 1/6 of equity total open-notional cap per holding bar; rung
fills taken in order (fill minute, shallower rung = smaller k, column
order BNB,BTC,ETH,SOL,XRP) while cumulative used + q <= N_MAX
(q = s*g*0.25/4/1.657); later fills cancelled; vol leg still uncapped
shift-2.

Audit frozen assumption C9 misread "0.05/0.30" as two simultaneous caps
(per-asset 0.05 AND total 0.30). With typical q ~= 0.05 (s*g ~= 1.3–1.5),
the per-asset 0.05 leg binds on the first rung and cancels almost
everything. Result:

| row | monthly % | 4h DD % | 1m DD % | taken / cancelled (live rungs) |
| --- | --- | --- | --- | --- |
| v179 primary_normal (leader, N_MAX=1/6 total-only) | 4.141 | 18.24 | 19.81 at 2022-11-09 12:00 | 2055 / 3129 |
| audit v179_normal (0.05 per-asset + 0.30 total) | 3.938 | 18.04 | 18.31 at 2022-04-21 16:00 | 891 / 4293 |
| v179 stress (leader) | 3.729 | 18.43 | 20.72 at 2022-11-09 12:00 | 2074 / 3110 |
| audit v179_stress | 3.652 | 18.20 | 18.45 at 2022-04-21 16:00 | 894 / 4290 |

Fill universe is identical: taken+cancelled = 5184 live rungs on both
rows (891+4293 = 2055+3129 = 5184; stress 894+4290 = 2074+3110 = 5184).
Only the budget cap differs. Audit yearly nets are uniformly lower
(normal: 22.33 vs 23.83, 43.86 vs 45.63, 106.27 vs 119.46, 66.14 vs
71.20, 68.33 vs 68.41) because the per-asset leg over-cancels.
Vol scale s is unaffected (same uncapped shift-2 leg): audit mean_s
1.486/1.484.

Consequence: v178 part REPRODUCED exactly; v179 payoff NOT reproduced
under the audit's frozen C9, for the documented single reason
(total-only 1/6 vs per-asset+total). Re-running the audit loop with
N_MAX total-only would recover the leader row (same fills, same s,
same ordering key); the blind `replication.json` is left untouched per
the blind rule.

## C. Look-ahead checks (leader code)

Budget (`v179_stress_budget_ladder.py:106-120`): `fills` built from
`fmins` (first minute with low<L, strictly inside T) only; sort key is
`(fill minute, rung index, asset column)` — rung index 0..3 is shallower
(2.5) first, asset index follows books columns
BNBUSDT,BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT. `rn = s[i]*g[i]*SIZE/nr/S_REF`
uses s[i] from `unit.shift(2)` (uncapped, decision i needs only exits
through bar i-2) and g[i] from 2-bar-lagged combined equity. No exit
price, no future bar, no post-anchor data enters take/cancel. A live
system knows its own fills minute by minute. PASS.

1m mark (`v178_diagnostics.py:106-117`, `v179:124-131`): books path vs
4h open(T), sleeve rungs from their fill minute at close/L-1 with size
s*g*0.25/4/1.657 (taken only for v179), minute eq =
prev*(1+path-exec+min(funding,0)). Uses only fill-minute-known L/f and
contemporaneous 1m closes; sleeve fees/funding stay in the bar-close
payoff (conservative gross marking, as v176 audit). Audit 1m DD matches
leader to 0.01pp on v178 (27.79/27.81) with the same worst bar
(2025-10-10 16:00). PASS. Close-sampled DD understates the intrabar path
by ~9.2pp on v178 (18.57 vs 27.79).

## Verdict

- v178: REPRODUCED (shift-2 fixed row exact on monthly/yearly/DD/1m-DD/
  worst-bar/fills; stress within 0.001pp monthly from the documented
  s_out+extra vs extra-as-fee accounting).
- v179: fill set REPRODUCED (5184 live rungs both), budget NOT reproduced
  under frozen C9 — audit applied per-asset 0.05 + total 0.30, leader
  applies total-only N_MAX = 0.05/0.30 = 1/6. This fully explains
  -0.20pp monthly and taken 891 vs 2055.
- Causality: vol shift-2 fix corrects the v176 ~1-minute forward use;
  budget ordering and 1m mark use only fill-minute-known info. PASS.
- Economics: ladder 5.508%/mo (fixed) vs v176 5.239%/mo but DD 18.57 vs
  20.72 and 1m DD 27.79 (crash window); budget cuts it to 4.141%/mo,
  gate DD max(18.24,19.81)=19.81 normal / max(18.43,20.72)=20.72 stress.
  Both fail monthly>=5% on the budgeted row; 1m DD exceeds 20% on stress.
  Manifest `rejected` stands.
