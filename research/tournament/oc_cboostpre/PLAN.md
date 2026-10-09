# oc_cboostpre — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_cboostpre.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, docs/opencode/OPENCODE_VF_COMMON.md read in full).
Write ONLY `research/tournament/oc_cboostpre/` + `tests/test_oc_cboostpre.py`. Scratch only under
`research/tournament/oc_cboostpre/tmp/` (never the system temp folder; never inspect /proc or
folders outside the workspace). GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/rm/
commit/switch/rebase/merge. Progress print every 10 minutes (heartbeat every 600 s in long loops).
Heavy 1m work (crash-risk recompute) via `scripts/heavy_slot.py` (RAM tight: one engine job at a
time, one coin's 1m slice in RAM at a time, float32 where possible); trigger build + replica +
placebo are CPU-only on 4h closes (no heavy slot needed).

## Why and the contamination label

`research/tournament/oc_cascadeboost`: B7 = dip budget x1.5 for 7 days after a cascade bar
(> 4 sigma 4h close-to-close move, definition of oc_cascadedelay) is the dev4 robust pick
(mean 6.74 / WORST 2.96 / DD 17.92 vs G2 5.60 / 2.59 / 16.91; 5y 6.36). CONTAMINATION (stated in
the assignment and repeated here BEFORE any outcome): the idea was formed AFTER
oc_cascadedelay's replica had covered all five years incl. the post-release year, so
post-release numbers are labelled diagnostics and new evidence must come from controls, unseen
years, frictions and prospective paper. THIS study is the unseen-years leg: pre-sample years
2017-2020, which nobody looked at when the idea was formed. No selection is made here;
diagnostic only (no engine, no adoption).

## Variants (exactly two + reference; nothing else)

- REF = base dip replica unchanged (mult 1), reproduction row only.
- B7 = dip budget x1.5 for 7 days after a cascade bar (mult 1.5 in window else 1.0).
- B3 = dip budget x1.5 for 3 days after a cascade bar (mult 1.5 in window else 1.0).
- Book untouched (dip-only sizing overlay; presample replica has no book leg anyway).
- No other variant, no ensemble, no threshold/window tuning, no refit.

## Cascade trigger + boost window (frozen, causal, VERBATIM oc_cascadedelay/oc_cascadeboost arithmetic, applied to pre-sample 4h closes — no new data)

- Source (read-only): `research/tournament/oc_presampletilt/bars_4h_presample.parquet`
  (4 syms BTCUSDT/ETHUSDT/BNBUSDT/XRPUSDT x shifts 0..3, ORIGIN 2020-01-01 + s h grid;
  per (sym, shift) series sorted by T = bar open). Only the `close` column is used.
  SOL absent pre-sample (no series; union over available majors only — disclosed).
- "range > 4sg" reading (frozen, inherited): "range" = absolute close-to-close log move
  |r[i]| with r[i] = ln(C[i]/C[i-1]) (r[0] = NaN). REJECTED alternative: (H-L)-based range.
- Sigma (frozen): SIG[i] = std(ddof=1) of r[i-540 .. i-1] (540 returns = 90d x 6 bars/day),
  min_periods 120 (else NaN). SIG[i] uses only bars with close_time <= T[i]; the tested
  return r[i] resolves at close_time[i] = T[i]+4h and is NEVER in its own sigma window —
  causal by construction, no self-inclusion.
- TRIGGER: bar i of (sym, shift) fires iff SIG[i] finite > 0 AND |r[i]| > 4.0 * SIG[i]
  (strictly greater; 4.0 frozen). Trigger close time tc = T[i] + 4h (known at tc).
  NaN SIG or non-finite closes -> never fires (conservative; counted and disclosed).
- BOOST WINDOW (market-wide per shift, frozen): a dip decision at holding-bar open T on
  shift s is BOOSTED iff there EXISTS a trigger (ANY available major, same shift s) with
  0 < T - tc <= N days (strictly after the trigger close, up to and including +N days).
  Same boosted(T, s) for all coins (the sleeve budget is global). REJECTED alternative:
  per-coin triggers — disclosed (inherited). On the 4h grid T in (tc, tc+Nd].
- MULT: boosted -> 1.5, else 1.0. Missing trigger history (T before first computable bar)
  -> 1.0 (never boosted; inert — disclosed with counts).
- Output: `boost_mult_presample.parquet` (shift, T, boosted_B7, boosted_B3, mult_B7,
  mult_B3; T range = union of pre-sample shift grids 2017-08-17..2020-09-30).
- Unit-tested: hand-checked synthetic trigger/sigma/boost arithmetic + causality/
  truncation test (recompute from bars truncated at a cut date -> identical on kept prefix).
- If the data named does not cover a pre-sample year: disclose and skip that year for that
  variant (never impute). None expected (closes from 2017-08-17; early bars have NaN SIG
  and never fire — counted, not imputed).

## Pre-sample years + ledger (fixed, inherited VERBATIM from oc_presampletilt)

- Years (bars with open in the interval; exits may realise after):
  Y2017 = [2017-10-16, 2018-01-01), Y2018 = [2018-01-01, 2019-01-01),
  Y2019 = [2019-01-01, 2020-01-01), Y2020p = [2020-01-01, 2020-09-01).
  Coins/warm-up inherited via the ledger (Y2017 BTC+ETH only incl. warm-up; Y2018+ BTC/ETH/
  BNB + XRP from 2018-07-03; SOL absent). No re-filtering here.
- Ledger (read-only, never edited, never rebuilt): `oc_presampletilt/tmp/ledger_presample.npz`
  + `oc_presampletilt/tmp/bt_presample.npy` (D0+B1 replica same as oc_k2placebo: RUNGS
  2.5/3/3.5/4/5, live 16..238 strict trade-through, w=1/(1+n) coins-present-only,
  outcome_mu TP 0.9/1.0/1.1 close5+backstop, gate costs inside, stop-first, kept iff
  y09/y10/y11 ALL finite; NO budget/cap; SPOT fills/exits, perp gate costs — spot-vs-perp
  caveat on every number). Reproduction gate: n == 9731, per-leg 909/2986/3115/2721, and
  base 4-phase-mean sums == (2.313362, 2.678870, 0.577643, 0.297538) +- 1e-6 (copied from
  `oc_presampletilt/results.json` presample V_RV6 per_year base — variant-independent).
  If the gate fails: STOP and report.
- Per fill join (phase=shift, T=bar open; coin mapping BTC/ETH/BNB/XRP = 0/1/2/3 inherited):
  exact match on the shift grid, fallback to latest grid time <= T (ffill, causal);
  missing -> 1.0 (counted and disclosed).

## Replica + placebo (fixed; CPU-only, no engine)

- Per pre-sample year y (4-phase means, same `phase_mean_sums` as k2placebo/voltilt/chronos/
  cascadedelay/cascadeboost with n_years=4 on ledger year 0..3): base(y), boosted_B7(y),
  boosted_B3(y), realised_mean(y) (mean mult over fills in y), norm(y) = boosted(y)/
  realised_mean(y), gain(y) = norm(y) - base(y). "Helps" in a year iff gain(y) > 0.
  Report n fills too, plus boosted fill share.
- Timing placebo per year (primary, pre-registered adaptation for a MARKET-WIDE rule,
  inherited verbatim from oc_cascadeboost): bar universe per (year y, shift s) = time-bars
  (s, T) on that shift's pre-sample grid with T in the year's [S_y, E_y) interval; mult
  series per (y, s) permuted uniformly WITHIN (y, s) (1000 perms, seed 20261007+y with
  y = 0..3 for Y2017..Y2020p; preserves per-shift boosted counts and the cross-sym sharing);
  fills map to their (y, s) time-bar. Percentile = 100*(1+#{perm<=actual})/1001;
  significant iff >= 95; perm norms use the ACTUAL realised-mean denominator. Rationale
  (disclosed, inherited): permuting over (sym,shift,T) triples would break the pre-registered
  market-wide sharing (all syms share one mult per time-bar); time-bar permutation within
  (year, shift) is the correct null. The assignment's "1000 permutations of the boost windows
  within the year, same count and length" is satisfied by this null (same boosted count per
  (y,s)) plus the block variant below (same window lengths); disclosed.
- Block placebo per year: 42-bar chronological blocks per (y, s), permuted within (y, s)
  (seed 20261008+y; preserves window-length structure up to block edges). Same
  normalisation/percentile/significance.
- No gate here (diagnostic only): report helps-count (gain>0) and timing-significant count
  over the 4 pre-sample years per variant; no selection, no engine adoption.

## Crash risk (fixed; stop-hit share of boosted fills vs base rate)

- The presample ledger stores no exit reason, so exit kinds are recomputed per fill from the
  read-only spot 1m store (`data/raw/spot_1m_presample_20261007`, one coin in RAM at a time,
  float32) with VERBATIM `build_ledger_presample.outcome_mu` logic at mu=1.0 (sl = lv*(1-4*sg),
  bl = lv*(1-8*sg), tp = lv*(1+1.0*sg); close5 4sg stop + 8sg backstop + TP + timeout at next
  4h open; stop-first ordering backstop > tp > stop). "Hit the stop" = kind in
  {stop, backstop} (close5 stop or backstop; timeout/TP otherwise). Base rate = stop-hit
  share over all fills in the year; boosted rate = stop-hit share over boosted fills in the
  year (per variant B7/B3); report delta (boosted - base) per year + pooled. Also report TP
  share as a secondary row (same split).
- Levels: lv = O(T)*(1-k*sg(T)), k from ledger rung {2.5,3,3.5,4,5}; O/sg from
  `bars_4h_presample` (open + `compute_sigma` = pct_change rolling-360 min_periods-120
  shift-1 on opens, VERBATIM `build_ledger_presample.compute_sigma`). DISCLOSED CAVEAT:
  the ledger's O/sg were sampled as 1m-open-at-T on its own grid while this recompute uses
  the frozen bars open series; the two agree whenever minute T is present (dense store) but
  may differ on gapped bars — the recompute is a like-for-like diagnostic, not a ledger
  rewrite; fills are never added/dropped (same 9731 fills; kinds only).
- Fill windows: same live 16..238 strict low trade-through (`find_fill` verbatim); NaN 1m
  gaps never fill/trigger/exit (inherited). If a fill's window cannot be rebuilt (missing
  1m): count it as unknown and disclose (never impute a kind; rates over known kinds only).

