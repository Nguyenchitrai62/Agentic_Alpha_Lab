# oc_b7breaker — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_b7breaker.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, docs/opencode/OPENCODE_VF_COMMON.md read in full; idea #4 of docs/opencode/IDEAS7_20261008.md EXACTLY as written).
Write ONLY `research/tournament/oc_b7breaker/` + `tests/test_oc_b7breaker.py`. Scratch only under
`research/tournament/oc_b7breaker/tmp/` (never the system temp folder; never inspect /proc or
folders outside the workspace). GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/rm/
commit/switch/rebase/merge. Progress print every 10 minutes (heartbeat every 600 s in long loops).
Heavy 1m work (stop-kind recompute) and any 4-phase engine via `scripts/heavy_slot.py`
(`.venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_b7breaker --min-free-gb 2.0 -- <cmd...>`;
never `--leader`). RAM tight: one heavy job at a time, one coin's 1m slice in RAM at a time,
float32 where possible. Long jobs: nohup + log file under tmp/, poll the log.

## Why and the contamination label

`research/tournament/oc_cascadeboost`: B7 = dip budget x1.5 for 7 days after a cascade bar
(> 4 sigma 4h close-to-close move, oc_cascadedelay definition) is the dev4 robust pick
(mean 6.74 / WORST 2.96 / DD 17.92 vs G2 5.60 / 2.59 / 16.91; 5y 6.36). CONTAMINATION (stated in
the assignment and repeated here BEFORE any outcome): the idea was formed AFTER
oc_cascadedelay's replica had covered all five years incl. the post-release year, so
ANYTHING derived from the cascade results is contaminated for 2021-2026. The PRIMARY, clean
test is the pre-sample replica 2017 .. 2020-09-23 (oc_presampletilt + oc_cboostpre machinery:
cascade flags on pre-sample 4h closes, D0+B1 ledger) — unseen years nobody looked at when the
idea was formed. SECONDARY (contaminated): the 2021-2026 replica gate and, for variants that
beat B7 on the pre-sample test only, the 4-phase engine vs REF and B7. Post-release year
numbers are LABELLED DIAGNOSTIC, never clean evidence; only prospective paper could confirm.

## Base = B7 (frozen, inherited verbatim)

- Cascade bar definition VERBATIM oc_cascadedelay / oc_cascadeboost / oc_cboostpre (existing 4h
  closes only, no new data): per (sym, shift) series sorted by T = bar open (close_time = T+4h),
  r[i] = ln(C[i]/C[i-1]) (r[0]=NaN); SIG[i] = std(ddof=1) of r[i-540..i-1] (540 returns = 90d,
  min_periods 120, tested bar EXCLUDED, causal by construction); TRIGGER bar i fires iff
  SIG[i] finite > 0 AND |r[i]| > 4.0*SIG[i] (strict, 4.0 frozen); tc = T[i]+4h.
  NaN SIG / non-finite closes -> never fires. Union over available majors per shift.
- B7 window (market-wide per shift, frozen): dip decision at holding-bar open T on shift s is
  B7-BOOSTED iff EXISTS a union trigger (same shift s) with 0 < T - tc <= 7 days.
  Same boosted(T,s) for all coins. B7 mult = 1.5 if boosted else 1.0.

## Breaker rule (IDEAS7 #4 EXACTLY: frozen interpretation disclosed BEFORE any outcome)

- Mech (IDEAS7): crash legs announce themselves by cascade clustering; keep first-cascade edge,
  suspend levering the leg.
- Rule: if >= K cascades in trailing M days, suspend ALL boost for M days (base sizes).
- Frozen causal reading (contemporaneous gate, NOT latching — rejected alternative disclosed):
  at decision T on shift s, breaker count C(T,s) = number of UNION triggers (same shift s,
  same trigger set as B7) with tc <= T AND T - tc <= M days (i.e. tc in [T-Md, T], inclusive
  both ends). breaker_active(T,s) iff C(T,s) >= K. Final mult:
  mult_V(T,s) = 1.0 if breaker_active(T,s) else B7mult(T,s).
  So the breaker suspends the boost exactly while the trailing-M-day cascade count is >= K
  (which automatically lasts until the oldest of the K cascades ages out); it does NOT latch
  a fixed M-day suspension after each firing (rejected: extra state, not in the one-line rule).
