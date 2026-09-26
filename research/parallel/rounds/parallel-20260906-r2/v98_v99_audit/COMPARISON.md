# v98 + v99 blind audit — COMPARISON.md (Part B)

Blind replication was saved BEFORE opening `v98/` / `v99/` (see `replication.json`,
`predictions_v98_H2.csv`, `predictions_v98_H1.csv`, `equity_v98_H2.csv`,
`equity_v98_H1.csv`, `equity_v99.csv`, `equity_v99_hidden_exec.csv` in this folder).
Audit scope: `v98/v98_recency.py`, `v98/v98_result.json`, `v98/result_manifest.json`,
`v99/v99_candidate.py`, `v99/v99_result.json`, `v99/result_manifest.json`
(plus `v92/v92_pooled_hgb_vt.py` and `v94/v94_long_short_ensemble.py` as shared base).
No leader files were edited. All writes are under `v98_v99_audit/` +
`tests/test_v98_v99_audit.py`.

Disclosure: a repo-wide grep for 1m fill-rule precedents surfaced 3 lines of
`v99_candidate.py` (docstring carry-cost line + maker-rate lines) before Part A
was saved. Part A was still built solely from the assignment spec plus the
audited v92/v93_v94/v95_v96 replications (recency weights, v96 books, blind
carry-forward and minutes-2..15 window documented in `replicate_v98_v99.py`);
the glimpse did not change any blind choice, and the window difference below
was derived from the spec wording and verified locally after opening.

## A. Number comparison (blind audit vs leader)

### v98 (A1): exact match for both half-lives

Per-anchor IC (blind vs leader `ic_by_anchor`):

| anchor | train rows blind | train rows leader | IC blind H2 | IC leader H2 | IC diff | IC blind H1 | IC leader H1 | IC diff |
|---|---|---|---|---|---|---|---|---|
| 2021-09-24 | 33088 | 33088 | 0.098 | 0.098 | 0.0 | 0.0898 | 0.0898 | 0.0 |
| 2022-09-24 | 44038 | 44038 | 0.0188 | 0.0188 | 0.0 | 0.0257 | 0.0257 | 0.0 |
| 2023-09-24 | 54988 | 54988 | 0.087 | 0.087 | 0.0 | 0.0465 | 0.0465 | 0.0 |
| 2024-09-24 | 65968 | 65968 | 0.137 | 0.137 | 0.0 | 0.1656 | 0.1656 | 0.0 |
| 2025-09-24 | 76918 | 76918 | 0.1334 | 0.1334 | 0.0 | 0.131 | 0.131 | 0.0 |

Yearly normal H=2 (blind vs leader `primary_half_life_2y.normal.yearly`):

| anchor | net % blind | net % leader | diff | DD % blind | DD % leader | fills blind | fills leader |
|---|---|---|---|---|---|---|---|
| 2021-09-24 | 5.56 | 5.56 | 0.0pp | 20.16 | 20.16 | 1295 | 1295 |
| 2022-09-24 | 51.94 | 51.94 | 0.0pp | 12.27 | 12.27 | 1591 | 1591 |
| 2023-09-24 | 50.36 | 50.36 | 0.0pp | 16.44 | 16.44 | 1657 | 1657 |
| 2024-09-24 | 64.03 | 64.03 | 0.0pp | 14.00 | 14.00 | 1830 | 1830 |
| 2025-09-24 | 24.48 | 24.48 | 0.0pp | 20.78 | 20.78 | 1245 | 1245 |

Yearly normal H=1 (blind vs leader `secondary_half_life_1y.normal.yearly`):

