# oc_d_poststop — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_d_poststop.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md, `docs/opencode/IDEAS12_20261008.md` idea #2 read in full).
Write ONLY `research/tournament/oc_d_poststop/` + `tests/test_oc_d_poststop.py`. No other file is
edited (registry, ledgers, CONTINUOUS_RESEARCH.md, NEXT_AGENT.md, docs/ except nothing,
bot/, backend/, scripts/, other workers' folders, ../Kronos, git state untouched;
GIT READ-ONLY: never stash/reset/checkout/restore/clean/rm/commit/switch/rebase/merge).
Scratch only under `research/tournament/oc_d_poststop/tmp/`. Progress print every 10 min
(heartbeat every 600 s in long loops). Heavy 1m work (stop-kind/x recompute; any engine)
via `scripts/heavy_slot.py` (RAM tight: one job at a time, one coin's 1m slice in RAM
at a time, float32 where possible); replica joins + placebos are CPU-only.

## Idea #2 EXACTLY as written (IDEAS12 §2)

Mech: oc_cascadedelay proved cooled fills ARE the profit (dSum -2.95/-2.02, cooled 52-72%
carry P&L; timing 0.1 in 2024); oc_cooldown skips only the 2022-FTX tail. Stops mark
capitulation prints — buy the next flush, don't skip it.

Rule: after a dip stop on coin c (replica ledger, known at close), size c's new rungs
x1.25 for N days. V1 N=7, V2 N=3 (frozen B7-family windows/mult). No fit.

Data/harness: replica ledger + 1m (spot pre-sample OK); replica PRIMARY, engine + control
+ Bybit SECONDARY. Effect: +0.0-0.10%/mo, DD +0/-0.3 watch. Prior 12% (strongest lesson,
rarest trigger: ~4% stop rate -> wide CI).

Crash: stops cluster inside legs (COVID boosted stops +1.5/+3.3pp, oc_cboostpre); contained
by modest x1.25 (vs B7 x1.5) + cap 2.0 + B1; explicit FAIL if the 2020p COVID leg is
negative on PRIMARY.

Closest CLOSED: oc_cooldown (24h SKIP, inverse) / oc_cascadedelay (budget HALVE, inverse
logic) / oc_rearm (same-bar re-arm, DD up 5/5) — multi-day post-stop aggression was never
tested.

## Frozen variants (ONLY these two + reference, no tuning, no refit)

- REF = base dip replica unchanged (mult 1.0), reproduction row only.
- V1: per (coin c, shift s, decision bar open T'), mult 1.25 iff a stop on the SAME coin c
  and SAME shift s exited at tc with 0 < T' - tc <= 7 days, else 1.0.
- V2: same with N = 3 days.
- Mult 1.25 / N = 7 / N = 3 are the frozen B7-family constants (IDEAS12: "frozen B7-family
  windows/mult"), never scanned. No book leg (dip-only sizing overlay; presample replica
  has no book leg anyway). No other variant, no ensemble, no refit.

## Stop event (frozen, causal, VERBATIM ledger arithmetic, no new data)

- Source of fills: the reused replica ledgers (see below). The ledgers store no exit
  reason and no exit time, so both are recomputed per fill from the read-only 1m stores
  with VERBATIM `build_ledger_presample.outcome_mu` / `compute_placebo_dip.outcome_mu`
  logic at mu=1.0 (sl = lv*(1-4*sg), bl = lv*(1-8*sg), tp = lv*(1+1.0*sg); close5 4sg stop
  + 8sg backstop + TP + timeout at next 4h open; stop-first ordering backstop > tp > stop;
  costs identical to the ledger builders, kinds only).
- "Hit the stop" = kind in {stop, backstop} (close5 stop or backstop; TP/timeout otherwise).
- Exit minute x (VERBATIM branch): backstop x = f+1+kb; tp x = f+1+kt; stop x = km+1
  (km = f+1+ks; x = 240 with o2 if km+1 >= 240); time x = 240. tc = T + x minutes where
  T = the fill's holding-bar open. tc is known when the exit prints, strictly before any
  later 4h decision bar open T' with T' > tc — causal by construction (the "(known at
  close)" parenthetical is satisfied conservatively: a stop is only used for decisions
  strictly after its exit minute).
