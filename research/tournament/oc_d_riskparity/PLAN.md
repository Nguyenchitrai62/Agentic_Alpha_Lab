# oc_d_riskparity — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_d_riskparity.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md, `docs/opencode/IDEAS12_20261008.md` idea #3 read in full).
Write ONLY `research/tournament/oc_d_riskparity/` + `tests/test_oc_d_riskparity.py`. No other file is
edited (registry, ledgers, CONTINUOUS_RESEARCH.md, NEXT_AGENT.md, docs/, bot/, backend/, scripts/,
other workers' folders, ../Kronos, git state untouched;
GIT READ-ONLY: never stash/reset/checkout/restore/clean/rm/commit/switch/rebase/merge).
Scratch only under `research/tournament/oc_d_riskparity/tmp/`. Progress print every 10 min
(heartbeat every 600 s in long loops). Heavy 1m work (V2 ledger rebuilds, stop-kind recomputes;
any engine) via `scripts/heavy_slot.py` (RAM tight: one job at a time, one coin's 1m slice in
RAM at a time, float32 where possible); V1 joins + placebos are CPU-only on ledger arrays.

## Idea #3 EXACTLY as written (IDEAS12 §3)

Mech: oc_contrib/oc_depthregime: deep rungs + stops carry DD while shallow + TP earn; fixed
sizes overpay tail risk per deep fill. size = base x (4sg/stopDist) so every rung's stop-out
loses the same.

Rule: V1 parity-scaled sizes with frozen 4sg stops (pure arithmetic; exposure-normalized
constant control). V2 depth-scaled stops (2.5/3.5/4.5/5.5sg rungs -> 4/5/6/7sg stops, frozen
round numbers) + parity sizes. No distribution or return fit.

Data/harness: sigma360 + frozen stops (spot pre-sample OK); replica PRIMARY, engine + control
SECONDARY. Effect: ~0 return (+-0.05), DD -0-0.5 (crash-reducing BY CONSTRUCTION: deep rungs
shrink). Prior 12%.

Crash: helps by construction (deep = smaller when it matters); shallow slightly larger but
tight-stopped; cap/B1 kept.

Closest CLOSED: oc_idea1_kellyrung (DD 21.79 breach — Kelly sized tails UP, this sizes them
DOWN) / kelly screen (in-flight distributional fit — this fits nothing) / oc_b1shape (corr
shapes, S1 stands).

## Frozen reading of "size = base x (4sg/stopDist)" (no fit, pure arithmetic)

Base replica sizes equalise the ENTRY-to-stop loss (every rung stops 4sg below its entry, so
every stop-out loses ~4sg + fees), but overpay the OPEN-to-stop tail risk: a deep rung that
stops sits (k+4)sg below the signal open while a shallow one sits (2.5+4)sg below. Parity
equalises the OPEN-to-stop dollar risk:

- stopDist_k = (k + stop_sg_k) x sg(T): rung depth k (distance open -> rung entry) plus the
  entry->stop distance stop_sg_k, in units of the replica level sigma sg(T) at the decision
  bar T (sigma360, VERBATIM replica sigma; spot pre-sample OK).
