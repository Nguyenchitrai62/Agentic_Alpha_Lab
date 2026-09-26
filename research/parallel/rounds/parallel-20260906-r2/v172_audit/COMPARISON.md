# v172 audit — Part B comparison

Part A `replication.json` was saved before `v172/` was opened.
Independent implementation from `OPENCODE_V172_AUDIT.md` (+ v171 spec) only
(`v172_audit/replicate_v172.py`); engine_real imported solely for
`v154_books`, `context`, constants; W=60 execution rebuilt from
`v135.load_1m` per the v170 spec.

## Reproduction vs `v172/v172_result.json` — EXACT on everything

| Anchor | k audit/v172 | Sleeve net% | Sleeve DD% | Events |
|---|---|---|---|---|
| 2021-09-24 | 4 / 4.0 | 24.31 / 24.31 | 4.90 / 4.90 | 101 / 101 |
| 2022-09-24 | 4 / 4.0 | -4.62 / -4.62 | 11.17 / 11.17 | 95 / 95 |
| 2023-09-24 | 4 / 4.0 | 15.09 / 15.09 | 8.57 / 8.57 | 105 / 105 |
| 2024-09-24 | 4 / 4.0 | 13.00 / 13.00 | 2.50 / 2.50 | 84 / 84 |
| 2025-09-24 | 4 / 4.0 | 16.28 / 16.28 | 6.16 / 6.16 | 98 / 98 |

Books alone (W60): 3.802 / 18.93 both. Combined monthly / full-path DD:
size 0.25: 4.597 / 22.42 both; size 0.20: 4.476 / 21.39 both;
size 0.15: 4.334 / 20.12 both. All 15 yearly nets, DDs, fills and mean_g
exact (e.g. 0.25: 42.27 / 31.58 / 125.56 / 82.66 / 92.29). No return diff
> 1pp, no DD diff > 0.5pp anywhere — nothing to explain.

Non-material definitional diffs (all numerically immaterial, numbers exact):
train Sharpe per bar matches to 3dp (audit .0432/.0399/.0313/.0295/.0291 vs
v172 .0429/.0397/.0311/.0293/.0290) — same cause as in the v171 audit: v172
seeds the sigma rolling window at the grid start (2020-02-01) while the audit
uses full pre-history; k choices and every reported number are unaffected.
Selection uses `G <= anchor-1d` (audit: `<`), one extra bar, no effect.
Exit base is the 4h open(T+4h) with s_out from the 1m minute-0 range (audit:
1m minute-0 open base with 4h fallback) — exact match shows the two prints
coincide. 1m dedup keep-first vs keep-last is moot (zero duplicated 1m
timestamps per the v171 audit); float32 cube vs float64 is sub-0.01bp.

## Code review (`v172_sleeve_realistic.py`)

- Look-ahead: none found. sigma(t) uses 4h opens <= t; trigger (16..238)
  and entry (m+1) minutes are strictly inside holding bar T = t+4h, i.e.
  after the decision; the only use of T+4h data is the exit fill itself
  (base + s_out) plus the same-bar funding settlement. No signal, weight,
  k-selection or return uses post-decision data beyond executed prices.
- Exit-minute alignment: CORRECT. `xr[:-1] = (H[1:,0,:]-L[1:,0,:])/O[1:,0,:]`
  is cube row i+1, minute 0 — the minute starting at T+4h, as specified.
  Minute 0 is never forward-filled (ffill loop starts at 1), so s_out is raw.
  Last-row xr is NaN -> s_out floor 0.0002, and the missing o2 filters the
  row to r = 0. Entry ffill can repeat a stale print (same class as v171,
  conservative direction, disclosed in the v171 audit).
- Combined loop (`v171.run_combined` with W60 exec in ctx): mirrors
  engine_real FULL (vol target, 20% governor with 2-bar lag on combined
  equity, budget, min-notional, real funding/carry); sleeve added as
  `g[i]*sl[i]` live with `sl = sleeve*(size/0.25)` — matches the spec.
  `sleeve_walk_forward` applied windows [anchor, +365d) match; k re-chosen
  with THIS cost per anchor as required.

## Reading of the result (not a replication issue)

Realistic range-based slippage (audit: mean s_in 13–56bps, s_out 7–25bps,
growing with k) flips all five anchors from k=3 (v171) to k=4 and cuts the
sleeve far below v171's +8…+65%/yr: 2022 goes negative (-4.62%, DD 11.17%).
Primary row 4.597%/month FAILS the 5%/month gate and full-path DD 22.42
exceeds 20%; all three sizes breach 20% DD (22.42 / 21.39 / 20.12).

## Verdict

PASS — blind replication matches `v172_result.json` exactly on every row;
no look-ahead, no exit-misalignment, no unrealistic fill found. The cost
model works as specified, but under it the sleeve no longer clears the
leader's gate (4.597%/mo, DD 22.42, 2022 negative) — hypothesis-grade.
