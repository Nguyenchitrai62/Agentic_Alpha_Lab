# oc_idea5 PLAN (pre-registered BEFORE any outcome is computed)

Idea #5 of `research/tournament/oc_ideas/IDEAS.md`: premium-gated book flips
(veto reversals into dislocated tape). This file freezes the hypothesis, data,
exact causal definitions, the single scored variant, and the decision rule
before any outcome statistic (`r`, `pn`, returns, DD, Sharpe, worst-day) is
computed. Only counts/spans (grid size, file date ranges) were inspected to
write it; no `y`/return column was read. No tuning on results; any post-hoc
change is logged in REPORT.md.

## Hypothesis (fixed here)

Member D works because Coinbase premium carries information (v285). The
unexploited use is execution, not weight: flipping the book short into a
deeply negative Coinbase-minus-Binance dislocation (or long into a positive
one) is selling the flush bottom — delaying the flip by one bar avoids the
flip-whipsaw. Expected per IDEAS.md: return +0.0–0.2 pp/mo, DD −0.3–1.0 pp,
turnover falls. Sign is read from the data; consistency across anchor years is
what matters (rule below). This differs from v285 (premium as a 20% ensemble
weight) and from oc_premfill (premium level AT THE FILL for dip outcomes): a
bar-open BOOK execution veto, no weight change, different layer/timing.

## Inputs (read-only, never edited)

- Books: rebuilt EXACTLY as `scripts/forward_v205.py::research_books_d2`
  (same files, same math as `oc_bookvol/compute_bookvol.py`: O1 = half
  (A+B)/2 + half (Aq+Bq)/2 on the union index missing -> 0.0, then
  D2 = 0.8*O1 + 0.2*(D+Dq)/2) from `artifacts/research/engine_real/`.
- Opens: `artifacts/research/engine_real/opens_v154.parquet` (4h opens,
  Binance USD-M perps BTC/ETH/SOL/BNB/XRP).
- Coinbase hourly (spot, close only):
  `data/raw/coinbase_20260925/BTC-USD_1h.parquet`,
  `data/raw/coinbase_20260925/ETH-USD_1h.parquet`,
  `data/raw/coinbase_alts_20260930/SOL-USD_1h.parquet`,
  `data/raw/coinbase_alts_20260930/XRP-USD_1h.parquet`
  (columns open_time/close; open_time = hourly bar START UTC).
  BNB has no Coinbase listing -> premium always NaN -> gate never fires
  for BNB (disclosed fail-safe, not a fit).
- Binance perp hourly: `research/tournament/ext/hourly_ext.parquet`
  (t = hour START UTC, close = perp hourly close resampled from 1m; its
  4h-boundary opens match `opens_v154` median diff 0 — verified from
  counts only). LIGHT equivalent of the assigned "Binance 1m": hourly
  aggregation only (same precedent as oc_idea7 hourly-vs-1m); no 1m file
  is loaded by the screen.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides
  the old RULES.md hidden-year cut; all five years are research data, any
  finding still needs prospective validation). Hourly/Coinbase bars with
  START >= 2026-09-24 00:00 UTC are dropped; no data beyond the cutoff used.
- One process, 4h grid + two hourly panels only, RAM < 1 GB.

## Exact causal definitions (fixed now, one variant only)

- Grid: inner join of books index with opens index (dropna all), sorted 4h
  grid (expected 10956 bars 2021-09-24..2026-09-23 20:00 from counts only).
  Weight `w_c[t]` (raw books_d2) is known at the close of bar `t`.
- Next-bar simple return: `r_c[t] = open_c[t+1]/open_c[t] - 1`. The last
  grid bar has no forward return and is dropped (expected scored 10955).
  Same timing as oc_bookvol/oc_idea9.
- BASE (deployed, identical to oc_bookvol V0): `u[t] = sum_c w_c[t]*r_c[t]`;
  `sig0[t] = std(u[t-360..t-1], ddof=1)*sqrt(2190)`, min_periods 120;
  `s0[t] = min(2, 0.25/sig0[t])`, NaN or sig <= 0 -> 1.0;
  `ws_base_c[t] = w_c[t]*s0[t]`. Windows end at t-1 (strictly before t).
  `sign(ws_base)==sign(w)` since `s0>0`.
- Premium level (bps, scale-free): for coin c and hourly START h
  (both bars START < 2026-09-24 00:00 UTC),
  `p_c(h) = 1e4*ln(CB_close(h)/BN_close(h))` where CB = Coinbase hourly
  close, BN = hourly_ext close. Either leg missing/non-finite/<=0 -> NaN.
  BNB -> always NaN. Reading of IDEAS.md "strictly <T": every hourly bar
  used has START < T (bar completed at/before T is known at the 4h close T;
  the bar starting at T is never used).
- 1h mean before T: `x_c(T) = p_c(T-1h)` (the single hourly premium bar
  with START = T-1h, END == T). Missing -> NaN -> no veto (fail-safe).
  With hourly inputs the "1h mean" is that one completed hour.
- Dislocation z: `z_c(T) = (x_c(T)-mean(W))/std(W,ddof=1)` where
  `W = {x_c(S) : S a 4h grid time, S < T, S >= T-90d}` (up to 540 prior
  4h samples, strictly before T). Require >= 270 non-NaN in W else NaN;
  std non-finite or <= 0 -> NaN. Unit: standard deviations.
- Flip signal (per coin, strict reversal only): `flip_c(T) = 1` iff
  `sign(w_c[T])*sign(w_c[T-1]) < 0` (opposite non-zero signs on the raw
  books, equivalently on BASE). Flat (0) never counts; first grid bar
  never flips. Entries/exits via zero are NOT vetoed (disclosed).