- parity mult m_k = 4 / (k + stop_sg_k) (frozen arithmetic; numerator 4 = the frozen base
  stop in sg units, so every rung's open-to-stop loss is 4sg x base size).
- Deep rungs shrink by construction (larger k + wider stop -> smaller m); shallow rungs are
  relatively larger but tight-stopped. No distribution, no return, no threshold is fit.

## Frozen variants (ONLY these two + reference, no tuning, no refit)

- REF = base dip replica unchanged (mult 1.0), reproduction row only.
- V1: base 5-rung grid k in {2.5, 3.0, 3.5, 4.0, 5.0} (ledger rung 0..4), frozen UNIFORM 4sg
  entry->stop (ledger outcomes y10 unchanged: sizing-only overlay).
  stop_sg = 4 for all rungs -> m = 4/(k+4):
  rung0 (2.5sg) 0.615385, rung1 (3.0sg) 0.571429, rung2 (3.5sg) 0.533333,
  rung3 (4.0sg) 0.500000, rung4 (5.0sg) 0.444444.
  w' = w x m_{rung}; y10 unchanged. Sizing-only, CPU-only, both eras.
- V2: 4-rung grid k' in {2.5, 3.5, 4.5, 5.5} (V2 rung 0..3) with depth-scaled entry->stop
  s' in {4, 5, 6, 7} paired in order (frozen round numbers), + parity sizes:
  open-to-stop 6.5/8.5/10.5/12.5 sg -> m' = 4/(k'+s'):
  V2-rung0 0.615385, V2-rung1 0.470588, V2-rung2 0.380952, V2-rung3 0.320000.
  Backstop frozen 8sg (unchanged, disclosed); TP legs 0.9/1.0/1.1 unchanged; kept iff
  y09/y10/y11 ALL finite (same paired-leg rule); B1 w = 1/(1+n) with DETECT_K = 2.5
  unchanged; live 16..238 strict trade-through; gate costs inside; stop-first. Everything
  else VERBATIM the base replica core of each era (same grids, sigma, warm-up, years,
  coins, n_vector, costs). V2 therefore REBUILDS fills + outcomes at the new grid (heavy
  1m, one coin at a time via heavy_slot); it is not a sizing overlay.
- Book untouched (dip-only sizing/stop overlay; presample replica has no book leg anyway;
  engine stage keeps G2 book byte-identical). G2 dip gross cap 2.0 + every other G2 limit
  bind enforced inside the engine (engine stage only; replica has NO budget/cap, inherited).
- Mults are TIME-INVARIANT per rung (pure rung arithmetic, no market state): this is NOT a
  timing rule and NOT a cross-sectional rule, so timing/block placebos are REPORTED as
  diagnostics but do not gate (same disclosure as oc_d_ddrank's cross-sectional case).

## Pre-sample years + ledger (fixed, inherited VERBATIM from oc_presampletilt/oc_cboostpre)

- Years (bars with open in the interval; exits may realise after):
  Y2017 = [2017-10-16, 2018-01-01), Y2018 = [2018-01-01, 2019-01-01),
  Y2019 = [2019-01-01, 2020-01-01), Y2020p = [2020-01-01, 2020-09-01).
  Coins/warm-up inherited via the ledger (Y2017 BTC+ETH only incl. warm-up; Y2018+ BTC/ETH/
  BNB + XRP from 2018-07-03; SOL absent). No re-filtering here.
- V1 ledger (read-only, never edited, never rebuilt): `oc_presampletilt/tmp/ledger_presample.npz`
  + `oc_presampletilt/tmp/bt_presample.npy` (D0+B1 replica same as oc_k2placebo: RUNGS
  2.5/3/3.5/4/5, live 16..238 strict trade-through, w=1/(1+n) coins-present-only,
  outcome_mu TP 0.9/1.0/1.1 close5+backstop, gate costs inside, stop-first, kept iff
  y09/y10/y11 ALL finite; NO budget/cap; SPOT fills/exits, perp gate costs — spot-vs-perp
  caveat on every number). Reproduction gate: n == 9731, per-leg 909/2986/3115/2721, and
  base 4-phase-mean sums == (2.313362, 2.678870, 0.577643, 0.297538) +- 1e-6 (copied from
  `oc_presampletilt/results.json`). If the gate fails: STOP and report.
- V1 join: per fill rung index 0..4 -> frozen m_k above (no bars needed; missing rung ->
  1.0, counted; none expected).
- V2 ledger (rebuilt HERE, stored HERE under `tmp/ledger_v2_presample.npz` +
  `tmp/bt_v2_presample.npy`): same VERBATIM core as `build_ledger_presample.py` (same ORIGIN
  2020-01-01 + s h grid, same spot 1m store, same compute_sigma rolling-360/min_periods-120/
  shift-1, same warm-up, same years/coins, same n_vector DETECT_K=2.5, same live window,
  same outcome branch with PER-RUNG M_SL in {4,5,6,7} and frozen BACKSTOP 8.0, same TP legs,
  same kept rule, same gate costs, same stop-first), with ONLY: RUNGS_V2 = (2.5,3.5,4.5,5.5),
  STOPS_V2 = (4.0,5.0,6.0,7.0), w = B1 x m'_{V2 rung}. Resume-safe per-leg checkpoints in
  MY tmp only. Fills/years counted + disclosed (V2 has its own fill set; gains below use
  V2's own realised mean).

## Replica + placebo (fixed; V1 CPU-only overlay, V2 rebuilt ledger)

- Per pre-sample year y (4-phase means, same `phase_mean_sums` as k2placebo/voltilt/chronos/
  cascadedelay/cascadeboost/cboostpre with n_years=4 on ledger year 0..3): base(y) from the
  REF ledger, tilted(y) with parity weights (V1: w x m on REF fills; V2: w2 x m' built into
  the V2 ledger, outcomes y10_2 from depth-scaled stops), realised_mean(y) (mean parity mult
  over fills in y of that variant's ledger), norm(y) = tilted(y)/realised_mean(y),
  gain(y) = norm(y) - base(y). "Helps" in a year iff gain(y) > 0. Report n fills too, plus
  per-rung fill shares and the realised mean (exposure diagnostic).
  dSum_pre = sum gains over 4 pre-sample years (diagnostic; the +0.273 gate is the
  2021-2026 secondary gate, not applied to pre-sample).
- Timing placebo per year (DIAGNOSTIC ONLY — parity is not a timing rule): uniform
  permutation of per-fill parity mults across fills within the year (1000 perms, seed
  20261009+y, y = 0..3; preserves marginal mult distribution, breaks rung->outcome link;
  fills inherit permuted mult). Block placebo per year (diagnostic): permute per-fill mults
  in chronological 42-fill blocks per (coin, phase) within the year (seed 20261008+y;
  preserves local persistence up to block edges). All perm norms use the ACTUAL
  realised-mean denominator. Percentile = 100*(1+#{perm<=actual})/1001; significant iff
  >= 95. Reported per year per variant; NEVER gates (disclosed, pre-registered).
- PRIMARY pass (pre-registered): gain > 0 in >= 3/4 pre-sample years AND Y2020p (COVID leg)
  gain > 0 (must survive the COVID leg, IDEAS12 explicit) AND pooled parity-weighted
  stop-rate delta <= +1pp (see crash section). If PRIMARY fails for both variants:
  SECONDARY replica is still computed (cheap for V1, heavy rebuild for V2 — both done) for
  completeness, but ENGINE is only for a variant that helps on the pre-sample AND passes
  the secondary gate.
- Round-trip ~4-8 bps bounds all effects (stated in REPORT).

## Crash risk (fixed; stop-hit share parity-weighted vs base + per-rung groups)

- "Hit the stop" = kind in {stop, backstop} at mu=1.0 (close5 stop or backstop; TP/timeout
  otherwise), VERBATIM `build_ledger_presample.outcome_mu` / `compute_placebo_dip.outcome_mu`
  branch (sl = lv x (1 - M_SL x sg) with M_SL = 4.0 base / per-rung {4,5,6,7} V2,
  bl = lv x (1 - 8 x sg), tp = lv x (1 + 1.0 x sg); close5 sampling; stop-first ordering
  backstop > tp > stop).
- V1 kinds: recomputed HERE per REF fill from the read-only spot 1m store
  (`data/raw/spot_1m_presample_20261007`, one coin in RAM at a time, float32) with levels
  lv = O(T) x (1 - k x sg(T)), k from ledger rung {2.5,3,3.5,4,5}; O/sg from
  `bars_4h_presample` (open + VERBATIM `compute_sigma` pct_change rolling-360 min_periods-120
  shift-1). DISCLOSED CAVEAT (inherited from oc_cboostpre): the ledger's O/sg were sampled
  as 1m-open-at-T on its own grid while this recompute uses the frozen bars open series;
  the two agree whenever minute T is present (dense store) but may differ on gapped bars —
  the recompute is a like-for-like diagnostic, not a ledger rewrite; fills are never
  added/dropped (same 9731 fills; kinds only). Unknown windows counted, rates over known
  kinds only. Via heavy_slot.
- V2 kinds: recorded DURING the V2 rebuild itself (same 1m arrays, per-rung stops; no second
  pass needed); base-rate comparison uses V1-kind base shares on REF fills.
- Groups (frozen): V1 shallow = rungs {0,1} (k<=3.0), mid = {2}, deep = {3,4} (k>=4.0);
  V2 shallow = {0} (2.5sg), mid = {1}, deep = {2,3} (4.5/5.5sg). Report per-group stop-hit
  shares + pooled parity-weighted stop share (weights = parity mults = actual tilted
  exposure) vs pooled base share, per year + pooled, plus TP shares as a secondary row.
  FAIL if pooled parity-weighted stop-given-fill rises > +1pp over base (b7breaker standard,
  pre-registered). COVID leg Y2020p stop deltas reported on their own row; Y2020p gain must
  be > 0 (survival) per PRIMARY pass above.
- Fill windows: same live 16..238 strict low trade-through (`find_fill` verbatim); NaN 1m
  gaps never fill/trigger/exit (inherited).

## SECONDARY: 2021-2026 replica gate (fixed)

- V1 ledger (read-only, never edited, never rebuilt): `oc_k2placebo/tmp/ledger.npz` +
  `oc_k2placebo/tmp/bt_all.npy` (oc_placebo_dip D0+B1 4-phase replica, 5 anchor years
  2021-09-24..2026-09-23; RUNGS 2.5-5, live 16..238 strict trade-through, B1 w=1/(1+n),
  gate costs inside, stop-first). Reproduction gate: n == 22312 and base 4-phase-mean
  sums == (0.911273, 0.832599, 2.099814, 3.197390, 0.677229), sum5y == 7.718304 +- 0.002
  (copied from `oc_k2placebo/results.json`). If the gate fails: STOP and report.
  V1 join: rung 0..4 -> frozen m_k (CPU-only).
- V2 ledger (rebuilt HERE, `tmp/ledger_v2_2021.npz` + `tmp/bt_v2_2021.npy`): VERBATIM
  `compute_placebo_dip.build_base` core (same START 2020-08-01 grid, same perp 1m stores
  `data/raw/btc_intraday_20260924` + `data/raw/majors_intraday_20260924`, same bar
  opens/sigma pct_change rolling-360/min_periods-120/shift-1, same TRADE_START/YEAR_END,
  same n_vector DETECT_K=2.5, same live window, same costs/settle/stop-first, same kept
  rule), with ONLY: RUNGS_V2/STOPS_V2/MULTS_V2 as above (per-rung M_SL in outcome_mu,
  w = B1 x m'). Resume-safe per-(coin,phase) checkpoints in MY tmp only, via heavy_slot,
  one coin in RAM at a time, float32.
- Per year y = 0..4 (anchors 2021..2025-09-24, year = [A_y, A_{y+1}), A_5 = 2026-09-24):
  base(y), tilted(y), realised_mean(y), norm(y) = tilted(y)/realised_mean(y),
  gain(y) = norm(y) - base(y). dSum5y = sum gains over 5 years. sum-half = count gain>0
  (HELP in >= 4/5 required). SECONDARY pass (pre-registered): dSum5y >= +0.273 AND
  sum-half >= 4/5 (assignment: "dSum5y >= +0.273 and sum-half >= 4/5"). Timing / block
  placebos reported per year (same diagnostic nulls, seeds + y = 0..4: timing 20261009+y,
  block 20261008+y) but do not gate beyond the dSum/sum-half rule (disclosed).
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
  - Candidate leg: V1 = dip rung size x m_{rung} (book byte-identical to G2); V2 = dip rungs
    at 2.5/3.5/4.5/5.5sg with per-rung stops 4/5/6/7sg and sizes x m' (book byte-identical
    to G2; G2 dip gross cap 2.0 and every other G2 limit bind enforced inside the engine;
    gate costs maker 0.0002/taker 0.00055/stop-taker, longs pay 0.0001/8h, shorts 0; limit
    fill only on 1m trade-through; nothing in first 5 min after a 4h close (win_start=5);
    stop-first). Mechanism = exact copy of oc_cboostctrl/run_engine.py (= oc_cascadeboost =
    v414 pipe v321, corr-aware inv sizes kd=1.7, bear books, risk budget 0.26*1*1.7,
    sleeve_gross_cap 2.0).
  - Exposure-matched constant control: CTRL_C = constant dip-budget multiplier per anchor year
    = candidate's realised mean dip-budget multiplier in that year from the candidate's own
    engine run (same average exposure, no parity shape; non-tradable decomposition control by
    construction, labelled; never feeds any tradable choice). Share split
    exposure = (CTRL-REF)/(CAND-REF), parity-shape = (CAND-CTRL)/(CAND-REF) when CAND > REF.
  - Bybit S5 leg: price-source switch only (Bybit 1m from 2021-11-15; y2021 short window);
    same candidate vs REF on Bybit-S5 dev4 under the robust rule (DD<=20, no losing dev year,
    then highest WORST, ties->mean) AND full-path DD<=20 (oc_confirmgate Leg1 definition).
  - Stages: dev [2021-09-24, 2025-09-24) for selection (robust rule on dev4 ONLY), last year
    2025-09-24..2026-09-23 scored ONCE for the pick AND REF only (labelled). 5y + full-path DD
    reported. If PRIMARY or SECONDARY fails: NO ENGINE (valid negative result; REPORT states
    which gate failed and stops — no engine claim).
- Candidate-credibility checks (applied in REPORT): (1) sign-stable / fit-free rule (this rule
  has NO fits, NO thresholds on returns, rung arithmetic only — passes by construction);
  (2) beats the exposure control (CAND > CTRL_C on dev4 mean, else the gain is exposure);
  (3) Bybit leg (must not lose robustly / DD-breach on S5); (4) pre-sample leg (PRIMARY pass
  above). All four must hold to adopt; else REJECT / needs-prospective.

## Leakage / checks (stated in REPORT)

- Feature timing (V1: no features — rung index only; V2 levels/stops use O/sg available at T
  only; V2 fills/outcomes causal on 1m; truncation-tested in tests/test_oc_d_riskparity.py),
  label windows (no labels fit anywhere), fit windows (no fits; 2.5/3/3.5/4/5, 4/5/6/7,
  4/(k+s), seeds, BLOCK 42 all frozen ex-ante arithmetic, never scanned; no statistic from
  any test year feeds any choice; pre-sample years never used for any fit), fill timing
  (live 16..238 strict trade-through + stop-first inherited; perms reassign mults within year
  only: timing uniform within year; block-42-fill chronological within (year, coin, phase)).
  Gate costs inside the reused/rebuilt replica outcomes (maker 0.0002/taker 0.00055, adverse
  long funding 0.0001/8h). Coverage: disclose any skipped year / missing-mult count /
  unknown-kind count / V2 fill-count deltas vs REF. Spot-vs-perp caveat on every pre-sample
  number (SPOT fills/exits, perp gate costs).

## Compute plan (resume-safe, heartbeat every 600 s)

- `riskparity_rule.py`: pure helpers (`parity_mults_V1`, `parity_mults_V2`, `compute_sigma`,
  `find_fill`, `outcome_kind` (base M_SL=4.0) + `outcome_kind_v2` (per-rung stop mult),
  `phase_mean_sums`) — no data access; unit-tested.
- `compute_v1_presample.py`: CPU-only join REF presample ledger rung -> m_k + per-year
  sums/gains + 1000-perm timing/block diagnostics (V1 + REF reproduction gate) ->
  `tmp/v1_presample.json` (heartbeat 600 s).
- `compute_kind_v1_presample.py`: spot-1m kind recompute for REF fills (VERBATIM mu=1.0
  base stops), one coin at a time via heavy_slot -> `tmp/kind_v1_presample.npz` +
  per-rung/pooled stop table folded into `tmp/v1_presample.json` (heartbeat).
- `build_v2_presample.py`: heavy spot-1m V2 rebuild (VERBATIM presample core + V2 grid/
  stops/sizes; per-leg checkpoints) -> `tmp/ledger_v2_presample.npz` +
  `tmp/bt_v2_presample.npy` (heartbeat; via heavy_slot).
- `compute_v2_presample.py`: CPU-only V2-vs-base gains + timing/block diagnostics +
  stop table (kinds recorded in rebuild) -> `tmp/v2_presample.json`.
- `compute_v1_2021.py`: CPU-only join k2placebo ledger rung -> m_k + per-year gains +
  dSum5y/sum-half + diagnostics -> `tmp/v1_2021.json` (reproduction gate first).
- `compute_kind_v1_2021.py`: perp-1m kind recompute for k2placebo fills (base stops), one
  coin at a time via heavy_slot -> `tmp/kind_v1_2021.npz` (stop table for V1 secondary).
- `build_v2_2021.py`: heavy perp-1m V2 rebuild (VERBATIM build_base core + V2 grid/stops/
  sizes; per-(coin,phase) checkpoints) -> `tmp/ledger_v2_2021.npz` + `tmp/bt_v2_2021.npy`.
- `compute_v2_2021.py`: CPU-only V2-vs-base gains + dSum5y/sum-half + diagnostics + stop
  table -> `tmp/v2_2021.json`.
- Engine (`run_engine.py` + `analyze.py` + `compute_ctrlC.py`) ONLY if PRIMARY + SECONDARY
  pass for that variant (else not written; REPORT states the stop). Bybit S5 only in that
  branch.
- Deliverables: PLAN.md (this file), riskparity_rule.py, build/compute scripts,
  tmp/*.json/npz/npy, results.json, REPORT.md, tests/test_oc_d_riskparity.py (>=1
  causality/truncation test + >=1 hand-checked synthetic case;
  `.venv/Scripts/python.exe -m pytest tests/test_oc_d_riskparity.py -q`).
- No selection on the most recent year except the frozen engine branch (dev4 robust pick only;
  post-release year scored ONCE for the pick and REF).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the original row
  stays and the change is a disclosed extra row.)