| anchor | net % blind | net % leader | diff | DD % blind | DD % leader | fills blind | fills leader |
|---|---|---|---|---|---|---|---|
| 2021-09-24 | 0.69 | 0.69 | 0.0pp | 20.75 | 20.75 | 1303 | 1303 |
| 2022-09-24 | 58.54 | 58.54 | 0.0pp | 10.90 | 10.90 | 1670 | 1670 |
| 2023-09-24 | 36.09 | 36.09 | 0.0pp | 20.73 | 20.73 | 1638 | 1638 |
| 2024-09-24 | 60.78 | 60.78 | 0.0pp | 15.23 | 15.23 | 1905 | 1905 |
| 2025-09-24 | 6.46 | 6.46 | 0.0pp | 31.02 | 31.02 | 1419 | 1419 |

No threshold exceeded (IC diff > 0.01 or return diff > 1pp): nothing to explain for v98.

### v99 normal (A2): nets within threshold; fills exact

Yearly normal (blind vs leader `normal.yearly`):

| anchor | net % blind | net % leader | diff | DD % blind | DD % leader | fills blind | fills leader |
|---|---|---|---|---|---|---|---|
| 2021-09-24 | 10.95 | 11.13 | 0.18pp | 14.06 | 14.04 | 1570 | 1570 |
| 2022-09-24 | 33.05 | 33.07 | 0.02pp | 10.88 | 10.87 | 2174 | 2174 |
| 2023-09-24 | 55.29 | 55.30 | 0.01pp | 7.61 | 7.62 | 2175 | 2175 |
| 2024-09-24 | 37.94 | 37.95 | 0.01pp | 9.12 | 9.12 | 2147 | 2147 |
| 2025-09-24 | 21.32 | 21.32 | 0.0pp | 15.34 | 15.34 | 2055 | 2055 |

Return diffs are all < 1pp (max 0.18pp in 2021); DDs within 0.02pp; fills exact.
Root causes of the small 2021 delta are the same three v93 conventions below,
not hidden logic.

### v99 hidden-year 1m execution: net diff exceeds 1pp; maker-rate gap identified

| metric | blind audit | leader `hidden_year_1m_execution` | diff |
|---|---|---|---|
| net % | 17.43 | 18.69 | 1.26pp |
| monthly geo % | 1.349 | 1.439 | 0.09pp |
| max DD % | 17.11 | 16.62 | 0.49pp |
| fills (trend-leg bars) | 2055 | 2055 | 0 |
| maker fills / orders (blind) | 6629 / 7641 | — | — |
| maker rate | 0.8676 | 0.897 | 0.0294 |

The 1.26pp net gap exceeds the 1pp threshold and is fully attributed to the
1m window definition in B.2 (verified: recomputing the blind orders with the
leader window gives 6857 makers / 7646 orders = 0.8968, i.e. the leader 0.897).

## B. Root causes of the deltas

### B.1 v99 normal (all < 1pp; same pattern as the v93 audit)

