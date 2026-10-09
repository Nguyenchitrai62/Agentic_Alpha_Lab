# oc_b7c2pre — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_b7c2pre.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, docs/opencode/OPENCODE_VF_COMMON.md read in full).
Write ONLY `research/tournament/oc_b7c2pre/` + `tests/test_oc_b7c2pre.py`. Scratch only under
`research/tournament/oc_b7c2pre/tmp/` (never the system temp folder; never inspect /proc or
folders outside the workspace). GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/rm/
commit/switch/rebase/merge. Progress print every 10 minutes (heartbeat every 600 s in long loops).
Heavy 1m work (if any) via `scripts/heavy_slot.py` (RAM tight: one job at a time); replica +
placebo are CPU-only on the reused ledger (no heavy slot needed); stop-kind recompute is NOT
redone (frozen `stop_kinds.npz` reused read-only, so no 1m heavy step here).

## Why and the contamination label

`research/tournament/oc_b7c2` stacks B7 (dip budget x1.5 for 7d after a >4 sigma 4h move,
market-wide per shift) with C2 (rung x1.25/x0.75 by Chronos downside quantile risk=-ch_q10,
per-anchor fits) as a PRODUCT (and product capped at 1.5). On dev4 (2021-2024) the stack
underperforms standalone B7 (B7C2 mean 6.652/WORST 2.922 vs B7 6.738/2.955; cap weaker still),
so the robust dev4 pick is B7, not the stack. CONTAMINATION (pre-registered in oc_b7c2):
both components already scored the post-release year, so post-release numbers are labelled
diagnostics. THIS study is the unseen-years leg: pre-sample years 2017-2020, which nobody
looked at when the B7 idea was formed (see oc_cboostpre PLAN) and which Chronos/RV6/GARCH
never saw (see oc_presampletilt PLAN). No selection is made here; diagnostic only
(no engine, no adoption). C2 rule uses the EARLIEST frozen fit (anchor-2021) applied to
EARLIER years, hence labelled everywhere "fit from later data, rule frozen".

## Variants (exactly two stack + three reference/copies; nothing else)

- REF = base dip replica unchanged (mult 1), reproduction row only (copy gate, not rerun).
- B7 = COPY from oc_cboostpre (dip budget x1.5 for 7d after cascade bar, market-wide per
  shift, N=7). Not rerun here; numbers copied to the digit from
  `oc_cboostpre/results.json` + `tmp/stop_presample.json` (copy gate, else STOP).
- C2 = COPY from oc_presampletilt (rung x1.25/x0.75 outer quintiles of risk=-ch_q10,
  frozen anchor-2021 fit, missing/NaN->1). Not rerun here; numbers copied to the digit
  from `oc_presampletilt/results.json` (copy gate, else STOP).
- B7C2 = REF + BOTH multipliers applied as a PRODUCT (verbatim oc_b7c2):
  m(sym,T,shift) = m_B7(T,shift) * m_C2(sym,T).
- B7C2_cap = product CLIPPED: m = min(m_B7*m_C2, 1.5) (verbatim oc_b7c2 cap).
- Book untouched (presample replica has no book leg anyway; dip-only sizing overlay).
- Stack multisets (pre-registered, verbatim oc_b7c2): B7C2 in
  {0.75,1.0,1.125,1.25,1.5,1.875}; B7C2_cap in {0.75,1.0,1.125,1.25,1.5}
  (m_B7 in {1.0,1.5}, m_C2 in {0.75,1.0,1.25}).
- No other variant, no ensemble, no threshold/window tuning, no refit.

## Frozen inputs (read-only, never edited, never refit)

- `research/tournament/oc_presampletilt/tmp/ledger_presample.npz` +
  `oc_presampletilt/tmp/bt_presample.npy` (D0+B1 replica same as oc_k2placebo: RUNGS
  2.5/3/3.5/4/5, live 16..238 strict trade-through, w=1/(1+n) coins-present-only,
  outcome_mu TP 0.9/1.0/1.1 close5+backstop, gate costs inside, stop-first, kept iff
  y09/y10/y11 ALL finite; NO budget/cap; SPOT fills/exits, perp gate costs — spot-vs-perp
  caveat on every number). Reproduction gate: n == 9731, per-leg 909/2986/3115/2721, and
  base 4-phase-mean sums == (2.313362, 2.678870, 0.577643, 0.297538) +- 1e-6. If gate
  fails: STOP and report.
