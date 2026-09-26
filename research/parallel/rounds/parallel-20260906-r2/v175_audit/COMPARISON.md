# v175 audit — Part B comparison

Part A `replication.json` was saved before `v175/` was opened.
Independent implementation from `OPENCODE_V175_AUDIT.md` (+ v171/v172 audit
base) only (`v175_audit/replicate_v175.py`); engine_real imported solely
for `v154_books`, `context`, constants; W=60 execution rebuilt from
`v135.load_1m` per the v170 spec. Numbers below from
`v175_audit/checks_v175.py` (raw parquet, no v175 imports except the
result JSON).

## Reproduction vs `v175/v175_result.json` — exact on 3/5 anchors, knife-edge k-flips on 2

| Anchor | k audit/v175 | Sleeve net% | Sleeve DD% | Events |
|---|---|---|---|---|
| 2021-09-24 | 2.5 / 2.5 | 14.79 / 14.79 | 15.83 / 15.83 | 408 / 408 |
| 2022-09-24 | 4 / 4.0 | 6.34 / 6.34 | 10.06 / 10.06 | 118 / 118 |
| 2023-09-24 | 4 / 4.0 | 42.04 / 42.04 | 8.55 / 8.55 | 147 / 147 |
| 2024-09-24 | 3 / 3.5 | 26.46 / 28.18 | 8.69 / 4.93 | 260 / 166 |
| 2025-09-24 | 4 / 3.5 | 26.44 / 31.77 | 4.69 / 6.79 | 127 / 198 |

Combined (books W60 + sleeve): full-path DD 22.81 / 22.81 at both sizes
(driven by the exactly-matching 2021 year). Monthly 5.509 / 5.627 (0.25)
and 4.884 / 4.963 (0.15). Yearly rows 2021–2023 match exactly at both
sizes (net, DD, fills, mean_g, e.g. 0.25: 42.19 / 49.40 / 176.85); only
2024/2025 differ, purely from the k-flip (audit 0.25: 101.87 / 110.30 vs
v175 107.54 / 118.80). Books alone (W60): 3.802 / 18.93 both — the audit
loop reproduces the v172-audit gate. `reference_v172 [4.597, 22.42]` in
the v175 result is the v172 primary size-0.25 row, confirmed consistent
with the v172 audit (4.597 / 22.42).

Diagnosis of the flips (verified numerically, both conventions causal):
v175 seeds the sigma rolling window at the grid start (2020-02-01) and
selects on `t <= anchor-1d`; the audit uses full pre-history sigma and
`t < anchor-1d` (same frozen choice as the v171/v172 audits). Only 720
sigma cells differ (first ~240 grid bars, March 2020 + early-history
gaps). Re-running selection under v175's conventions reproduces v175's k
AND its train Sharpes to all 4 decimals (0.0601 / 0.0517 / 0.0440 /
0.0456 / 0.0451). Margins are knife-edge: 2024 audit 3 (0.0450) vs 3.5
(0.0448, gap 0.0002); 2025 audit 4 (0.0445) vs 3.5 (0.0443, gap 0.0002).
Any sub-0.01bp convention (float32 cube, keep-first vs keep-last dedup,
seeding, boundary bar) flips these two anchors. Per-bar sleeve returns at
FIXED k were not contradicted anywhere (3 exact anchors + exact 2021–2023
combined rows).

## Code review (`v175_limit_dip_sleeve.py`)

- Look-ahead: none found. sigma uses 4h opens <= t; L is priced off
  open(T) known at placement; fill minutes 16..238 are strictly inside
  T = t+4h; the only uses of T+4h data are the exit fill (4h open base +
  minute-0 range for s_out) and the same-bar funding settlement. `filled`
  requires finite exit open — execution, not signal. Cube offsets place
  minutes by `(open_time - floor4h)//60` (correct); within-bar ffill never
  carries across bars; minute 0 is never ffilled.
- Exit-base assumption confirmed: v175 uses the 4h open(T+4h) (not the 1m
  minute-0 open) with s_out from the minute-0 range — exactly the audit's
  frozen A6. Dedup keep-first vs keep-last is moot (zero duplicated 1m
  timestamps per the v171 audit); float32 vs float64 is sub-0.01bp.