1. Carry-leg timing convention. Blind assumed a uniform forward convention:
   `pos_t = 0.6*s_t` earns `carry[t+1]` (book uses `carry[t-1]` realised at `t`,
   mirroring the model leg's 2-bar delay). The leader script uses
   `carry_exp * carry` contemporaneously (`exposure[t]*carry[t]`,
   `v99_candidate.py:100-101`) while its vol book uses `carry.shift(1)`.
   Same asymmetry as audited v93 (`v93_portfolio.py:52`); it is an execution
   assumption, not leakage, and washes out after the vol window fills (2022+
   agree to <= 0.02pp).
2. Early-window NaN handling. Leader's `realized` leaves first-bar NaNs in
   (`books.shift(2)*(o/o.shift(1)-1)` and `carry.shift(1)` with no `fillna(0)`,
   `v99_candidate.py:83`), so `vol` stays NaN longer and `s` stays at the causal
   default 1.0; blind filled realised components with 0.0, giving a slightly
   different scale path only in the first ~120-360 bars of 2021. Later years
   are unaffected.
3. Initial carry-turnover cost. Leader fills the first `carry_exp.diff()`
   with 0.0 (no establishment cost on the carry leg, `:101`); blind filled it
   with `|pos|` (consistent with the model leg). One-off level effect in 2021
   only.
4. Fills definition (no gap here). Both count trend-leg turnover bars only
   (`Wt.diff`, `v99_candidate.py:92,110` vs blind `model_turn`); carry rescaling
   costs are charged but never counted. Fills agree exactly, unlike the v93
   blind which had added carry bars.

### B.2 v99 hidden execution (1.26pp gap; window definition)

1. 1m window. The spec sentence "a 1m bar within minutes 2..15" was read blind
   as bars with open_time in `[T+2min, T+15min]` inclusive (14 bars), with the
   fallback fill at the minute-15 1m open (`replicate_v98_v99.py:
   run_hidden_execution`). The leader slices `m.loc[fill_bar:fill_bar+14min]`
   (15 1m bars, minutes 0..14) and tests `w["low/high"].iloc[1:]`, i.e. minutes
   1..14 (`v99_candidate.py:56-61`); the fallback is the minute-15 1m open when
   present. Both use strict trade-through (buy: `low < p0`; sell: `high > p0`)
   and the same fallback price (`minute-15 open * (1+0.0002*side)`) with maker
   0.0002 / taker 0.0005. The one-minute shift at each end moves ~228/7646
   orders from maker to taker: leader 0.897 vs blind 0.8676. Local recomputation
   on the blind `Wt` with the leader window gives 0.8968, confirming the window
   is the whole maker-rate gap; the ~1.26pp net gap is the corresponding taker
   uplift (extra 0.0003 fee + `|fill/limit-1|` drag on those orders).
2. Cost model is otherwise identical. Leader `cost = |dW|*fee_rate + dW*rel`
   with `rel = px/p0-1 +/- 0.0002` (`:97-99`) equals blind
   `extra = |diff|*0.0003 + |diff|*|fill/limit-1|` on top of the normal
   `turn*0.0002`; carry legs keep the lab cost model in both
   (`:100-101`, docstring `:6-7`). Funding (`0.00005` long gross) is unchanged
   in both execution paths.
3. Gap handling (no effect in this window). Leader `if len(w) < 15: continue`
   leaves `rel=0, maker=True` (zero cost, counted as maker); blind counted a
   missing 1m bar as taker. `missing_1m=0` over 2025-09-24..2026-09-23, so this
   does not contribute here, but it is an optimistic edge for gappy symbols.

## C. Look-ahead audit

### `v98_recency.py` — no look-ahead found

- Data/features: imports audited `v92` and calls `v92.build()` (spot prefix
  strictly before first USD-M bar, past closes, ewm `adjust=False`, daily
  SMA/ribbon + funding via `merge_asof backward`, volume z past 180). Pass.
- Labels/embargo: reuses `v92.EMBARGO_BARS` (102) and `v92.H` (42);
  `tr = t<cutoff and t+172h<cutoff and y not NaN` with `cutoff = A-408h`
  (`:28-30`), identical to audited v92. Pass.
- Recency weights: `age = cutoff - row open_time` in 365.25-day years,
  `w = 0.5**(age/H)` with H=2/1 (`:31-32`). Both inputs are known at training
  time (cutoff is the anchor-derived training boundary, row time is the bar
  being weighted); no OOS or future timestamps enter. Passed to HGB as
  `sample_weight` (`:35`); predictions use only contemporaneous features.
  IC is `spearman(pred, y)` on the OOS year (`:45`), NaN handling by pandas
  corr. Pass.
- Weights/vol/execution: `v92.weights_from` (long-only, contemporaneous
  pred/rib/vol42, `|raw|` normalisation, `active/5`, daily ffill),
  `v92.vol_target_scale` (trailing 60d/min-20d on `W.shift(2)` realised
  returns, cap 2, NaN->1), `v92.simulate` (`W_t*scale_t` earns
  `open[t+2]/open[t+1]-1`, fee+slip on scaled turnover, `0.00005`/bar long
  funding), `v92.stats` yearly cuts. Same timing as audited v92. Pass.

### `v99_candidate.py` — no look-ahead found (one timing-asymmetry note, as in v93)

- Books: retrains audited `v92.train_predict`/`weights_from` and
  `v94.add_targets`/`train_predict`/`weights_ls` over the same 5 anchors
  (`:72-77`); each book's own `vol_target_scale` (trailing 60d/min-20d,
  cap 2, NaN->1) is applied before combining
  `books = 0.5*W_lo*s_lo + 0.5*W_ls*s_ls` (`:79-80`). All scale inputs are
  lagged realised returns. Pass.