- Levels: lv = O(T)*(1-k*sg(T)), k from ledger rung {2.5,3,3.5,4,5}; O/sg from the frozen
  bars series (presample: `bars_4h_presample` opens + VERBATIM `compute_sigma` pct_change
  rolling-360 min_periods-120 shift-1; 2021-2026: `bars_4h_4shift` opens + the same
  VERBATIM replica sigma, i.e. `compute_placebo_dip.build_base` opens/sig arithmetic).
  DISCLOSED CAVEAT (inherited from oc_cboostpre): the ledger's O/sg were sampled on its own
  grid while this recompute uses the frozen bars open series; the two agree whenever minute
  T is present (dense store) but may differ on gapped bars — the recompute is a like-for-like
  diagnostic, never a ledger rewrite; fills are never added/dropped (kinds + exit times only).
- Fill windows: same live 16..238 strict low trade-through (`find_fill` verbatim); NaN 1m
  gaps never fill/trigger/exit (inherited). A fill whose window/level cannot be rebuilt is
  counted as unknown and NEVER triggers (conservative; rates over known kinds only).
- Per-coin same-shift scope (frozen, disclosed difference vs B7 market-wide): triggers from
  coin c on shift s boost only later decisions on the same (c, s). REJECTED alternative:
  cross-shift or cross-coin sharing — disclosed (the idea sizes "c's new rungs").
- Missing trigger history (T' before first computable exit) -> 1.0 (never boosted; inert,
  counted and disclosed).
- Output: `poststop_mult_presample.parquet` (shift, T, per-sym mult_V1/mult_V2 on the
  pre-sample grid) + `poststop_mult_2021.parquet` (same on the 2021-2026 grid) + per-fill
  stop-event tables in tmp/. T ranges = union of the respective shift grids.
- Unit-tested: hand-checked synthetic stop/kind/x/window arithmetic + causality/truncation
  test (recompute from bars/1m truncated at a cut date -> identical triggers on kept prefix).

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
- Per fill join (phase=shift, T=bar open, coin BTC/ETH/BNB/XRP = 0/1/2/3 inherited):
  exact match on the (shift, sym, T) mult panel, fallback to latest grid time <= T
  (ffill, causal); missing -> 1.0 (counted and disclosed).

## Replica + placebo (fixed; CPU-only joins, no engine)

- Per pre-sample year y (4-phase means, same `phase_mean_sums` as k2placebo/voltilt/chronos/
  cascadedelay/cascadeboost/cboostpre with n_years=4 on ledger year 0..3): base(y),
  boosted_V1(y), boosted_V2(y), realised_mean(y) (mean mult over fills in y),
  norm(y) = boosted(y)/realised_mean(y), gain(y) = norm(y) - base(y). "Helps" in a year
  iff gain(y) > 0. Report n fills too, plus boosted (1.25) fill share.
  dSum_pre = sum gains over 4 pre-sample years (diagnostic; the +0.273 gate is the
  2021-2026 secondary gate, not applied to pre-sample).