## No fits (nothing estimated)

Threshold 4.0, windows (540/120), boost 1.5, N = 7/3, seeds (20261007+y / 20261008+y),
BLOCK 42 are all frozen ex-ante round numbers/inherited conventions, never scanned. No harness
join, no quantiles, no embargo beyond strict causality (trigger at tc uses only closes with
close_time <= tc). No statistic from any test year feeds any choice. Pre-sample years were
never used for any fit anywhere in this program (the boost rule has no fits at all).

## Leakage / checks (stated in REPORT)

- Feature timing (triggers: closes with close_time <= tc only; sigma window excludes the
  tested bar; boost window strictly after tc; truncation-tested in
  tests/test_oc_cboostpre.py), label windows (no labels fit anywhere in this study),
  fit windows (no fits; frozen threshold/windows/N/boost, no statistic from any test year
  feeds any choice), fill timing (live 16..238 strict trade-through + stop-first inherited;
  perms reassign mults within (year, shift) only). Gate costs inside the reused replica
  outcomes. Coverage: disclose any skipped year / missing-mult count / unknown-kind count
  (none expected).

## Compute plan (resume-safe, heartbeat every 600 s)

- `cboostpre_rule.py`: pure helpers (`close_returns`, `trailing_sigma`, `triggers_of`,
  `boosted_mask`, `compute_sigma`, `find_fill`, `outcome_kind`) — no data access;
  unit-tested. (Trigger arithmetic VERBATIM oc_cascadedelay `delay_rule.py` /
  oc_cascadeboost `boost_rule.py` with BOOST = 1.5, B7_DAYS = 7, B3_DAYS = 3; outcome
  logic VERBATIM `build_ledger_presample.outcome_mu` kind branch.)