## Adversarial checks

(1) Look-ahead: none (above). Rebuilt fill minutes span [16, 238], all
strictly inside the holding bar, after the decision.

(2) Marketable bids (open of minute 16 < L): 14/1060 fills (1.3%) —
2/408 (2021), 3/118 (2022), 6/147 (2023), 0/260 (2024), 3/127 (2025).
Re-pricing those fills at the minute-16 open with taker fee 0.0005
instead IMPROVES every year (sleeve-sum deltas +0.0068 / +0.0161 /
+0.0363 / 0 / +0.0111; implied 2023 net 42.04 -> 45.82%). The model's
fill at L with maker fee is conservative in all 14 cases, never
optimistic. Immaterial to the result.

(3) Gap fills (trigger-minute low >2% below L): 53/1060 (5.0%), max gap
8.19% (2023). A resting buy bid is filled at L as the price trades
through L — including gap-opens below L, where the true fill (open or
better) beats L. Model price L is conservative in every gap case. Gap
events average -23.5bps in 2021 (vs +15.6bps all events) but +58…+366bps
elsewhere — gaps are not the engine of the result.

(4) Top-5% concentration: share of each year's sleeve sum from the top 5%
of events — 2021: 196.2% (21 events carry 0.3128 of 0.1594), 2022:
188.6%, 2023: 44.1%, 2024: 64.5%, 2025: 44.7%. Without the top 5%, the
2021/2022 sleeves go negative. This is a crash-rebound strategy whose
early years rest on ~6–21 panic bars — more concentrated than v171.

(5) Exit at T+4h+15min (same fees/funding, s_out recomputed at minute 15,
0 missing bars): 2021 +15.09pp (14.79 -> 29.88, doubles), 2022 +4.13pp,
2023 +1.52pp, 2024 -0.06pp, 2025 -4.15pp. No systematic collapse — the
rebound is not just the 4h-open print — but 2021 doubles with a 15-minute
delay and 2025 loses ~1/6. Exit timing moves results by ~±15pp.

(6) 2021 drawdown: sleeve-alone peaks 2021-11-26, troughs 2022-05-11
(DD 15.83%). Books-alone (governor-less light loop, dates indicative)
peaks 2022-01-12, troughs 2022-04-18 — fully inside the sleeve DD window.
YES, they lose together: overlapping DD windows, 20/365 days jointly
negative in 2021, and the combined 2021 DD (22.81) exceeds both alone
(books 18.93, sleeve 15.83). Daily corr(sleeve, books) is -0.079, so it
is not day-to-day correlation but shared exposure to the same 2021–2022
stress episode (mean_g falls to 0.804 — the governor binds).

## Reading of the result (not a replication issue)

Resting-limit entry restores the economics vs v172's taker entry (limit
fills: 1060 vs v172's 483 events at applied k; monthly 5.627 vs 4.597 at
identical 22.81 DD). But: full-path DD 22.81 exceeds the 20% governor
reference at both sizes (22.81 / 20.66); 2022 sleeve is thin (+6.34%,
DD 10.06%); k-selection in 2024/2025 is knife-edge (see above); the
result leans on a handful of crash bars and on exit timing in 2021.

## Verdict

CONDITIONAL PASS — no look-ahead, no exit-misalignment, no optimistic
fill found; 3/5 anchors, all 2021–2023 combined rows, books gate, and
full-path DD reproduce exactly, and the two k-flips are fully explained
(grid-seeded sigma + boundary bar; v175's convention re-run matches its
k and Sharpes to 4dp; both conventions are causal). Downgraded from full
PASS because 2024/2025 do not reproduce under the audits' frozen
conventions and the strategy carries documented fragilities: top-5%
events exceed 100% of the 2021/2022 sleeve sums, 2021 doubles with a
15-minute exit delay, and the sleeve draws down together with the books
in 2021–2022 (combined DD 22.81 > 20%). Hypothesis-grade, not validated.
