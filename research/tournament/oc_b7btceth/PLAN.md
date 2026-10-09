# oc_b7btceth — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_b7btceth.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, docs/opencode/OPENCODE_VF_COMMON.md read in full).
Implements idea #5 of `docs/opencode/IDEAS7_20261008.md` EXACTLY as written
(rule, the two pre-registered variants and frozen constants, data, leakage notes).
Write ONLY `research/tournament/oc_b7btceth/` + `tests/test_oc_b7btceth.py`.
Scratch only under `research/tournament/oc_b7btceth/tmp/` (never the system temp
folder; never inspect /proc or folders outside the workspace). GIT IS READ-ONLY:
never stash/reset/checkout/restore/clean/rm/commit/switch/rebase/merge.
Progress print every 10 minutes (heartbeat every 600 s in long loops).
Engine / 1m work (if gated) via `scripts/heavy_slot.py` (RAM tight: one job at a
time, one coin at a time, float32). Long jobs: nohup + log under tmp/.

## Why and the contamination protocol

Base = B7 of `research/tournament/oc_cascadeboost` (dip budget x1.5 for 7 days
after a cascade bar, oc_cascadedelay definition: |close-to-close log move| >
4 x trailing-90d sigma, market-wide per shift). oc_cascadeboost B7 is the dev4
robust pick (dev4 mean 6.74 vs G2 5.60) but CONTAMINATED (idea formed after the
delay replica covered all five years incl. the post-release year); pre-sample
(`oc_cboostpre`) shows B7 helps 3/4 unseen years but fails the COVID leg Y2020p
(gain -0.069, boosted stops +1.5pp), the same leg that breaks every tilt.
IDEAS7 #5 mech (rank 5, prior 11%): toxicity heterogeneity — BTC passive fills
during liq intensity earn forward marks; alts thinner, slower depth recovery
(XRP the only non-contracting exception off a low base). Rule: B7 boost applies
to BTC+ETH rungs only (V1) / BTC only (V2); other coins base size in window.

CONTAMINATION PROTOCOL (from the assignment, repeated here BEFORE any outcome):
anything derived from the cascade results is contaminated for 2021-2026. The
PRIMARY, clean test is the pre-sample replica 2017 .. 2020-09-23
(`oc_presampletilt` + `oc_cboostpre` machinery: cascade flags on pre-sample 4h
closes, D0+B1 ledger): per-year normalised gain vs B7 AND vs no boost, timing
placebo pct, boosted-fill stop rate, and the COVID leg (2020p) separately.
SECONDARY: the 2021-2026 replica gate (contaminated, info only) and, for
variants that beat B7 on the pre-sample test, the 4-phase engine vs REF and B7
(dev4 robust pick, 5y, full-path DD; post-release year labelled diagnostic).
No selection is made on 2021-2026 or on the post-release year in this study;
the pre-sample beater definition below is the only gate to the engine.

## Variants (exactly two + two references; nothing else)

- REF = base dip replica unchanged (mult 1), reproduction row only.
- B7 = plain dip budget x1.5 for 7 days after a cascade bar (mult 1.5 in window
  else 1.0), VERBATIM oc_cascadeboost/oc_cboostpre (reference for head-to-head).
- V1 = BTC+ETH-only B7 (assignment V1): mult 1.5 iff the bar is B7-boosted AND
  the fill's coin is BTC or ETH; all other coins mult 1.0 in the window.
- V2 = BTC-only B7 (assignment V2): mult 1.5 iff the bar is B7-boosted AND the
  fill's coin is BTC; all other coins mult 1.0 in the window.
- Coin sets frozen ex-ante (never pick best coin ex-post): pre-sample ledger
  coins BTC/ETH/BNB/XRP = 0/1/2/3 (inherited `oc_presampletilt` MAJORS4 order),
  so V1 mask = {0,1}, V2 mask = {0}. Secondary 2021-2026 ledger coins
  BTC/ETH/SOL/BNB/XRP = 0/1/2/3/4 (inherited `oc_k2placebo` MAJORS order), so
  V1 mask = {0,1}, V2 mask = {0} (SOL/BNB/XRP base size in window).
- Book untouched (dip-only sizing overlay; presample replica has no book leg;
  engine stage, if gated, keeps the book leg byte-identical to G2).
- No sizing-model change (NOT oc_corrbudget/governor: coin mask only, no
  budget, cap, correlation or threshold change). No other variant, no ensemble,
  no threshold/window tuning, no refit.

## Cascade trigger + B7 window + coin mask (frozen, causal, VERBATIM arithmetic, no new data)