- Portfolio vol: `realized = 0.8*(books.shift(2)*ret1).sum + 0.2*3*carry.shift(1)`
  uses only realised (lagged) returns; `vol` trailing 360-bar (min 120)
  `*sqrt(2190)`; `s = min(0.15/vol, 2)`, NaN->1 causal default (`:83-85`). Pass.
- Normal execution: model leg is v92-identical forward timing (`Wt = 0.8*s*books`
  earns `o[t+2]/o[t+1]-1`, costs on scaled turnover + long funding `:100`);
  carry leg charges `|diff(carry_exp)|*2*0.0004/1.2` with first diff 0. The carry
  leg uses `exposure[t]*carry[t]` (0-bar delay) while the model leg uses a 2-bar
  delay — the same inconsistent execution assumption flagged in v93, but all
  scale inputs are lagged, so it is not forward leakage. Fills count the trend
  leg only (reporting choice, matches blind). Pass with note.
- Hidden 1m execution: orders are `Wt.diff()>1e-9` at `t>=2025-09-24`
  (`:54,117`); each executes at `fill_bar = t+4h` (`:55`) as a limit at that
  bar's 1m open (`p0`, `:59`); the fill test uses strictly later 1m bars
  (`iloc[1:]`, `:61`) and the fallback is the minute-15 1m open (`:63`), both at
  or after the execution-bar open — correct 1-bar delay from the decision at `t`,
  no future beyond the execution bar. Strict through (`<`/`>`) matches the
  v91 precedent. The minutes-1..14 window vs the spec's minutes-2..15 wording
  (B.2) and the `len<15: continue` optimistic gap default are implementation
  choices, not leakage. Pass with the window labelled.

## D. Manifest notes

- `v98/result_manifest.json`: track A, status `rejected`, `live_approved:false`,
  `audit.passed:false, replay_complete:false` ("awaiting OpenCode audit").
  Normal monthly 2.693%, worst-year DD 20.78%, fills 7618/60mo; secondary 1y
  monthly 2.213%, worst DD 31.02%.
- `v99/result_manifest.json`: track C, status `rejected`, `live_approved:false`,
  same pending-audit flags. Normal monthly 2.269%, worst-year DD 15.34%,
  fills 10121/60mo; hidden 1m execution net 18.69% / DD 16.62% / maker 0.897.

## E. Verdict

- v98 blind reproduction is bit-exact (train rows, ICs, yearly nets/DDs/fills
  for both H=2 and H=1). Leader v98 code has no look-ahead in data,
  labels/embargo, recency weights, features, vol-target, or execution.
- v99 normal nets reproduce within 0.18pp (threshold 1pp) with DDs within
  0.02pp and fills exact; residual deltas are fully attributed to the
  documented carry-timing, early-NaN/default, and initial-cost conventions
  carried over from v93, not to hidden logic or leakage.
- v99 hidden-year 1m execution differs by 1.26pp net (threshold exceeded) with
  maker 0.868 blind vs 0.897 leader; the gap is fully attributed to the 1m
  window definition (minutes 2..15 blind vs 1..14 leader, verified locally to
  reproduce the leader maker rate to 0.0002). Cost model, funding, carry
  handling, and 1-bar execution delay are otherwise identical, and the leader
  1m path has no look-ahead. The window and the `len<15` gap default should be
  carried as labelled execution assumptions. Audit complete; leader files
  untouched.
