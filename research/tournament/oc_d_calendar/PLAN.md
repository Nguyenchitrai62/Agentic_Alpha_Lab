# oc_d_calendar — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_d_calendar.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md, `docs/opencode/IDEAS12_20261008.md` idea #4 read in full).
Write ONLY `research/tournament/oc_d_calendar/` + `tests/test_oc_d_calendar.py`. No other file is
edited (registry, ledgers, CONTINUOUS_RESEARCH.md, NEXT_AGENT.md, docs/ except nothing,
bot/, backend/, scripts/, other workers' folders, ../Kronos, git state untouched;
GIT READ-ONLY: never stash/reset/checkout/restore/clean/rm/commit/switch/rebase/merge).
Scratch only under `research/tournament/oc_d_calendar/tmp/`. Progress print every 10 min
(heartbeat every 600 s in long loops). Heavy 1m work (stop-kind recompute; any engine)
via `scripts/heavy_slot.py` (RAM tight: one job at a time, one coin's 1m slice in RAM
at a time, float32 where possible); replica joins + placebos are CPU-only.
Long jobs: nohup + log file under tmp/; never inspect /proc or folders outside the workspace.

## Idea #4 EXACTLY as written (IDEAS12 §4)

Mech: makers quote but don't commit size in thin books (two-regime recovery lit: depth
stuck 66-79% weeks after spreads normalize); weekend/Asian flushes overshoot on air and
snap back on normal flow. Calendar = zero-fit trigger (stationary rates by construction).

Rule: V1 Sat/Sun-UTC signal bars dip x1.25 else x1.0; V2 00-08 UTC bars x1.2 else x1.0
(frozen UTC windows) + constant-mult control for the exposure shift. No fit.

Data/harness: timestamps only; replica PRIMARY, engine + control SECONDARY.
Effect: +0.0-0.05%/mo, DD flat. Prior 7%.

Crash: no interaction by construction (COVID crash 2020-03-12 was a Thursday; Terra/Luna
spanned weeks — disclosed); cap kept.

Closest CLOSED: oc_seasondepth (hour-of-week SIGMA-SCALE, sum 1/5 — this is SIZE) /
oc_weekend book-flat (P&L 0/5, different leg) / oc_lit_calendar (book gates, different leg).

## Frozen variants (ONLY these two + reference, no tuning, no refit)

- REF = base dip replica unchanged (mult 1.0), reproduction row only.
- V1: per decision bar open T (UTC): mult 1.25 iff T.weekday() in (5, 6) (Saturday/Sunday
  UTC), else 1.0. Market-wide per (shift, T): same mult for all coins at the same time-bar.
- V2: per decision bar open T (UTC): mult 1.2 iff 0 <= T.hour < 8 (00-08 UTC), else 1.0.
  Market-wide per (shift, T), same for all coins.
- Mults 1.25 / 1.2 / 1.0, windows (Sat/Sun, 00-08 UTC) are frozen ex-ante round numbers from
  IDEAS12, never scanned. No book leg (dip-only sizing overlay; presample replica has no
  book leg anyway). No other variant, no ensemble, no refit.
- "Signal bar" = the dip decision holding-bar open T (the bar whose open timestamps the
  rung decision). T is read in UTC; no timezone conversion, no DST.
- Constant-mult control for the exposure shift: in the replica, norm(y) divides by the
  realised mean mult (exposure-matched by construction, same as all replica gates); the
  tradable constant-mult control CTRL_C is engine-stage only (per-year constant = the
  candidate's realised mean dip-budget multiplier in that year; non-tradable decomposition
  control, labelled; never feeds any tradable choice).

## Calendar trigger (frozen, causal, timestamps-only, no fit)

- Source: timestamps only. Pre-sample grid from read-only
  `research/tournament/oc_presampletilt/bars_4h_presample.parquet` (4 syms
  BTCUSDT/ETHUSDT/BNBUSDT/XRPUSDT x shifts 0..3, ORIGIN 2020-01-01 + s h grid; only the
  `T` column is used — no price is read for the trigger); 2021-2026 grid from read-only
  `research/tournament/oc_kronoshidden/bars_4h_4shift.parquet` (5 majors x shifts 0..3;
  only `T` used). No other column is read for the trigger.
- V1(T) = 1.25 if Saturday/Sunday UTC else 1.0. V2(T) = 1.2 if 00<=hour<8 UTC else 1.0.
  Missing/NaT T -> 1.0 (never boosted; inert — counted, none expected).
