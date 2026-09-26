# v174 audit — Part B comparison

Part A `replication.json` was saved before `v174/` was opened.
Independent implementation from `OPENCODE_V174_AUDIT.md` only, with
`v172_audit/` (`replicate_v172.py` + `replication.json`) as the stated base
(`v174_audit/replicate_v174.py`); engine_real imported solely for
`v154_books`, `context`, constants; W=60 execution rebuilt from
`v135.load_1m` per the v170/v172 spec. Dip leg re-implements v172 exactly;
spike leg mirrors it with the sign flips in the assignment.

## Reproduction vs `v174/v174_result.json` — EXACT on everything

| Anchor | k dip audit/v174 | k spike audit/v174 | Spike net% | Spike DD% | Events |
|---|---|---|---|---|---|
| 2021-09-24 | 4 / 4.0 | 4 / 4.0 | -4.02 / -4.02 | 6.38 / 6.38 | 62 / 62 |
| 2022-09-24 | 4 / 4.0 | 4 / 4.0 | -2.79 / -2.79 | 21.92 / 21.92 | 90 / 90 |
| 2023-09-24 | 4 / 4.0 | 4 / 4.0 | 0.91 / 0.91 | 7.29 / 7.29 | 124 / 124 |
| 2024-09-24 | 4 / 4.0 | 4 / 4.0 | -11.94 / -11.94 | 12.14 / 12.14 | 100 / 100 |
| 2025-09-24 | 4 / 4.0 | 4 / 4.0 | 1.01 / 1.01 | 5.41 / 5.41 | 95 / 95 |

Books alone (W60): 3.802 / 18.93 both.
`check_v172_books_dip` (books+dip 0.25): 4.597 / 22.42 both; all 5 yearly
nets/DDs exact (42.27 / 31.58 / 125.56 / 82.66 / 92.29).
Primary books+dip+spike: 4.402 / 20.52 both; yearly exact
(37.31 / 35.55 / 127.34 / 61.39 / 94.22, DDs 17.59 / 15.00 / 15.26 /
13.87 / 12.95).
Secondary books+spike: 3.543 / 19.04 both; yearly exact
(16.38 / 45.67 / 100.40 / 42.36 / 66.97).
Daily dip-vs-spike correlation: audit -0.2169 applied-coverage
(-0.2170 full-grid, 1826 / 2427 days) vs v174 -0.217.
No return diff > 1pp, no DD diff > 0.5pp anywhere — nothing to explain.

Non-material definitional diffs (all numerically immaterial, numbers exact):
train Sharpe per bar matches to 3dp — dip audit
.0432/.0399/.0313/.0295/.0291 vs v174 .0429/.0397/.0311/.0293/.0290;
spike audit .0067/.0017/.0006/.0009/-.0030 vs v174
.0070/.0020/.0008/.0011/-.0029 — same cause as in the v171/v172 audits:
v17x seeds the sigma rolling window at the grid start while the audit uses
full pre-history; k choices and every reported number are unaffected.
Exit base is the 1m minute-0 open with 4h-open fallback (audit) vs the 4h
open(T+4h) with s_out from the 1m minute-0 range (v174 code) — exact match
shows the two prints coincide (same finding as the v172 audit). 1m dedup
keep-first vs keep-last is moot (zero duplicated 1m timestamps per the v171
audit); float32 cube vs float64 is sub-0.01bp. Daily-corr coverage differs
by one day (audit [first anchor, last+365d) vs code live [START, END)) with
no effect at 3dp.

## Code review (`v174_spike_fade.py::spike_returns`)

- Look-ahead: none found. sigma uses 4h opens <= t
  (`pct_change().rolling(360, min 120)` ending at t); trigger (16..238) and
  entry (m+1) minutes are strictly inside holding bar T = t+4h; the only uses
  of T+4h data are the exit fill itself (o2 base + s_out) plus the same-bar
  funding settlement (`shift(-2)`). `hit.any` with NaN comparisons is False,
  so non-finite trigger closes cannot fire. k-selection reuses the audited
  `v171.sleeve_walk_forward` pre-anchor path. No signal, weight, k-selection
  or return uses post-decision data beyond executed prices.
- Mirror correctness: dip `o2*(1-s_out)/(po*(1+s_in))-1-2*TAKER-fund`
  becomes spike `po*(1-s_in)/(o2*(1+s_out))-1-2*TAKER+fund` — slippage signs
  correctly mirrored (short sells low, covers high), fee identical
  (2*0.0005), trigger correctly flipped (`>= +k*sigma`).
- Short-side funding sign: CORRECT. v172 long pays (`-fund`), v174 short
  receives (`+fund`), matching the code comment ("receives ... pays it if
  negative") and the engine convention (`fundp = -w*fund`: positive funding
  costs longs, pays shorts). Settlement bar (shift -2 = T+4h) matches the
  long leg. Under AGENTS.md (long 0.0001/8h, short zero by assumption) the
  engine/books funding is a separate path; within this sleeve the +fund term
  is the specified symmetric mirror, not a realism break.
- Combined loop (`v171.run_combined` with W60 exec in ctx): primary adds
  `dip_sleeve+spk_sleeve`, secondary `spk_sleeve`, check `dip_sleeve` —
  matches the spec; governor/vol/budget/min-notional/carry path is the
  audited engine_real FULL.

## Reading of the result (not a replication issue)

Spike pre-anchor Sharpes are ~0 (0.007 down to -0.003) vs dip ~0.03-0.04:
spikes do not mean-revert like dips. Spike-alone sleeves lose in 2021/2022/
2024 (-4.02/-2.79/-11.94%, 2022 DD 21.92%) and earn ~0-1% in 2023/2025.
Adding the short to the dip book lowers return (4.402 vs 4.597) while still
breaching 20% DD (20.52); books+spike alone is 3.543/19.04. Daily dip/spike
correlation is -0.217 (weak negative, not a hedge). Primary row FAILS the
5%/month gate.

## Verdict

PASS — blind replication matches `v174_result.json` exactly on every row;
no look-ahead, no exit-misalignment, no funding-sign error found. The mirror
works as specified, but the economics fail: spikes are not symmetric with
dips — hypothesis-grade, correctly rejected.