- No new trigger build in this study: the B7 window is REUSED read-only from
  the frozen parquets (`oc_cboostpre/boost_mult_presample.parquet` pre-sample,
  `oc_cascadeboost/boost_mult_4shift.parquet` secondary). Trigger arithmetic
  is VERBATIM oc_cascadedelay/oc_cascadeboost/oc_cboostpre (closes-only
  |r| > 4*SIG(540,min120), tc = T+4h, union over available majors per shift,
  window (tc, tc+7d] market-wide per shift); `b7btceth_rule.py` re-implements
  the same pure helpers for unit tests only and asserts identical constants
  (THRESH 4.0, WINDOW 540, MIN_PERIODS 120, BOOST 1.5, BOOST_DAYS 7).
- COIN MASK (frozen, this study's only new logic): per fill with ledger coin
  c and B7 time-bar mult m_B7(T, shift) in {1.0, 1.5}:
  mult_V1 = 1.5 iff m_B7 == 1.5 AND c in MASK_V1 else 1.0;
  mult_V2 = 1.5 iff m_B7 == 1.5 AND c in MASK_V2 else 1.0.
  MASK_V1 = {0,1} (BTC,ETH) on both ledgers; MASK_V2 = {0} (BTC) on both.
  Mask is static per coin (known at signal time; no lookahead).
- BOOSTED FLAG (frozen, for reporting + stop split only): boosted_V = mult_V
  == 1.5 (exact; mults take values in {1.0, 1.5} only).
- Join (phase=shift, T=bar open): exact match on the shift grid, fallback to
  latest grid time <= T (ffill, causal); missing -> 1.0 (counted and disclosed).
  Same join for V1, V2 and the B7 reference.
- Unit-tested: hand-checked synthetic trigger/sigma/boost/mask arithmetic +
  causality/truncation test (triggers recomputed from bars truncated at a cut
  date -> identical on kept prefix; mask is per-coin static so truncation
  cannot change it).
- If the data named does not cover a year: disclose and skip that year for that
  variant (never impute). None expected.

## No fits (nothing estimated)

Threshold 4.0, windows (540/120), boost 1.5 x 7d, coin masks {0,1}/{0},
seeds (20261007+y / 20261008+y), BLOCK 42 are all frozen ex-ante round numbers /
inherited conventions (masks from the assignment, never scanned). No harness
join, no quantiles, no embargo beyond strict causality (trigger at tc uses only
closes with close_time <= tc; mask uses only the fill's own coin). No statistic
from any test year feeds any choice. Pre-sample years were never used for any
fit anywhere in this program (the rule has no fits at all).

## Frozen inputs (read-only, never edited, never refit)

- `research/tournament/oc_presampletilt/bars_4h_presample.parquet` (trigger
  audit only; B7 windows reused from the frozen parquet below).
- `research/tournament/oc_presampletilt/tmp/ledger_presample.npz` +
  `tmp/bt_presample.npy` (D0+B1 replica; reproduction gate n == 9731, per-leg
  909/2986/3115/2721, base 4-phase-mean sums == (2.313362, 2.678870, 0.577643,
  0.297538) +- 1e-6 — variant-independent).
- `research/tournament/oc_cboostpre/boost_mult_presample.parquet` (B7 reference
  mults on the same grid; read-only head-to-head AND the window source for the
  coin mask) + `tmp/stop_kinds.npz` (per-fill exit kinds in ledger order;
  read-only stop split — NO new 1m work) + `results.json` (frozen B7 norms
  for the reproduction gate).
- `research/tournament/oc_kronoshidden/bars_4h_4shift.parquet` (secondary audit
  only; windows reused from the frozen parquet below).
- `research/tournament/oc_k2placebo/tmp/ledger.npz` + `tmp/bt_all.npy`
  (secondary D0+B1 ledger; reproduction gate n == 22312, base sum5y ==
  7.718304 +- 0.002) + `research/tournament/oc_cascadeboost/boost_mult_4shift.parquet`
  (secondary B7 reference + window source; read-only).
- `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl` +
  `v421_result.json` row R2B1D17BFG2 (G2 baseline — engine stage only, if gated)
  + `research/tournament/oc_chronos/run_engine.py` mechanism (copied verbatim;
  only the dip mult lookup gains the coin mask — engine stage only, if gated).

## PRIMARY — pre-sample replica + placebo + stop split (clean; CPU-only, no engine)

- Per pre-sample year y (Y2017/Y2018/Y2019/Y2020p; 4-phase means, same
  `phase_mean_sums` with n_years=4): base(y), boosted_V(y), realised_mean_V(y)
  (mean mult over fills in y), norm_V(y) = boosted_V(y)/realised_mean_V(y),
  gain_vs_base_V(y) = norm_V(y) - base(y), gain_vs_B7_V(y) = norm_V(y) -
  norm_B7(y) (norm_B7 from the same-ledger B7 join). "Helps vs base" in a year
  iff gain_vs_base > 0; "beats B7" in a year iff gain_vs_B7 > 0. Report n fills
  + boosted fill share + realised mean too. The COVID leg Y2020p is reported
  separately in its own row (it is the stress case: B7 gain -0.069 there).
- Per-coin dSum (assignment harness): per coin c, phase-mean sums base_c(y),
  boosted_Vc(y) (fills of coin c only, same phase averaging), realised means
  and normalised gains; pooled over the 4 years. Shows WHERE the masked edge
  lives (BTC/ETH vs alts) without any ex-post coin picking.
- Timing placebo per year (primary, inherited verbatim null adapted to the
  mask, pre-registered): bar universe per (year y, shift s) = time-bars (s, T)
  on that shift's pre-sample grid with T in the year's [S_y, E_y) interval;
  the UNDERLYING B7 mult series per (y, s) permuted uniformly WITHIN (y, s)
  (1000 perms, seed 20261007+y with y = 0..3; preserves per-shift boosted
  counts and cross-sym sharing); the variant mult for a fill = permuted B7
  mult at its (y, s) time-bar masked by its coin (1.5 iff permuted B7 == 1.5
  AND coin in mask else 1.0). Percentile = 100*(1+#{perm<=actual})/1001;
  significant iff >= 95; perm norms use the ACTUAL variant realised-mean
  denominator. Block placebo per year: 42-bar chronological blocks per (y, s),
  permuted within (y, s) (seed 20261008+y), same masking/normalisation.
  Rationale (disclosed): permuting the underlying market-wide B7 window then
  applying the deterministic coin mask is the correct null — it preserves the
  mask structure and tests cascade TIMING given the mask.
- Boosted-fill stop rate (no new 1m; reuse read-only `stop_kinds.npz` kinds in
  ledger order): "hit the stop" = kind in {stop, backstop} (verbatim mu=1.0
  branch, codes backstop=0/stop=2, unknown=-1); base rate = stop-hit share over
  known-kind fills in the year; boosted rate = stop-hit share over boosted
  (mult_V == 1.5) fills in the year (per variant V1/V2, plus B7 reference row);
  report delta (boosted - base) per year + pooled. Rates over known kinds only;
  unknown count disclosed (15 inherited).
- PRIMARY BEATER DEFINITION (frozen; the only gate to the engine): variant V
  beats plain B7 on the clean pre-sample years iff
  sum_{4y} norm_V(y) > sum_{4y} norm_B7(y) (strictly; normalised sums, like for
  like on the same 9731 fills). Supporting rows (helps-count vs base,
  timing-significant count, COVID-leg gain_vs_B7, pooled stop delta, per-coin
  dSum) are reported but do NOT change eligibility. If neither variant beats
  B7, STOP with no engine (negative result, valid).

## SECONDARY — 2021-2026 replica gate (contaminated, info only) + conditional engine

- Secondary replica (CPU-only): same coin-mask join/method on the k2placebo
  ledger (5 years 2021-2026, anchors 2021-09-24..2025-09-24) for V1/V2 with the
  B7 reference from the frozen cascadeboost parquet; per-year base/boosted/
  norm/gain_vs_base/gain_vs_B7 + per-coin dSum + 1000-perm timing/block
  placebos (seeds 20261007+y / 20261008+y, y = 0..4; null = permuted B7 window
  WITHIN (year, shift) + deterministic coin mask). Report dSum5y vs base and
  vs B7 + sum-half counts. This leg is CONTAMINATED (idea derived from cascade
  results covering these years): info only, never a selection basis. "Without
  losing the 2021-2024 gains" is judged here as: dev4 (2021-2024) replica
  sum_V vs sum_B7 reported side by side (plus engine below if run).
- Conditional 4-phase engine (ONLY for variants beating B7 on the PRIMARY
  pre-sample test, via heavy_slot, one job at a time; resume-safe caches
  tmp/runs_dev.pkl / tmp/runs_last.pkl; heartbeat every 600 s; nohup + tmp
  log): mechanism = exact copy of oc_cascadeboost/run_engine.py (= v414 pipe
  v321, corr-aware inv sizes kd=1.7, bear books, risk budget 0.26*1*1.7,
  sleeve_gross_cap G=2.0, win_start=5, gate costs maker 0.0002/taker 0.00055,
  longs 0.0001/8h, trade-through, minute-5 ban, stop-first). Rows: REF + B7 +
  each eligible V variant (dev stage [2021-09-24, 2025-09-24); REF must
  reproduce v421 G2 dev years 0..3 R/DD to the digit, else STOP); last stage
  [DEV0, 2026-09-23) ONCE for REF + the dev4 robust pick only (robust pick on
  dev4 ONLY among DD <= 20 / no-losing-dev-year rows: prefer dev4 mean >= 5,
  then highest dev4 WORST-year, ties -> higher mean; post-release Y4 labelled
  scored-once DIAGNOSTIC). Engine dip mult: rung size x mult_V(T, shift, coin)
  (1.5 iff B7-boosted AND coin in mask else 1.0; coin index = engine cols
  position mapped to BTC/ETH/SOL/BNB/XRP). Metrics: per-year 4-phase reset
  %/mo + DD, dev4 geo mean, W, max yearly DD, losing count, 5y geo mean,
  full-path DD via v388.mix (max of marked/close), worst 1m-marked DD episode,
  win rates + fills/year + sized mean multiplier + boosted share. If no variant
  is eligible, no engine rows are run at all.

## Leakage / checks (stated in REPORT)

- Feature timing (B7 windows: closes with close_time <= tc only, SIG window
  excludes the tested bar, window strictly after tc; mask is a static per-coin
  flag known at signal time; truncation-tested in
  tests/test_oc_b7btceth.py), label windows (no labels fit anywhere), fit
  windows (no fits; frozen threshold/windows/boost/masks/seeds, no statistic
  from any test year feeds any choice), fill timing (replica live 16..238
  strict trade-through + stop-first inherited; engine win_start=5 +
  trade-through + stop-first if run; perms reassign underlying B7 mults within
  (year, shift) only, seeds above, mask applied deterministically). Gate costs
  inside the reused replica outcomes / engine. Coverage: disclose any skipped
  year / missing-mult count / unknown-kind count (none expected beyond the
  inherited 15 unknowns). Spot-vs-perp caveat on every pre-sample number (SPOT
  fills/exits, perp gate costs).

## Compute plan (resume-safe, heartbeat every 600 s)

- `b7btceth_rule.py`: pure helpers (`close_returns`, `trailing_sigma`,
  `triggers_of`, `boosted_mask`, `coin_mult` / `apply_mask`, `anchor_of`) — no
  data access; unit-tested. (Trigger arithmetic VERBATIM oc_cascadedelay
  `delay_rule.py` / oc_cascadeboost `boost_rule.py` / oc_cboostpre
  `cboostpre_rule.py` with BOOST = 1.5, BOOST_DAYS = 7; MASK_V1 = {0,1},
  MASK_V2 = {0}.)
- `compute_boost_presample_btceth.py`: CPU-only join to the reused presample
  ledger (B7 window from the frozen cboostpre parquet + deterministic coin
  mask) + per-year sums/gains vs base AND vs B7 + per-coin dSum + 1000-perm
  timing/block placebos (permuted B7 window within-(year,shift) + mask) for
  V1 + V2 -> `tmp/boost_presample_btceth.json` (heartbeat every 600 s); stop
  split from read-only `stop_kinds.npz` -> same JSON (no 1m work).
- `compute_replica_gate_btceth.py`: secondary 2021-2026 replica/placebo (same
  shapes as above, 5 years, k2placebo ledger + frozen cascadeboost parquet)
  -> `tmp/replica_btceth.json` (CPU-only).
- `run_engine_btceth.py` + `analyze_btceth.py`: ONLY for PRIMARY-beating
  variants (same shape as oc_cascadeboost/run_engine.py + analyze.py, mult
  lookup = frozen B7 parquet + coin mask per (shift, T, coin); REF + B7
  reproduction gates first; worst 1m-marked DD episode per row in analyze).
- Deliverables: PLAN.md (this file), b7btceth_rule.py,
  compute_boost_presample_btceth.py, compute_replica_gate_btceth.py,
  (run_engine_btceth.py + analyze_btceth.py only if gated),
  tmp/*.json, results.json, REPORT.md,
  tests/test_oc_b7btceth.py (>=1 causality/truncation test + >=1 hand-checked
  synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_b7btceth.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the original row
  stays and the change is a disclosed extra row).