- Output: `calendar_mult_presample.parquet` (shift, T, mult_V1, mult_V2 on the pre-sample
  grid) + `calendar_mult_2021.parquet` (same on the 2021-2026 grid). T ranges = union of
  the respective shift grids. Mults in {1.0, 1.25} (V1) / {1.0, 1.2} (V2); per time-bar
  (market-wide: every coin shares one mult per (shift, T) — disclosed difference vs
  DD-rank per-coin mults, same sharing as B7 market-wide).
- Unit-tested: hand-checked synthetic weekday/hour/mult arithmetic + causality/truncation
  test (recompute from bars truncated at a cut date -> identical mults on kept prefix).
- Causality is by construction (T's own calendar fields are known at T; no lookahead —
  the trigger uses nothing but the decision time itself).

## Pre-sample years + ledger (fixed, inherited VERBATIM from oc_presampletilt/oc_cboostpre)

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
  `oc_presampletilt/results.json` / `oc_cboostpre/results.json` reproduction). If the gate
  fails: STOP and report.
- Per fill join (phase=shift, T=bar open; coin mapping BTC/ETH/BNB/XRP = 0/1/2/3 inherited):
  exact match on the (shift, T) mult panel, fallback to latest grid time <= T
  (ffill, causal); missing -> 1.0 (counted and disclosed).

## Replica + placebo (fixed; CPU-only joins, no engine)

- Per pre-sample year y (4-phase means, same `phase_mean_sums` as k2placebo/voltilt/chronos/
  cascadedelay/cascadeboost/cboostpre with n_years=4 on ledger year 0..3): base(y),
  tilted_V1(y), tilted_V2(y), realised_mean(y) (mean mult over fills in y),
  norm(y) = tilted(y)/realised_mean(y), gain(y) = norm(y) - base(y). "Helps" in a year
  iff gain(y) > 0. Report n fills too, plus boosted (hi-mult) fill share.
  dSum_pre = sum gains over 4 pre-sample years (diagnostic; the +0.273 gate is the
  2021-2026 secondary gate, not applied to pre-sample).