- `research/tournament/oc_cboostpre/boost_mult_presample.parquet` (shift,T,mult_B7;
  B7 col only used here; union triggers per shift, closes-only |r|>4*SIG(540,min120),
  tc=T+4h, window (tc,tc+7d] market-wide per shift — VERBATIM oc_cascadedelay/
  oc_cascadeboost, no recompute). B3 col ignored.
- `research/tournament/oc_presampletilt/chronos_features_presample.parquet`
  (sym,shift,T,ch_q10 + others; ch_q10 only used here; context = last 512 closes ending
  at bar closing at T).
- Frozen C2 anchor-2021 fit (verbatim oc_presampletilt tilt_rule.FROZEN_2021["C2"]):
  direction +1, q20 = 1.110054237503456, q80 = 2.8608138206510407, hi/lo = 1.25/0.75.
  Applied to ALL pre-sample years on all 4 shifts; labelled "fit from later data,
  rule frozen".
- `research/tournament/oc_cboostpre/results.json` (expected B7 copy numbers) +
  `oc_cboostpre/tmp/stop_presample.json` + `oc_cboostpre/tmp/stop_kinds.npz`
  (frozen per-fill exit kinds TP/time/stop/backstop/unknown at mu=1.0; 15 unknown;
  reused read-only for the stack stop-rate split; kinds never recomputed here).
- `research/tournament/oc_presampletilt/results.json` (expected C2 copy numbers).
- `research/tournament/oc_b7c2/stack_rule.py` (product/cap arithmetic copied verbatim;
  only the time grid changes from 5y anchors to 4 presample legs).
- `research/tournament/oc_presampletilt/bars_4h_presample.parquet` (decision-bar
  universe source for the stack placebo; close/open columns only for universe bounds).

## Mechanism (verbatim oc_b7c2 product, applied to the presample replica)

- Per pre-sample year y in (Y2017=[2017-10-16,2018-01-01), Y2018, Y2019,
  Y2020p=[2020-01-01,2020-09-01)): bars with open in the interval; exits may realise
  after. Coins/warm-up inherited via the ledger (Y2017 BTC+ETH only incl. warm-up;
  Y2018+ BTC/ETH/BNB + XRP from 2018-07-03; SOL absent). No re-filtering.
- Per fill join (phase=shift, T=bar open; coin mapping BTC/ETH/BNB/XRP=0/1/2/3):
  m_B7 = 1.5 iff boosted_B7(T,shift) else 1.0 (exact (shift,T) match on the frozen
  boost grid, fallback latest grid time <= T ffill causal, missing -> 1.0, same as
  oc_cboostpre mult_at); m_C2 = assign_mult(-ch_q10(sym,T), dir=+1, q20, q80, 1.25,
  0.75), missing/NaN -> 1.0 (same as oc_presampletilt, frozen 2021 fit applied to all
  years); m_B7C2 = m_B7*m_C2; m_cap = min(m_B7C2, 1.5).
- Replica sums per year (verbatim oc_k2placebo/oc_presampletilt `phase_mean_sums` with
  n_years=4 on ledger years 0..3): base(y) = mean_p sum(w*y10), tilted(y) = mean_p
  sum(w*mult*y10), realised_mean(y) = mean mult over fills in y, norm(y) =
  tilted(y)/realised_mean(y), gain_vs_base(y) = norm(y)-base(y),
  gain_vs_B7(y) = norm_stack(y)-norm_B7_copy(y), gain_vs_C2(y) = norm_stack(y)-
  norm_C2_copy(y). "Helps" in a year iff gain_vs_base(y) > 0. Report n fills too,
  plus boosted fill share (stack: mult>1 share; B7/C2 shares copied).

