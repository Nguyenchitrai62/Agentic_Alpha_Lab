# oc_d_ddrank — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_d_ddrank.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md, `docs/opencode/IDEAS12_20261008.md` idea #1 read in full).
Write ONLY `research/tournament/oc_d_ddrank/` + `tests/test_oc_d_ddrank.py`. No other file is
edited (registry, ledgers, CONTINUOUS_RESEARCH.md, NEXT_AGENT.md, docs/ except nothing,
bot/, backend/, scripts/, other workers' folders, ../Kronos, git state untouched;
GIT READ-ONLY: never stash/reset/checkout/restore/clean/rm/commit/switch/rebase/merge).
Scratch only under `research/tournament/oc_d_ddrank/tmp/`. Progress print every 10 min
(heartbeat every 600 s in long loops). Heavy 1m work (stop-kind recompute; any engine)
via `scripts/heavy_slot.py` (RAM tight: one job at a time, one coin's 1m slice in RAM
at a time, float32 where possible); replica joins + placebos are CPU-only on 4h closes.

## Idea #1 EXACTLY as written (IDEAS12 §1)

Mech: the carrier rotates (oc_coinattrib: XRP 52-71% of book/dips in 2022/2024, SOL 63%/71%
dips in 2021/2022 -> keep all 5); trailing losers overshoot and snap back harder.
Cross-sectional rank is distribution-free (no level fit).

Rule (causal): rank 5 coins by trailing-30d DD-depth of own 4h closes (<= bar close,
frozen 30d). V1 rung mult deepest x1.25 / shallowest x0.75 / middle x1.0 (frozen K2-family
mults); V2 top-2 deep x1.25 else x1.0. No parameter fitted to returns.

Data/harness: 4h closes only (spot pre-sample OK); replica PRIMARY, engine + constant
control + Bybit S5 SECONDARY. Effect: +0.0-0.12%/mo, DD flat/-0.3. Prior 14%.

Crash: deepest coin = epicenter risk (SOL-FTX, XRP-SEC); contained by kept B1 (downweights
correlated flushes) + cap 2.0 + pre-registered stop-rate check (fail if pooled
stop-given-fill rises >+1pp, b7breaker standard); must survive the 2020p COVID leg.

Closest CLOSED: oc_trendladder/oc_btclead/oc_b1btc (trend/lead/corr axes) / oc_altdipb1
(alt BASKET, DD worse 5/5) — this ranks by own trailing DD depth.

## Frozen variants (ONLY these two + reference, no tuning, no refit)

- REF = base dip replica unchanged (mult 1.0), reproduction row only.
- V1: per (shift s, decision bar open T), rank available coins by DD-depth (see below):
  deepest -> 1.25, shallowest -> 0.75, middle -> 1.0.
- V2: per (s, T), top-2 deepest -> 1.25, else -> 1.0.
- Mults {1.25, 1.0, 0.75} are the frozen K2-family mults (IDEAS12: "frozen K2-family mults").
  30d, 1.25/0.75/1.0, top-2 are frozen ex-ante round numbers, never scanned.
- Book untouched (dip-only sizing overlay; presample replica has no book leg anyway).

## DD-depth (frozen, causal, closes-only, no fit)

- Source (read-only): pre-sample `research/tournament/oc_presampletilt/bars_4h_presample.parquet`
  (4 syms BTCUSDT/ETHUSDT/BNBUSDT/XRPUSDT x shifts 0..3, ORIGIN 2020-01-01 + s h grid;
  per (sym, shift) series sorted by T = bar open; only `close` used; SOL absent pre-sample);
  2021-2026 `research/tournament/oc_kronoshidden/bars_4h_4shift.parquet` (5 majors x shifts
  0..3; only `close` used). No other column is read.
- Window: LOOKBACK = 180 bars = 30d x 6 bars/day (frozen 30d). MIN_PERIODS = 60 finite
  closes (frozen; early bars -> NaN -> mult 1.0, inert, counted).
- Timing: for a dip decision at holding-bar open T[j] on shift s (grid time), the available
  closes are those with close_time <= T[j], i.e. bars i with T[i]+4h <= T[j] (on the 4h grid
  this is i <= j-1). Let C = close series. Current = C[j-1] (the bar that just closed;
  NaN -> DD NaN). Window = C[j-180 .. j-1] (180 bars ending at the just-closed bar, current
  included; strictly no bar closing after T[j]). DD-depth[j] = (max(window) - current) /
  max(window) (NaN if max non-finite/non-positive or < MIN_PERIODS finite in window).
  DD-depth >= 0 by construction (0 = at trailing peak). Uses only closes with
  close_time <= T[j] — causal by construction.