- Inclusions disclosed: tc == T counts (0 <= diff; trigger closed exactly at T is known at T
  per "count <= close only"); upper bound inclusive (<= M days, mirroring B7's inclusive Nd);
  same-shift only (market-wide per shift, inherited); union over available majors only
  (SOL absent pre-sample). Missing trigger history (T before first computable bar) -> count 0,
  breaker inert, mult = B7 mult (counted and disclosed).
- Variants (exactly two, pre-registered, NOT oc_crashgate — that gated C2 TILT on 30d DD-depth;
  this gates BOOST on cascade COUNT):
  - V1: K=2 / M=14 (breaker if >= 2 cascades in trailing 14 days).
  - V2: K=3 / M=21 (breaker if >= 3 cascades in trailing 21 days).
- Book untouched (dip-only sizing overlay; presample replica has no book leg anyway).
- No other variant, no ensemble, no K/M/threshold/window tuning, no refit.

## Frozen inputs (read-only, never edited, never refit)

- Pre-sample (PRIMARY): `research/tournament/oc_presampletilt/bars_4h_presample.parquet`
  (4 syms BTC/ETH/BNB/XRP x shifts 0..3, ORIGIN 2020-01-01+s h grid; SOL absent — union over
  available majors only) + `oc_presampletilt/tmp/ledger_presample.npz` +
  `oc_presampletilt/tmp/bt_presample.npy` (D0+B1 replica; reproduction gate below).
- Secondary (contaminated): `research/tournament/oc_kronoshidden/bars_4h_4shift.parquet`
  (5 majors x shifts 0..3) + `research/tournament/oc_k2placebo/tmp/ledger.npz` +
  `bt_all.npy` (reproduction gate below).
- Stop recompute (primary): `data/raw/spot_1m_presample_20261007` (read-only spot 1m store).
- Engine (conditional, secondary only): `research/parallel/rounds/parallel-20260906-r2/v421/
  v421_runs.pkl` + `v421_result.json` row R2B1D17BFG2 + `research/tournament/oc_chronos/
  run_engine.py` mechanism (copied verbatim; only the dip mult lookup changes to the frozen
  breaker mult) — engine stage only, ONLY if a variant beats B7 on the pre-sample test.

## Pre-sample years + ledger (fixed, inherited VERBATIM from oc_presampletilt/oc_cboostpre)

- Years (bars with open in the interval; exits may realise after):
  Y2017 = [2017-10-16, 2018-01-01), Y2018 = [2018-01-01, 2019-01-01),
  Y2019 = [2019-01-01, 2020-01-01), Y2020p = [2020-01-01, 2020-09-01).
  Coins/warm-up inherited via the ledger (Y2017 BTC+ETH only incl. warm-up; Y2018+ BTC/ETH/
  BNB + XRP from 2018-07-03; SOL absent). No re-filtering here.
- Ledger (read-only, never rebuilt): reproduction gate n == 9731, per-leg 909/2986/3115/2721,
  base 4-phase-mean sums == (2.313362, 2.678870, 0.577643, 0.297538) +- 1e-6 (copied from
  oc_presampletilt/results.json presample V_RV6 per_year base — variant-independent).
  If the gate fails: STOP and report.
- B7 reference on pre-sample (reproduced, not refit): expected per-year base/boosted/norm/gain
  from oc_cboostpre/results.json (B7 gains +0.045913/+0.078085/+0.111004/-0.069459;
  B3 +0.026117/+0.048702/+0.297794/-0.136671). B7 mult grid is rebuilt here with verbatim
  arithmetic (union triggers must match oc_cboostpre counts: Y2017 8/12/9/11, Y2018 43/42/47/46,
  Y2019 46/53/49/57, Y2020p 31/39/31/29 per shift s0..s3) and asserted; any mismatch: STOP.
- Per fill join (phase=shift, T=bar open): exact match on the shift grid, fallback to latest
  grid time <= T (ffill, causal); missing -> B7 mult 1.0 then breaker applied (counted).

## PRIMARY — pre-sample replica + placebo + stop rate (clean test; BINDING for engine gating)

- Grids: `breaker_mult_presample.parquet` (shift, T, boosted_B7, mult_B7, breaker_V1, breaker_V2,
  mult_V1, mult_V2; T range = union of pre-sample shift grids). mult_V = 1.0 if breaker else
  mult_B7 (hence mult_V in {1.0,1.5}, V-subset of B7 boosted bars by construction).
- Per pre-sample year y (4-phase means, same phase_mean_sums with n_years=4):
  base(y), B7(y) [reproduced], V1(y), V2(y), realised_mean_V(y) (mean mult_V over fills in y),
  norm_V(y) = V(y)/realised_mean_V(y), gain_V_vs_base(y) = norm_V(y)-base(y),
  delta_V_vs_B7(y) = norm_V(y)-norm_B7(y). "Helps vs no boost" iff gain>0; "beats B7" per year
  iff delta>0. Report n fills + boosted (mult>1) fill share per variant/year (breaker REDUCES
  the boosted share vs B7 by construction — report the reduction).
- Timing placebo per year per variant (V1, V2 AND B7-reproduced): bar universe per (year y,
  shift s) = time-bars (s,T) on that shift's pre-sample grid with T in [S_y,E_y); mult series
  per (y,s) permuted uniformly WITHIN (y,s) (1000 perms, seed 20261007+y with y=0..3;
  preserves per-shift boosted counts and market-wide sharing); fills map to their (y,s)
  time-bar. Percentile = 100*(1+#{perm<=actual})/1001; significant iff >= 95; perm norms use
  the ACTUAL realised-mean denominator. Block placebo: 42-bar chronological blocks per (y,s),
  permuted within (y,s) (seed 20261008+y). Same normalisation/percentile/significance.
- "Beats plain B7 on the clean pre-sample years" (pre-registered, BINDING): variant V beats B7
  iff sum_{4y} delta_V_vs_B7 > 0 AND Y2020p delta_V_vs_B7 > 0 (must survive/improve the COVID
  leg to pass — IDEAS7: "must survive 2020p COVID leg"). Helps-count and timing reported
  alongside but NOT part of the beats rule (disclosed). Engine runs ONLY for beating variants;
  if neither beats B7: STOP with no engine (negative result, valid).
- Crash risk (IDEAS7 harness: "must not raise stops >+1pp pooled"): recompute exit kinds per
  fill VERBATIM oc_cboostpre compute_stop_presample (spot 1m, mu=1.0 outcome_kind, live
  16..238 strict trade-through, stop-first backstop>tp>stop; levels lv=O(T)*(1-k*sg(T)) with
  O/sg from bars_4h_presample + verbatim compute_sigma; same unknown-kind convention).
  Report per-year base stop rate, V1/V2 boosted stop rate + delta, TP share secondary row,
  pooled stop delta. Pooled delta > +1pp is a FAIL flag for that variant (reported; variant
  cannot be picked even if it beats B7 on gains — pre-registered safety condition).

## SECONDARY — 2021-2026 replica gate + conditional 4-phase engine (contaminated; diagnostic)

- Grids: `breaker_mult_4shift.parquet` (same breaker arithmetic on bars_4h_4shift; union
  triggers per shift must equal oc_cascadeboost 264/266/263/255 — asserted; B7 mults must match
  oc_cascadeboost boost_mult_4shift.parquet exactly — asserted; else STOP).
- Replica (CPU-only, reused k2placebo ledger n==22312, base sum5y==7.718304+-0.002 — asserted):
  per year base/boosted/realised_mean/norm for V1/V2 (+B7 reproduced) with the SAME
  time-bar-within-(year,shift) 1000-perm timing/block placebos (seeds 20261007+y/20261008+y).
  Gate (same as oc_cascadedelay/oc_cascadeboost, reported for each breaker variant):
  sum-half (boosted>=base in >=4/5y) PLUS dSum5y>=+0.273. This gate is CONTAMINATED (idea formed
  after seeing cascade years) — reported only; it does NOT gate adoption. "Without losing the
  2021-2024 gains" = variant's dev4 (2021-2024) replica/engine rows reported vs B7 (delta vs B7
  per dev year + dSum2021-2024 vs B7); a variant that beats B7 pre-sample but loses dev4 gains
  is reported as such (no adoption claim).
- Engine (ONLY for pre-sample-beating variants; else NO engine): mechanism = exact copy of
  oc_cascadeboost/run_engine.py (= oc_chronos pipe v321, corr-aware inv kd=1.7, bear books,
  risk budget 0.26*1*1.7, sleeve_gross_cap G=2.0, win_start=5, gate costs inside: maker 0.0002,
  taker 0.00055, longs pay 0.0001/8h shorts 0, trade-through, minute-5 ban, stop-first).
  Dip leg: rung size x mult_V(T,shift) (breaker mult, market-wide per (shift,T)); book leg
  byte-identical to G2. Rows: REF + B7 + each beating breaker variant. Stages: dev
  [2021-09-24,2025-09-24) first (REF must reproduce v421 G2 years 0..3 R/DD to the digit AND
  5y/full-path on full window else STOP); last [DEV0,2026-09-23) ONCE for REF + dev4 robust
  pick only (every Y4 number labelled scored-once DIAGNOSTIC — contaminated). Metrics/selection
  fixed: per-year reset %/mo + DD via reset_metric.year_reset; dev4 geo mean, W, max yearly DD,
  losing count; 5y geo mean; full-path DD via v388.mix (max of marked/close); worst 1m-marked DD
  episode per row; win rates + fills/year + sized mean multiplier + boosted share. Robust pick on
  dev4 ONLY among engine-run rows: DD<=20, no losing dev year; prefer dev4 mean>=5, then highest
  dev4 WORST-year, ties->higher mean. Post-release year scored ONCE, only for the pick (+REF),
  LABELLED DIAGNOSTIC. Via heavy_slot, one job at a time; resume-safe caches
  tmp/runs_dev.pkl / tmp/runs_last.pkl; heartbeat every 600 s; nohup + tmp log.

## No fits (nothing estimated)

Threshold 4.0, windows (540/120/min), B7 boost 1.5 / N=7, breaker K/M = (2,14)/(3,21), seeds
(20261007+y/20261008+y), BLOCK 42 are all frozen ex-ante round numbers/inherited conventions,
never scanned. No harness join, no quantiles, no embargo beyond strict causality (trigger at tc
uses only closes with close_time <= tc; breaker count uses only tc <= T). No statistic from any
test year feeds any choice. Pre-sample years were never used for any fit anywhere (the rule has
no fits at all).

## Leakage / checks (stated in REPORT)

- Feature timing (triggers: closes with close_time <= tc only; sigma excludes tested bar;
  B7 window strictly after tc; breaker count tc <= T only — count<=close; truncation-tested in
  tests/test_oc_b7breaker.py), label windows (none fit anywhere), fit windows (no fits; frozen
  integers, no statistic from any test year feeds any choice), fill timing (replica live
  16..238 strict trade-through + stop-first inherited; engine win_start=5 + trade-through +
  stop-first; perms reassign mults within (year, shift) only). Gate costs inside replica
  outcomes / engine. Coverage: disclose any skipped year / missing-mult count / unknown-kind
  count (none expected; early NaN-SIG bars never fire; missing mult -> B7 1.0 then breaker).

## Compute plan (resume-safe, heartbeat every 600 s)

- `breaker_rule.py`: pure helpers (`close_returns`, `trailing_sigma`, `triggers_of`,
  `boosted_mask`, `breaker_active`, `breaker_mult`, `compute_sigma`, `find_fill`,
  `outcome_kind`) — no data access; unit-tested. (Trigger/B7 arithmetic VERBATIM
  oc_cascadeboost boost_rule.py / oc_cboostpre cboostpre_rule.py with BOOST=1.5, B7_DAYS=7;
  breaker constants K1=2/M1=14, K2=3/M2=21; outcome logic VERBATIM outcome_mu kind branch.)
- `build_breaker_presample.py`: CPU-only pre-sample 4h closes -> `breaker_mult_presample.parquet`
  + trigger counts per (year, shift) + boosted/breaker shares (fast; prints progress; asserts
  union counts match oc_cboostpre + B7 mults match).
- `build_breaker_4shift.py`: CPU-only 2021-2026 4h closes -> `breaker_mult_4shift.parquet`
  (asserts union 264/266/263/255 + B7 match; SECONDARY, runs after primary outcome is logged —
  no outcome feeds any choice, order is compute hygiene only).
- `compute_breaker_presample.py`: CPU-only join to reused pre-sample ledger + per-year
  sums/gains/deltas + 1000-perm timing/block placebos for B7/V1/V2 -> `tmp/breaker_presample.json`
  (heartbeat every 600 s). PRIMARY outcome logged here; beats-B7 rule applied mechanically.
- `compute_stop_breaker.py`: spot-1m kind recompute VERBATIM oc_cboostpre (one coin at a time,
  float32, via heavy_slot) -> `tmp/stop_kinds.npz` + `tmp/stop_breaker.json` (heartbeat).
- `compute_breaker_4shift.py` (SECONDARY): CPU-only 2021-2026 replica + placebos for B7/V1/V2 ->
  `tmp/breaker_4shift.json`.
- `run_engine.py` + `analyze.py`: ONLY for pre-sample-beating variants (same shape as
  oc_cascadeboost/run_engine.py + analyze.py, mult lookup = frozen breaker parquet,
  market-wide per (shift,T); REF reproduction gate first; worst 1m-marked DD episode per row).
- Deliverables: PLAN.md (this file), breaker_rule.py, build_*.py, compute_*.py,
  (run_engine.py + analyze.py only if gated), breaker_mult_*.parquet, tmp/*.json,
  results.json, REPORT.md, tests/test_oc_b7breaker.py (>=1 causality/truncation test + >=1
  hand-checked synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_b7breaker.py -q`).

## Post-hoc log

- 2026-10-08: `build_breaker_4shift.py` union assertion clarified (no result row changed,
  no threshold/window touched): oc_cascadedelay/oc_cascadeboost report union counts OVER THE
  5 ANCHOR YEARS (tc >= 2021-09-24: 264/266/263/255); the shift grid starts 2020-08-01 for
  the 540-return warmup so full-grid union is larger (s0 338). Assertion now counts anchor-only.
  Found before any secondary outcome (primary pre-sample outcome already logged; unaffected).