## Placebo (fixed; CPU-only, numpy)

- Timing placebo per year, PRIMARY, for EACH stack variant (B7C2, B7C2_cap): 1000
  uniform bar-level permutations of the variant's stack multipliers over that year's
  decision-bar universe (seed 20261007+y with y=0..3 for Y2017..Y2020p), normalised by
  the ACTUAL realised-mean denominator (constant denominator, verbatim predecessors);
  percentile = 100*(1+#{perm<=actual})/1001; significant iff >= 95.
- Decision-bar universe for the stack (pre-registered): (sym,shift,T) triples from
  `bars_4h_presample.parquet` with T in the year's [S_y,E_y) interval, restricted to
  warmed-up coins with finite bars (same coin-availability as the ledger: Y2017
  BTC/ETH only; Y2018+ BTC/ETH/BNB+XRP-from-2018-07-03; SOL absent). Stack mult per
  triple computed with the SAME frozen join as fills (m_B7 ffill-causal x m_C2
  frozen-2021, missing->1). Fills map to their triple; fills with no triple (gapped
  bars; none expected) map to a mult-1.0 bar if present else counted as missing and
  disclosed (never imputed with a non-1 mult).
- Rationale (disclosed): the product varies per (sym,shift,T) (B7 market-wide x C2
  per-coin), so the bar-level null is the correct JOINT null: it preserves the
  per-year stack-mult distribution while breaking both WHEN (B7) and WHICH (C2)
  timing. Time-bar-only permutation would break the pre-registered per-coin sharing
  of the product. B7/C2 timing pcts are COPIES (not recomputed).
- Block placebo per year: 42-bar chronological blocks per (sym,shift) permuted within
  the year (seed 20261008+y; preserves window-length structure up to block edges).
  Same normalisation/percentile/significance. B7/C2 block pcts are COPIES.

## Crash risk (fixed; stop-hit share of boosted fills vs base rate; no 1m recompute)

- Kinds REUSED read-only from `oc_cboostpre/tmp/stop_kinds.npz` (verbatim
  build_ledger_presample.outcome_mu kind branch at mu=1.0; stop-first; same 9731 fills
  in ledger order; 15 unknown). "Hit the stop" = kind in {stop,backstop}. Base rate =
  stop-hit share over known fills in the year (copy gate vs cboostpre stop table).
- Stack boosted rate = stop-hit share over known fills in the year with stack mult >
  1.0 (net-boosted; uncapped set {1.125,1.25,1.5,1.875}, capped {1.125,1.25,1.5});
  report delta (boosted - base) per year + pooled, plus boosted share. Also report TP
  share as a secondary row (same split) and the de-boosted (mult<1, i.e. 0.75) stop
  rate for context. B7/C2 boosted stop rates are COPIES. Unknown kinds excluded from
  rates only (counted and disclosed). COVID leg Y2020p reported separately in every
  stop row (does C2 reduce B7's crash-leg damage there = stack Y2020p boosted-stop
  delta vs B7 Y2020p boosted-stop delta).

## No fits (nothing estimated)

Threshold 4.0, windows (540/120), boost 1.5, N=7 (B3=3 ignored), hi/lo 1.25/0.75,
C2 q20/q80 above, seeds (20261007+y / 20261008+y), BLOCK 42 are all frozen ex-ante
round numbers/inherited conventions, never scanned. No harness join, no quantiles
fit here, no embargo beyond strict causality (B7 trigger at tc uses only closes with
close_time <= tc; C2 forecast for T uses only 512 closes of bars closing <= T).
No statistic from any test year feeds any choice. Pre-sample years were never used
for any fit anywhere in this program (the boost rule has no fits; the C2 fit comes
from LATER data and is labelled as such).

## Metrics / verdict (fixed)

- Table per pre-sample year x {REF(base copy), B7(copy), C2(copy), B7C2, B7C2_cap}:
  n fills, base, tilted/boosted, realised mean, norm, gain_vs_base, gain_vs_B7,
  gain_vs_C2 (stack rows only), timing pct, block pct, boosted fill share.
- Stop table per year x {base, B7 copy, C2 copy-context, B7C2, B7C2_cap}: boosted
  share, boosted stop rate, delta vs base (+ TP secondary, de-boosted context).
- COVID leg Y2020p highlighted separately in every table + pooled full vs pooled
  ex-COVID (Y2017-2019) for the helps-count question.
- Counts: helps (gain_vs_base>0) over 4 years per stack variant; timing-significant
  (>=95) count; gain_vs_B7>0 count and gain_vs_C2>0 count (does the stack beat each
  leg alone?); Y2020p row quoted verbatim.
- Verdict (Vietnamese, 3 lines in REPORT.md): does the stack help on unseen years
  (vs no tilt / vs B7 alone / vs C2 alone) and does C2 reduce B7's crash-leg damage
  there (Y2020p boosted-stop delta stack vs B7)? Adopt/reject/needs-prospective label
  (no engine adoption here; diagnostic only).
- Gate costs: inside the reused replica outcomes (maker 0.0002/taker 0.00055, adverse
  long funding 0.0001/8h); the stack is a sizing-only overlay with no extra cost.
  Spot-vs-perp caveat on every number (SPOT fills/exits, perp gate costs).

## Leakage / checks (stated in REPORT)

- Feature timing (B7 triggers: closes with close_time <= tc only; SIG window excludes
  the tested bar; boost window strictly after tc (0 < T-tc <= 7d); C2 forecast for T
  uses only 512 closes of bars closing <= T; stack lookup uses only (sym,shift,T) at
  the holding bar; truncation-tested in tests/test_oc_b7c2pre.py: recompute stack
  mults from truncated frozen tables -> identical on kept prefix; multiset check),
  label windows (no labels fit anywhere in this study), fit windows (B7: no fits;
  C2: frozen anchor-2021 fit + 7d embargo inherited, applied to earlier years and
  labelled; no statistic from any test year feeds any choice), fill timing (live
  16..238 strict trade-through + stop-first inherited; perms reassign mults within
  the year only). Gate costs inside the reused replica outcomes. Coverage: disclose
  any skipped year / missing-mult count / unknown-kind count (none expected beyond
  the frozen 15 unknown + C2 burn-in/context missing->1 counts).

## Compute plan (resume-safe, heartbeat every 600 s)

- `stack_rule.py`: pure helpers (`assign_c2` verbatim oc_b7c2/oc_presampletilt,
  `stack_mult`, `stack_mult_cap`, `variant_mult_c2`) — no data access; unit-tested.
  (Product/cap arithmetic VERBATIM oc_b7c2 `stack_rule.py`; C2 thresholds verbatim
  oc_presampletilt FROZEN_2021["C2"].)
- `compute_stack_presample.py`: CPU-only join to the reused ledger + per-year
  sums/gains (vs base/B7-copy/C2-copy) + 1000-perm timing/block placebos (bar-level
  within-year permutation as above) for B7C2 + B7C2_cap -> `tmp/stack_presample.json`
  (copy gates asserted BEFORE scoring the stack; heartbeat every 600 s; progress
  print every 10 min).
- `compute_stop_stack.py`: CPU-only (no 1m; frozen kinds read-only) stack
  boosted/de-boosted stop/TP splits per year + pooled (+ ex-COVID pooled) ->
  `tmp/stop_stack.json` (copy gates on base/B7 stop rates vs frozen stop table).
- `analyze_stack.py` (small CPU-only writer): `results.json` + `REPORT.md` tables
  (REPORT written from tables only; B7/C2 rows copied from frozen sources, asserted
  equal).
- Deliverables: PLAN.md (this file), stack_rule.py, compute_stack_presample.py,
  compute_stop_stack.py, analyze_stack.py, tmp/*.json, results.json, REPORT.md,
  tests/test_oc_b7c2pre.py (>=1 causality/truncation test + >=1 hand-checked
  synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_b7c2pre.py -q`).
- No 4-phase engine in this study (diagnostic only). No selection on any year.

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the original row
  stays and the change is a disclosed extra row).