- Coins ranked at (s, T): warmed-up + finite-O/sg coins implicit via the ledger join; for the
  mult panel, the universe is syms with finite DD-depth at (s, T). Missing/NaN DD -> that
  coin's mult = 1.0 at (s, T) (never ranked; counted). If NO coin has finite DD at (s, T),
  all mults = 1.0 (inert).
- Ranking (deterministic, fit-free): sort finite-DD coins by DD-depth descending (deepest
  first); ties broken by sym alphabetical (frozen). V1: rank 0 -> 1.25; rank N-1 -> 0.75;
  others -> 1.0; N == 1 -> 1.0 (no cross-section, disclosed); N == 2 -> deepest 1.25,
  shallowest 0.75 (no middle). V2: ranks 0,1 (if exist and N >= 2) -> 1.25, else 1.0;
  N == 1 -> 1.0 (disclosed). Rank is distribution-free (no level/threshold fit).
- Output: `ddrank_mult_presample.parquet` (shift, T, per-sym mult_V1/mult_V2) +
  `ddrank_mult_2021.parquet` (same on the 2021-2026 grid). T ranges = union of the
  respective shift grids. Per-coin mults (not market-wide: each coin has its own rank mult
  at the same (s, T) — disclosed difference vs B7 market-wide).
- Unit-tested: hand-checked synthetic DD/rank/mult arithmetic + causality/truncation test
  (recompute from bars truncated at a cut date -> identical on kept prefix).

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
  `oc_presampletilt/results.json`). If the gate fails: STOP and report.
- Per fill join (phase=shift, T=bar open, coin BTC/ETH/BNB/XRP = 0/1/2/3 inherited):
  exact match on the (shift, sym, T) mult panel, fallback to latest grid time <= T
  (ffill, causal); missing -> 1.0 (counted and disclosed).

## Replica + placebo (fixed; CPU-only, no engine)

- Per pre-sample year y (4-phase means, same `phase_mean_sums` as k2placebo/voltilt/chronos/
  cascadedelay/cascadeboost with n_years=4 on ledger year 0..3): base(y), tilted_V1(y),
  tilted_V2(y), realised_mean(y) (mean mult over fills in y), norm(y) = tilted(y)/
  realised_mean(y), gain(y) = norm(y) - base(y). "Helps" in a year iff gain(y) > 0.
  Report n fills too, plus boosted (1.25) / de-weighted (0.75, V1 only) fill shares.
  dSum_pre = sum gains over 4 pre-sample years (diagnostic; the +0.273 gate is the
  2021-2026 secondary gate, not applied to pre-sample).
- Rank-shuffle placebo per year (PRIMARY null for this cross-sectional idea): at each
  (year y, shift s, time-bar T), permute the per-coin mults across coins (same multiset
  per bar, breaks ranking only; preserves timing/market exposure and per-bar boosted counts).
  1000 perms, seed 20261007+y (y = 0..3). Fills inherit their (sym, s, T) permuted mult.