- Timing placebo per year (PRIMARY null: this IS a timing rule — post-stop windows place
  extra size at specific times): at each (year y, shift s, coin c), permute that coin's
  mult series uniformly over that (y, s, c)'s time-bars (1000 perms, seed 20261007+y with
  y = 0..3 for Y2017..Y2020p; preserves per-(coin,shift) boosted counts, breaks the
  stop-timing link; fills inherit their (sym, s, T) permuted mult). Perm norms use the
  ACTUAL realised-mean denominator. Percentile = 100*(1+#{perm<=actual})/1001; significant
  iff >= 95. This null satisfies the assignment's "1000 permutations ... within the year,
  same count and length" per coin-shift (same boosted count per (y,s,c)) plus the block
  variant below (same window lengths up to block edges); disclosed.
- Block placebo per year: 42-bar chronological blocks per (y, s, c), permuted within
  (y, s, c) (seed 20261008+y; preserves window-length structure up to block edges). Same
  normalisation/percentile/significance.
- PRIMARY pass (pre-registered): gain > 0 in >= 3/4 pre-sample years AND Y2020p (COVID leg)
  gain > 0 (must survive the COVID leg — IDEAS12 explicit FAIL otherwise) AND pooled boosted
  stop-rate delta <= +1pp (see crash section). Timing significance is REPORTED per year but
  does not gate beyond the gains/stop checks (disclosed; the timing null above is the
  idea-correct null and wide CIs are expected at ~4% stop rates). If PRIMARY fails for both
  variants: SECONDARY replica is still computed (cheap) for completeness, but ENGINE is only
  for a variant that helps on the pre-sample AND passes the secondary gate.
- Round-trip ~4-8 bps bounds all effects (stated in REPORT).

## Crash risk (fixed; stop-hit share of boosted fills vs base rate)

- Reuses the same per-fill kind recompute above (no second pass needed): "hit the stop" =
  kind in {stop, backstop} at mu=1.0. Base rate = stop-hit share over all fills in the year;
  boosted rate = stop-hit share over mult==1.25 fills (per variant V1/V2); report delta
  (boosted - base) per year + pooled. Also report TP share as a secondary row (same split).
  FAIL if pooled boosted stop-given-fill rises > +1pp (b7breaker standard, pre-registered;
  same as oc_d_ddrank). Unknown-kind fills excluded from rates (counted and disclosed).
- COVID leg separately: Y2020p stop deltas reported on their own row; Y2020p gain must be
  > 0 (survival) per PRIMARY pass above (IDEAS12: "explicit FAIL if the 2020p COVID leg is
  negative on PRIMARY").

## SECONDARY: 2021-2026 replica gate (fixed; CPU-only join, heavy 1m kind/x recompute)

- Ledger (read-only, never edited, never rebuilt): `oc_k2placebo/tmp/ledger.npz` +
  `oc_k2placebo/tmp/bt_all.npy` (oc_placebo_dip D0+B1 4-phase replica, 5 anchor years
  2021-09-24..2026-09-23; RUNGS 2.5-5, live 16..238 strict trade-through, B1 w=1/(1+n),
  gate costs inside, stop-first). Reproduction gate: n == 22312 and base 4-phase-mean
  sums == (0.911273, 0.832599, 2.099814, 3.197390, 0.677229), sum5y == 7.718304 +- 0.002
  (copied from `oc_k2placebo/results.json`). If the gate fails: STOP and report.
- Stop events: same VERBATIM kind/x recompute on the 2021-2026 perp 1m store
  (`data/raw/btc_intraday_20260924` + `data/raw/majors_intraday_20260924`; one coin in RAM
  at a time, float32, via heavy_slot) with O/sg from `oc_kronoshidden/bars_4h_4shift.parquet`
  opens + the replica sigma arithmetic; same (c, s) scope, same N = 7/3, same mult 1.25.
  Join (sym, shift=phase, T=bar open) exact + causal ffill fallback; missing -> 1.0.
- Per year y = 0..4 (anchors 2021..2025-09-24, year = [A_y, A_{y+1}), A_5 = 2026-09-24):
  base(y), boosted(y), realised_mean(y), norm(y) = boosted(y)/realised_mean(y),
  gain(y) = norm(y) - base(y). dSum5y = sum gains over 5 years. sum-half = count gain>0
  (HELP in >= 4/5 required). SECONDARY pass (pre-registered): dSum5y >= +0.273 AND
  sum-half >= 4/5 (assignment: "dSum5y >= +0.273 and sum-half >= 4/5"). Timing / block
  placebos reported per year (same per-(y,s,c) nulls, seeds + y = 0..4: timing 20261007+y,
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
  - Candidate leg: dip rung size x post-stop mult(T, shift, sym) (book byte-identical to G2;
    G2 dip gross cap 2.0 and every other G2 limit bind enforced inside the engine; gate costs
    maker 0.0002/taker 0.00055/stop-taker, longs pay 0.0001/8h, shorts 0; limit fill only on
    1m trade-through; nothing in first 5 min after a 4h close (win_start=5); stop-first).
    Mechanism = exact copy of oc_cboostctrl/run_engine.py (= oc_cascadeboost = v414 pipe v321,
    corr-aware inv sizes kd=1.7, bear books, risk budget 0.26*1*1.7, sleeve_gross_cap 2.0).
  - Exposure-matched constant control: CTRL_C = constant dip-budget multiplier per anchor year
    = candidate's realised mean dip-budget multiplier in that year from the candidate's own
    engine run (same average exposure, no post-stop timing; non-tradable decomposition control
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
  has NO fits, NO thresholds on returns — a fixed 1.25 after ledger stops; passes by
  construction); (2) beats the exposure control (CAND > CTRL_C on dev4 mean, else the gain is
  exposure); (3) Bybit leg (must not lose robustly / DD-breach on S5); (4) pre-sample leg
  (PRIMARY pass above). All four must hold to adopt; else REJECT / needs-prospective.

## Leakage / checks (stated in REPORT)

- Feature timing (stop events: exit minute tc from 1m data strictly before any boosted
  decision T' > tc; levels use O/sg available at T; truncation-tested in
  tests/test_oc_d_poststop.py), label windows (no labels fit anywhere), fit windows (no fits;
  1.25/N=7/N=3/seeds/BLOCK 42 all frozen ex-ante, never scanned; no statistic from any test
  year feeds any choice; pre-sample years never used for any fit), fill timing (live 16..238
  strict trade-through + stop-first inherited; perms reassign mults within (year, shift, coin)
  only). Gate costs inside the reused replica outcomes (maker 0.0002/taker 0.00055, adverse
  long funding 0.0001/8h). Coverage: disclose any skipped year / missing-mult count /
  unknown-kind count. Spot-vs-perp caveat on every pre-sample number (SPOT fills/exits, perp
  gate costs).

## Compute plan (resume-safe, heartbeat every 600 s)

- `poststop_rule.py`: pure helpers (`compute_sigma`, `find_fill`, `outcome_kind_x`,
  `boosted_mult`, `phase_mean_sums`) — no data access; unit-tested.
- `build_poststop_presample.py`: heavy spot-1m kind/x recompute (one coin at a time via
  heavy_slot) + per-(coin,shift) stop-event tables -> `poststop_mult_presample.parquet` +
  trigger counts + boosted shares (heartbeat 600 s).
- `compute_poststop_presample.py`: CPU-only join to the reused presample ledger + per-year
  sums/gains + 1000-perm timing/block placebos per (y,s,c) (V1 + V2) ->
  `tmp/poststop_presample.json` (heartbeat every 600 s). Stop-rate table from the same kinds
  -> folded into the same json (no second 1m pass).
- `build_poststop_2021.py` + `compute_poststop_2021.py`: same frozen rule on the 2021-2026
  perp 1m store + join to the reused k2placebo ledger -> `tmp/poststop_2021.json` (kind/x
  recompute via heavy_slot; join + placebos CPU-only; heartbeat).
- Engine (`run_engine.py` + `analyze.py` + `compute_ctrlC.py`) ONLY if PRIMARY + SECONDARY
  pass (else not written; REPORT states the stop). Bybit S5 only in that branch.
- Deliverables: PLAN.md (this file), poststop_rule.py, build/compute scripts,
  poststop_mult_*.parquet, tmp/*.json, results.json, REPORT.md,
  tests/test_oc_d_poststop.py (>=1 causality/truncation test + >=1 hand-checked synthetic case;
  `.venv/Scripts/python.exe -m pytest tests/test_oc_d_poststop.py -q`).
- No selection on the most recent year except the frozen engine branch (dev4 robust pick only;
  post-release year scored ONCE for the pick and REF).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the original row
  stays and the change is a disclosed extra row.)