- Timing placebo per year (PRIMARY null: this IS a timing rule — calendar windows place
  extra size at specific times): time-bar permutation WITHIN (year, shift) — the mult
  series per (y, s) is permuted uniformly over that (y, s)'s time-bars (1000 perms, seed
  20261007+y with y = 0..3 for Y2017..Y2020p; preserves per-shift boosted counts and the
  market-wide cross-sym sharing; fills map to their (y, s) time-bar). Perm norms use the
  ACTUAL realised-mean denominator. Percentile = 100*(1+#{perm<=actual})/1001; significant
  iff >= 95. This null satisfies the assignment's "timing placebo pct where the idea is a
  timing rule" and "same count and length" per (y, s) (same boosted count) plus the block
  variant below (same window lengths up to block edges); disclosed. Inherited verbatim from
  oc_cboostpre (market-wide rule null); REJECTED alternative: permuting over
  (sym,shift,T) triples would break the pre-registered market-wide sharing — disclosed.
- Block placebo per year: 42-bar chronological blocks per (y, s), permuted within (y, s)
  (seed 20261008+y; preserves window-length structure up to block edges). Same
  normalisation/percentile/significance. (No rank-shuffle: the rule is not cross-sectional;
  every coin shares one mult per time-bar, so there is nothing to shuffle across coins.)
- PRIMARY pass (pre-registered): gain > 0 in >= 3/4 pre-sample years AND Y2020p (COVID leg)
  gain > 0 (must survive the COVID leg) AND pooled boosted stop-rate delta <= +1pp (see
  crash section). Timing significance is REPORTED per year but does not gate beyond the
  gains/stop checks (disclosed). If PRIMARY fails for both variants: SECONDARY replica is
  still computed (cheap) for completeness, but ENGINE is only for a variant that helps on
  the pre-sample AND passes the secondary gate.
- Round-trip ~4-8 bps bounds all effects (stated in REPORT).

## Crash risk (fixed; stop-hit share of boosted fills vs base rate)

- The presample ledger stores no exit reason, so exit kinds are recomputed per fill from the
  read-only spot 1m store (`data/raw/spot_1m_presample_20261007`, one coin in RAM at a time,
  float32) with VERBATIM `build_ledger_presample.outcome_mu` logic at mu=1.0 (sl = lv*(1-4*sg),
  bl = lv*(1-8*sg), tp = lv*(1+1.0*sg); close5 4sg stop + 8sg backstop + TP + timeout at next
  4h open; stop-first ordering backstop > tp > stop). "Hit the stop" = kind in
  {stop, backstop}. Base rate = stop-hit share over all fills in the year; boosted rate =
  stop-hit share over hi-mult fills (V1: mult==1.25; V2: mult==1.2); rest rate = stop-hit
  share over mult==1.0 fills ("skipped"/non-boosted); report delta (boosted - base) per year
  + pooled. Also report TP share as a secondary row (same split). FAIL if pooled boosted
  stop-given-fill rises > +1pp (b7breaker standard, pre-registered; same as oc_d_ddrank).
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
- COVID leg separately: Y2020p stop deltas reported on their own row; Y2020p gain must be
  > 0 (survival) per PRIMARY pass above. The 2020-03-12 crash was a Thursday (V1-neutral
  by construction) — disclosed per IDEAS12; Terra/Luna spanned weeks — disclosed.

## SECONDARY: 2021-2026 replica gate (fixed; CPU-only, no engine)

- Ledger (read-only, never edited, never rebuilt): `oc_k2placebo/tmp/ledger.npz` +
  `oc_k2placebo/tmp/bt_all.npy` (oc_placebo_dip D0+B1 4-phase replica, 5 anchor years
  2021-09-24..2026-09-23; RUNGS 2.5-5, live 16..238 strict trade-through, B1 w=1/(1+n),
  gate costs inside, stop-first). Reproduction gate: n == 22312 and base 4-phase-mean
  sums == (0.911273, 0.832599, 2.099814, 3.197390, 0.677229), sum5y == 7.718304 +- 0.002
  (copied from `oc_k2placebo/results.json`). If the gate fails: STOP and report.
- Mults: `calendar_mult_2021.parquet` built from `bars_4h_4shift.parquet` grid timestamps
  with the FROZEN weekday/hour rule above (5 majors share one mult per (shift, T)).
  Join (shift=phase, T=bar open) exact + causal ffill fallback; missing -> 1.0 (counted).
- Per year y = 0..4 (anchors 2021..2025-09-24, year = [A_y, A_{y+1}), A_5 = 2026-09-24):
  base(y), tilted(y), realised_mean(y), norm(y) = tilted(y)/realised_mean(y),
  gain(y) = norm(y) - base(y). dSum5y = sum gains over 5 years. sum-half = count gain>0
  (HELP in >= 4/5 required). SECONDARY pass (pre-registered): dSum5y >= +0.273 AND
  sum-half >= 4/5 (assignment: "dSum5y >= +0.273 and sum-half >= 4/5"). Timing / block
  placebos reported per year (same time-bar within-(y,s) nulls, seeds + y = 0..4: timing
  20261007+y, block 20261008+y) but do not gate beyond the dSum/sum-half rule (disclosed).
- Exposure note: norm(y) already divides by the realised mean mult (exposure-matched by
  construction, same as all replica gates); the constant-mult control is engine-stage only.

## ENGINE (only for a variant that helps on the pre-sample AND passes the secondary gate)

- If and only if a variant achieves PRIMARY pass AND SECONDARY pass, run the 4-phase engine
  vs G2 for that variant (+ REF + exposure-matched constant control + Bybit S5 row):
  - REF reproduction gate first: v421 R2B1D17BFG2 dev4 robust pick 5.41 %/month 4-phase reset
    metric, max yearly DD 16.91, full-path DD 16.82 (assignment: "reproduce 5.41 / 16.91 /
    16.82 first"; COMMON header: 5.41 %/mo reset, max yearly DD 16.91, full-path DD 16.82;
    hourly equity in `v421/v421_runs.pkl`; overlay A(t) = A(t-1)(1+r_bot(t)) + dSleeve(t));
    reset metric `research/diagnostics/r2_decompose5/reset_metric.py`; full-path DD via
    `v388.mix`). If the gate fails: STOP and report.
  - Candidate leg: dip rung size x calendar mult(T, shift) (book byte-identical to G2;
    G2 dip gross cap 2.0 and every other G2 limit bind enforced inside the engine; gate costs
    maker 0.0002/taker 0.00055/stop-taker, longs pay 0.0001/8h, shorts 0; limit fill only on
    1m trade-through; nothing in first 5 min after a 4h close (win_start=5); stop-first).
    Mechanism = exact copy of oc_cboostctrl/run_engine.py (= oc_cascadeboost = v414 pipe v321,
    corr-aware inv sizes kd=1.7, bear books, risk budget 0.26*1*1.7, sleeve_gross_cap 2.0).
  - Exposure-matched constant control: CTRL_C = constant dip-budget multiplier per anchor year
    = candidate's realised mean dip-budget multiplier in that year from the candidate's own
    engine run (same average exposure, no calendar timing; non-tradable decomposition control
    by construction, labelled; never feeds any tradable choice). Share split
    exposure = (CTRL-REF)/(CAND-REF), timing = (CAND-CTRL)/(CAND-REF) when CAND > REF.
  - Bybit S5 leg: price-source switch only (Bybit 1m from 2021-11-15; y2021 short window);
    same candidate vs REF on Bybit-S5 dev4 under the robust rule (DD<=20, no losing dev year,
    then highest WORST, ties->mean) AND full-path DD<=20 (oc_confirmgate Leg1 definition).
  - Stages: dev [2021-09-24, 2025-09-24) for selection (robust rule on dev4 ONLY), last year
    2025-09-24..2026-09-23 scored ONCE for the pick AND REF only (labelled). 5y + full-path DD
    reported. If PRIMARY or SECONDARY fails: NO ENGINE (valid negative result; REPORT states
    which gate failed and stops — no engine claim).