- Timing placebo per year (diagnostic; the idea is cross-sectional, not a timing rule):
  uniform permutation of the (sym, shift, T) triple mults across fills within the year
  (1000 perms, seed 20261009+y; breaks timing and ranking; preserves marginal mult
  distribution). Block placebo per year (diagnostic): 42-bar chronological blocks per
  (sym, shift) permuted within the year (seed 20261008+y; preserves local persistence).
  All perm norms use the ACTUAL realised-mean denominator. Percentile =
  100*(1+#{perm<=actual})/1001; significant iff >= 95.
- PRIMARY pass (pre-registered): gain > 0 in >= 3/4 pre-sample years AND Y2020p (COVID leg)
  gain > 0 (must survive the COVID leg) AND pooled boosted stop-rate delta <= +1pp
  (see crash section). Timing significance is REPORTED but does not gate (cross-sectional
  idea, not a timing rule — disclosed). If PRIMARY fails for both variants: STOP after the
  secondary replica gate is still reported? NO — per assignment, SECONDARY is still computed
  (cheap replica) for completeness, but ENGINE is only for a variant that helps on the
  pre-sample AND passes the secondary gate.
- Round-trip ~4-8 bps bounds all effects (stated in REPORT).

## Crash risk (fixed; stop-hit share of boosted/de-weighted fills vs base rate)

- The presample ledger stores no exit reason, so exit kinds are recomputed per fill from the
  read-only spot 1m store (`data/raw/spot_1m_presample_20261007`, one coin in RAM at a time,
  float32) with VERBATIM `build_ledger_presample.outcome_mu` logic at mu=1.0 (sl = lv*(1-4*sg),
  bl = lv*(1-8*sg), tp = lv*(1+1.0*sg); close5 4sg stop + 8sg backstop + TP + timeout at next
  4h open; stop-first ordering backstop > tp > stop). "Hit the stop" = kind in
  {stop, backstop}. Base rate = stop-hit share over all fills in the year; boosted rate =
  stop-hit share over mult==1.25 fills; de-weighted rate = stop-hit share over mult==0.75
  fills (V1 only); report delta (group - base) per year + pooled. Also report TP share as a
  secondary row (same split). FAIL if pooled boosted stop-given-fill rises > +1pp
  (b7breaker standard, pre-registered).
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
  > 0 (survival) per PRIMARY pass above.

## SECONDARY: 2021-2026 replica gate (fixed; CPU-only, no engine)

- Ledger (read-only, never edited, never rebuilt): `oc_k2placebo/tmp/ledger.npz` +
  `oc_k2placebo/tmp/bt_all.npy` (oc_placebo_dip D0+B1 4-phase replica, 5 anchor years
  2021-09-24..2026-09-23; RUNGS 2.5-5, live 16..238 strict trade-through, B1 w=1/(1+n),
  gate costs inside, stop-first). Reproduction gate: n == 22312 and base 4-phase-mean
  sums == (0.911273, 0.832599, 2.099814, 3.197390, 0.677229), sum5y == 7.718304 +- 0.002
  (copied from `oc_k2placebo/results.json`). If the gate fails: STOP and report.
- Mults: `ddrank_mult_2021.parquet` built from `bars_4h_4shift.parquet` closes with the
  FROZEN DD-depth/rank rule above (same 180/60 constants; 5 majors; per (shift, T) ranking
  over available majors with finite DD). Join (sym, shift=phase, T=bar open) exact + causal
  ffill fallback; missing -> 1.0 (counted).
- Per year y = 0..4 (anchors 2021..2025-09-24, year = [A_y, A_{y+1}), A_5 = 2026-09-24):
  base(y), tilted(y), realised_mean(y), norm(y) = tilted(y)/realised_mean(y),
  gain(y) = norm(y) - base(y). dSum5y = sum gains over 5 years. sum-half = count gain>0
  (HELP in >= 4/5 required). SECONDARY pass (pre-registered): dSum5y >= +0.273 AND
  sum-half >= 4/5 (assignment: "dSum5y >= +0.273 and sum-half >= 4/5"). Rank-shuffle /
  timing / block placebos reported per year (same seeds + y = 0..4 for the 5-year leg:
  rank-shuffle 20261007+y, block 20261008+y, timing 20261009+y) but do not gate beyond the
  dSum/sum-half rule (disclosed).
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
  - Candidate leg: dip rung size x DD-rank mult(T, shift, sym) (book byte-identical to G2;
    G2 dip gross cap 2.0 and every other G2 limit bind enforced inside the engine; gate costs
    maker 0.0002/taker 0.00055/stop-taker, longs pay 0.0001/8h, shorts 0; limit fill only on
    1m trade-through; nothing in first 5 min after a 4h close (win_start=5); stop-first).
    Mechanism = exact copy of oc_cboostctrl/run_engine.py (= oc_cascadeboost = v414 pipe v321,
    corr-aware inv sizes kd=1.7, bear books, risk budget 0.26*1*1.7, sleeve_gross_cap 2.0).
  - Exposure-matched constant control: CTRL_C = constant dip-budget multiplier per anchor year
    = candidate's realised mean dip-budget multiplier in that year from the candidate's own
    engine run (same average exposure, no ranking; non-tradable decomposition control by
    construction, labelled; never feeds any tradable choice). Share split
    exposure = (CTRL-REF)/(CAND-REF), timing+ranking = (CAND-CTRL)/(CAND-REF) when CAND > REF.
  - Bybit S5 leg: price-source switch only (Bybit 1m from 2021-11-15; y2021 short window);
    same candidate vs REF on Bybit-S5 dev4 under the robust rule (DD<=20, no losing dev year,
    then highest WORST, ties->mean) AND full-path DD<=20 (oc_confirmgate Leg1 definition).
  - Stages: dev [2021-09-24, 2025-09-24) for selection (robust rule on dev4 ONLY), last year
    2025-09-24..2026-09-23 scored ONCE for the pick AND REF only (labelled). 5y + full-path DD
    reported. If PRIMARY or SECONDARY fails: NO ENGINE (valid negative result; REPORT states
    which gate failed and stops — no engine claim).
- Candidate-credibility checks (applied in REPORT): (1) sign-stable / fit-free rule (this rule
  has NO fits, NO thresholds on returns, rank is distribution-free — passes by construction);
  (2) beats the exposure control (CAND > CTRL_C on dev4 mean, else timing/ranking is exposure);
  (3) Bybit leg (must not lose robustly / DD-breach on S5); (4) pre-sample leg (PRIMARY pass
  above). All four must hold to adopt; else REJECT / needs-prospective.

## Leakage / checks (stated in REPORT)

- Feature timing (DD-depth: closes with close_time <= T only; window excludes any bar closing
  after T; current = just-closed bar; ranking at (s,T) uses only DD available at T;
  truncation-tested in tests/test_oc_d_ddrank.py), label windows (no labels fit anywhere),
  fit windows (no fits; 180/60/1.25/0.75/top-2/seeds/BLOCK 42 all frozen ex-ante, never
  scanned; no statistic from any test year feeds any choice; pre-sample years never used for
  any fit), fill timing (live 16..238 strict trade-through + stop-first inherited; perms
  reassign mults within year only: rank-shuffle within (year, shift, T) bars; timing uniform
  within year; block-42 within (year, sym, shift)). Gate costs inside the reused replica
  outcomes (maker 0.0002/taker 0.00055, adverse long funding 0.0001/8h). Coverage: disclose
  any skipped year / missing-mult count / unknown-kind count. Spot-vs-perp caveat on every
  pre-sample number (SPOT fills/exits, perp gate costs).

## Compute plan (resume-safe, heartbeat every 600 s)

- `ddrank_rule.py`: pure helpers (`dd_depth`, `rank_mults`, `compute_sigma`, `find_fill`,
  `outcome_kind`) — no data access; unit-tested.
- `build_ddrank_presample.py`: CPU-only pre-sample 4h closes -> `ddrank_mult_presample.parquet`
  + DD coverage counts (fast; prints progress).
- `compute_ddrank_presample.py`: CPU-only join to the reused presample ledger + per-year
  sums/gains + 1000-perm rank-shuffle/timing/block placebos (V1 + V2) -> `tmp/ddrank_presample.json`
  (heartbeat every 600 s).
- `compute_stop_presample.py`: spot-1m kind recompute, one coin at a time (via heavy_slot) ->
  `tmp/stop_presample.json` (per-fill kinds + per-year base/boosted/de-weighted stop rates; heartbeat).
- `build_ddrank_2021.py` + `compute_ddrank_2021.py`: same frozen rule on `bars_4h_4shift`
  closes + join to the reused k2placebo ledger -> `tmp/ddrank_2021.json` (CPU-only; heartbeat).
- Engine (`run_engine.py` + `analyze.py` + `compute_ctrlC.py`) ONLY if PRIMARY + SECONDARY pass
  (else not written; REPORT states the stop). Bybit S5 only in that branch.
- Deliverables: PLAN.md (this file), ddrank_rule.py, build/compute scripts,
  ddrank_mult_*.parquet, tmp/*.json, results.json, REPORT.md,
  tests/test_oc_d_ddrank.py (>=1 causality/truncation test + >=1 hand-checked synthetic case;
  `.venv/Scripts/python.exe -m pytest tests/test_oc_d_ddrank.py -q`).
- No selection on the most recent year except the frozen engine branch (dev4 robust pick only;
  post-release year scored ONCE for the pick and REF).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the original row
  stays and the change is a disclosed extra row.)