- Veto INTO the dislocation (single pre-registered threshold 2.0):
  `veto_c(T) = 1` iff `flip_c(T)==1` AND `z_c(T)` non-NaN AND
  `((w_c[T] > 0 AND z_c(T) > +2.0) OR (w_c[T] < 0 AND z_c(T) < -2.0))`.
  That is the IDEAS.md example: short into deeply negative dislocation,
  long into deeply positive dislocation (new-leg sign == dislocation
  sign, |z|>2). NaN z -> 0. BNB -> 0 always.
- GATED (the single scored variant, max 1-bar delay, no queue):
  `ws_gate_c[T] = ws_base_c[T-1]` if `veto_c(T)==1 AND veto_c(T-1)==0`,
  else `ws_base_c[T]`. Per-coin independent; other coins unaffected. A
  vetoed flip executes at the latest one bar later (at T+1 the current
  BASE runs regardless of a fresh veto signal there — no stacking).
  First grid bar: `ws_gate = ws_base` (no prior).
- Net P&L per bar per variant (oc_bookvol harness):
  `TO[t] = sum_c |ws_c[t]-ws_c[t-1]|` (first grid bar vs flat 0, each
  variant's own turnover, so holds save turnover);
  `pn[t] = sum_c ws_c[t]*r_c[t] - 0.0005*TO[t]`; equity compounded from
  1.0. ANN = sqrt(6*365) = sqrt(2190).
- Anchor years `A_k = 2021-09-24 .. 2025-09-24` (UTC), partition
  `[A_k, A_{k+1})` k=0..3 plus `[A_4, A_4+365d)` (same as oc_bookvol;
  expected per-year scored bars 2190/2190/2196/2190/2189 minus the final
  dropped forward bar in the last year).
- Per (variant, year): return `= prod(1+pn)-1`; max DD on the year-rebased
  equity; Sharpe `= mean(pn)/std(pn,ddof=1)*ANN` (NaN if < 30 bars);
  daily sums grouped by UTC date of T; `worst_day` = min daily sum;
  `veto_rate` = share of (coin,bar) with veto==1; `flip_rate` likewise.
  Pooled-5y stats likewise (descriptive).

## Decision rule (assignment default + filter tail bar, fixed here)

Primary effect = drawdown reduction (the veto buys DD with turnover, per
IDEAS.md; return is expected small): `dDD_y = DD_BASE,y - DD_GATE,y`
(positive = gate draws down less). LOYO stability (threshold is fixed, so
LOYO is a stability check as in oc_bookvol/oc_idea9): `LOYO_h` passes iff
`sign(dDD_h) == sign(mean_{k!=h} dDD_k)` with that training mean `> 0`
(NaN -> fail). Worst-day guard:
`tail_ok_y = (worst_day_GATE,y >= worst_day_BASE,y)` (not worse).
Return/Sharpe/turnover/fire-rates are descriptive only (the gate is
expected to buy DD with flat-to-small return; a return gain without the
DD/tail bar is NOT PROMISING).

GATE is PROMISING iff ALL THREE hold: dDD > 0 in >= 4/5 years AND
LOYO-DD passes in >= 4/5 held-out years AND tail_ok in >= 4/5 years.
NaN counts as FAIL. One variant only (|z|>2, no threshold search, no
per-coin thresholds). One-line verdict in REPORT.md
(`PROMISING` / `NOT PROMISING`).

First-four-year (2021-2024) sensitivity is reported descriptively (repo
selection window) but is NOT part of the verdict.

## Causality / correctness tests (tests/test_oc_idea5.py)

- test_grid_and_base_matches_bookvol: grid size 10955 scored bars,
  per-year bar counts as above; BASE per-year ret/DD reproduce oc_bookvol
  V0 to 1e-6 (same books/math).
- test_premium_causal_truncate: sampled (coin,T): x/z recomputed from
  hourly+Coinbase truncated to START < T equal stored values; no used bar
  has START >= T; no bar with START >= 2026-09-24 used.
- test_z_window_strictly_before_T: z(T) unchanged when all x at/after T
  are perturbed; hand-check mean/std window bounds on one T.
- test_flip_veto_logic_synthetic: strict-reversal (zero never flips),
  INTO-sign rule at +-2.0 boundaries, NaN/BNB never veto, max-1-bar-delay
  (no consecutive holds) on a hand-built weight/z frame.
- test_year_partition_and_decision: 5 masks disjoint, cover scored bars
  once; verdict recomputed from results.json counters; turnover/cost >= 0.
- test_no_1m_and_cutoff: analysis script never references
  majors/btc/alts intraday 1m paths; max used hourly/Coinbase START
  < 2026-09-24 00:00 UTC.

## Deliverables

`research/tournament/oc_idea5/`: PLAN.md (this file),
`compute_idea5.py`, `results.json`, REPORT.md (tables + one-line
verdict). `tests/test_oc_idea5.py`. No commits, no edits outside these
two paths. One process, hourly data only, RAM < 1 GB. No tuning.

VF_COMMON note: `src/agentic_alpha_lab/patterns/common.py` was read. Its
compute/events/event_study contract targets BTC-bar feature studies; this
tournament screen follows the W assignment's book open-to-open replay
instead (forward_v205 books_d2 exact outcomes, 5 anchor years to
2026-09-24, oc_bookvol harness), while honouring the shared causality
principles: as-of availability (hourly START < T, windows ending before
t), pre-registered single threshold, and no reads beyond 2026-09-24.