- Candidate-credibility checks (applied in REPORT): (1) sign-stable / fit-free rule (this rule
  has NO fits, NO thresholds on returns — timestamps only, frozen UTC windows; passes by
  construction); (2) beats the exposure control (CAND > CTRL_C on dev4 mean, else the gain is
  exposure); (3) Bybit leg (must not lose robustly / DD-breach on S5); (4) pre-sample leg
  (PRIMARY pass above). All four must hold to adopt; else REJECT / needs-prospective.

## Leakage / checks (stated in REPORT)

- Feature timing (calendar: the decision time's own weekday/hour only, known at T; uses no
  price and no future bar; truncation-tested in tests/test_oc_d_calendar.py), label windows
  (no labels fit anywhere), fit windows (no fits; Sat/Sun, 00-08 UTC, 1.25/1.2, seeds
  20261007/20261008, BLOCK 42 all frozen ex-ante, never scanned; no statistic from any test
  year feeds any choice; pre-sample years never used for any fit), fill timing (live 16..238
  strict trade-through + stop-first inherited; perms reassign mults within (year, shift)
  only). Gate costs inside the reused replica outcomes (maker 0.0002/taker 0.00055, adverse
  long funding 0.0001/8h). Coverage: disclose any skipped year / missing-mult count /
  unknown-kind count. Spot-vs-perp caveat on every pre-sample number (SPOT fills/exits, perp
  gate costs).

## Compute plan (resume-safe, heartbeat every 600 s)

- `calendar_rule.py`: pure helpers (`mult_V1`, `mult_V2`, `mult_at`, `compute_sigma`,
  `find_fill`, `outcome_kind`, `phase_mean_sums`) — no data access; unit-tested.
- `build_calendar_presample.py`: CPU-only pre-sample grid timestamps ->
  `calendar_mult_presample.parquet` + boosted time-bar/fill shares (fast; prints progress).
- `compute_calendar_presample.py`: CPU-only join to the reused presample ledger + per-year
  sums/gains + 1000-perm timing/block placebos per (y,s) (V1 + V2) -> `tmp/calendar_presample.json`
  (heartbeat every 600 s).
- `compute_stop_presample.py`: spot-1m kind recompute, one coin at a time (via heavy_slot) ->
  `tmp/stop_presample.json` (per-fill kinds + per-year base/boosted/rest stop rates; heartbeat).
- `build_calendar_2021.py` + `compute_calendar_2021.py`: same frozen rule on `bars_4h_4shift`
  grid timestamps + join to the reused k2placebo ledger -> `tmp/calendar_2021.json`
  (CPU-only; heartbeat).
- Engine (`run_engine.py` + `analyze.py` + `compute_ctrlC.py`) ONLY if PRIMARY + SECONDARY pass
  (else not written; REPORT states the stop). Bybit S5 only in that branch.
- Deliverables: PLAN.md (this file), calendar_rule.py, build/compute scripts,
  calendar_mult_*.parquet, tmp/*.json, results.json, REPORT.md,
  tests/test_oc_d_calendar.py (>=1 causality/truncation test + >=1 hand-checked synthetic case;
  `.venv/Scripts/python.exe -m pytest tests/test_oc_d_calendar.py -q`).
- No selection on the most recent year except the frozen engine branch (dev4 robust pick only;
  post-release year scored ONCE for the pick and REF).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the original row
  stays and the change is a disclosed extra row.)