- `build_boost_presample.py`: CPU-only pre-sample 4h closes -> `boost_mult_presample.parquet`
  + trigger counts per (year, shift) + boosted shares (fast; prints progress).
- `compute_boost_presample.py`: CPU-only join to the reused ledger + per-year sums/gains +
  1000-perm timing/block placebos (time-bar within-(year,shift) permutation) for B7 + B3 ->
  `tmp/boost_presample.json` (heartbeat every 600 s).
- `compute_stop_presample.py`: spot-1m kind recompute, one coin at a time (via heavy_slot) ->
  `tmp/stop_presample.json` (per-fill kinds + per-year base/boosted stop rates; heartbeat).
- `analyze_presample.py` (folded into compute scripts where trivial; otherwise a small
  CPU-only writer): `results.json` + `REPORT.md` tables (REPORT written from tables only).
- Deliverables: PLAN.md (this file), cboostpre_rule.py, build_boost_presample.py,
  compute_boost_presample.py, compute_stop_presample.py, boost_mult_presample.parquet,
  tmp/*.json, results.json, REPORT.md, tests/test_oc_cboostpre.py (>=1 causality/
  truncation test + >=1 hand-checked synthetic case;
  `.venv/Scripts/python.exe -m pytest tests/test_oc_cboostpre.py -q`).
- No 4-phase engine in this study (diagnostic only). No selection on any year.

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the original row
  stays and the change is a disclosed extra row).
