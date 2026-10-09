# oc_b7patient — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_b7patient.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, docs/opencode/OPENCODE_VF_COMMON.md read in full).
Implements idea #6 of `docs/opencode/IDEAS7_20261008.md` EXACTLY as written
(rule, the two pre-registered variants and frozen constants, data, leakage notes).
Write ONLY `research/tournament/oc_b7patient/` + `tests/test_oc_b7patient.py`.
Scratch only under `research/tournament/oc_b7patient/tmp/` (never the system temp
folder; never inspect /proc or folders outside the workspace). GIT IS READ-ONLY:
never stash/reset/checkout/restore/clean/rm/commit/switch/rebase/merge.
Progress print every 10 minutes (heartbeat every 600 s in long loops).
Engine / 1m work via `scripts/heavy_slot.py` (RAM tight: one job at a
time, one coin at a time, float32). Long jobs: nohup + log under tmp/.

## Why and the contamination protocol

Base = B7 of `research/tournament/oc_cascadeboost` (dip budget x1.5 for 7 days
after a cascade bar, oc_cascadedelay definition: |close-to-close log move| >
4 x trailing-90d sigma, market-wide per shift). oc_cascadeboost B7 is the dev4
robust pick (dev4 mean 6.74 vs G2 5.60) but CONTAMINATED (idea formed after the
delay replica covered all five years incl. the post-release year); pre-sample
(`oc_cboostpre`) shows B7 helps 3/4 unseen years but fails the COVID leg Y2020p
(gain -0.069, boosted stops +1.5pp), the same leg that breaks every tilt.
IDEAS7 #6 mech (rank 6, prior 9%): spreads recover intraday, depth takes weeks;
boosted fills exited on the normal clock sell into dumping tape (makerexit
lesson: 8% unfilled remainders sell deeper). Rule: give boosted fills room for
the snapback — wider TP (V1) or one more clock bar (V2) — with the 4sg stop kept.

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
Report which variant (if any) beats plain B7 on the clean pre-sample years
without losing the 2021-2024 gains.

## Variants (exactly two + two references; nothing else)

- REF = base dip replica unchanged (mult 1, exit mu=1.0, timeout at next 4h open),
  reproduction row only.
- B7 = plain dip budget x1.5 for 7 days after a cascade bar (mult 1.5 in window
  else 1.0), exit VERBATIM base (mu=1.0, timeout at T+240), VERBATIM
  oc_cascadeboost/oc_cboostpre (reference for head-to-head).
- V1 = B7 sizing (mult 1.5 in the 7d B7 window, market-wide per shift) PLUS
  patient TP for boosted fills only (assignment V1): boosted fills keep the 4sg
  stop (and 8sg backstop, timeout clock, costs, stop-first), TP 1.0sg -> 1.5sg
  (frozen; tp = lv*(1+1.5*sg) instead of lv*(1+1.0*sg)). Non-boosted fills use
  the base exit (mu=1.0). One-sided extension of winners only (NOT oc_partialtp
  which banked half EARLY and cut mean bps — disclosed difference).
- V2 = B7 sizing (same 1.5/7d window) PLUS patient timeout for boosted fills
  only (assignment V2): boosted fills that would timeout at the next 4h open
  (T+240) get timeout clocks x2 — ONE extension of exactly one more 4h bar to
  T+480, maker-first, taker fallback (frozen reading below). Boosted fills that
  exit via TP/stop/backstop on the first clock use the base outcome unchanged
  (same exit, same net; no second-bar data needed). Non-boosted fills always use
  the base exit.
- Book untouched (dip-only sizing+exit overlay; presample replica has no book
  leg; engine stage, if gated, keeps the book leg byte-identical to G2).
- No other variant, no ensemble, no threshold/window/TP/timeout tuning, no refit.

## Cascade trigger + boost window (frozen, causal, VERBATIM trigger arithmetic, no new data)

- Source pre-sample (read-only): `research/tournament/oc_presampletilt/bars_4h_presample.parquet`
  (4 syms BTCUSDT/ETHUSDT/BNBUSDT/XRPUSDT x shifts 0..3, ORIGIN 2020-01-01 + s h
  grid; per (sym, shift) series sorted by T = bar open). Only the `close` column
  is used. SOL absent pre-sample (union over available majors only — disclosed).
- Source 2021-2026 secondary (read-only): `research/tournament/oc_kronoshidden/bars_4h_4shift.parquet`
  (5 majors x shifts 0..3). Only `close` is used. B7 mults reused read-only from
  `oc_cascadeboost/boost_mult_4shift.parquet` (no rebuild; same grid/join).
- Pre-sample B7 mults reused read-only from
  `research/tournament/oc_cboostpre/boost_mult_presample.parquet` (mult_B7;
  same join). No new trigger build in this study (triggers VERBATIM
  oc_cascadedelay/oc_cascadeboost/oc_cboostpre; union counts 915 raw fires
  inherited, disclosed).
- "range > 4sg" reading (frozen, inherited): "range" = absolute close-to-close
  log move |r[i]| with r[i] = ln(C[i]/C[i-1]) (r[0] = NaN). REJECTED
  alternative: (H-L)-based range.
- Sigma (frozen): SIG[i] = std(ddof=1) of r[i-540 .. i-1] (540 returns = 90d x 6
  bars/day), min_periods 120 (else NaN). SIG[i] uses only bars with close_time
  <= T[i]; the tested return r[i] resolves at close_time[i] = T[i]+4h and is
  NEVER in its own sigma window — causal by construction, no self-inclusion.
- TRIGGER: bar i of (sym, shift) fires iff SIG[i] finite > 0 AND |r[i]| > 4.0 *
  SIG[i] (strictly greater; 4.0 frozen). Trigger close time tc = T[i] + 4h
  (known at tc). NaN SIG or non-finite closes -> never fires (conservative;
  counted and disclosed in the inherited parquet).
- BOOST WINDOW / BOOSTED FLAG (market-wide per shift, frozen, inherited): a dip
  decision at holding-bar open T on shift s is BOOSTED iff there EXISTS a union
  trigger (ANY available major, same shift s) with 0 < T - tc <= 7 days
  (strictly after the trigger close, up to and including +7 days). Same
  boosted(T, s) for all coins (sleeve budget is global). Boosted -> mult 1.5
  (sizing) AND patient exit applies (V1 TP1.5 / V2 extension); else mult 1.0 and
  base exit. Boosted flag from signal-time triggers only (never from
  placement-window data). Missing trigger history -> 1.0/base exit (inert).
- If the data named does not cover a year: disclose and skip that year for that
  variant (never impute). None expected.

## Patient exits (frozen, VERBATIM base race + one changed leg, existing 1m + state only)

Base exit (frozen, VERBATIM `build_ledger_presample.outcome_mu` at mu=1.0, same
as `oc_holdext` BASE): levels from lv = O(T)*(1-k*sg(T)) (k from ledger rung
{2.5,3,3.5,4,5}; O/sg from `bars_4h_presample` opens + VERBATIM `compute_sigma`
= pct_change rolling-360 min_periods-120 shift-1; disclosed caveat below):
sl = lv*(1-4*sg), bl = lv*(1-8*sg), tp(mu) = lv*(1+mu*sg) with mu=1.0 base.
Fill at FIRST f in live 16..238 with low(f) < lv (STRICT trade-through).
Race on minutes f+1..239 then timeout at 240 (o2 = 1m open at T+240):
backstop touch (first low <= bl) exits at min(bl,open(t)) taker; else TP touch
(first high > tp(mu), STRICT) exits at tp maker; else close5 stop (clock minutes
m with (m+1)%5==0 on the absolute offset-from-T clock, first close(m) <= sl)
exits at open(m+1) (or o2 if m=239) taker; else timeout at o2 taker + funding
0.0001 if (T+4h).hour in (0,8,16). Priority stop-first: backstop wins ties
(kb<=ks and kb<=kt); else TP wins only if strictly earlier (kt<ks); else stop;
else timeout. Same-minute stop+TP -> stop wins. Fees: fill maker 0.0002; TP leg
maker 0.0002 (total 2*maker on TP); stop/backstop/time legs taker 0.00055. Net
returns are fractions of lv. Minute-5 ban inherited via live window (nothing in
minutes 0..15; engine stage win_start=5 + trade-through + stop-first if run).

- V1 (patient TP, boosted fills only): same race with mu=1.5 for the TP level
  (tp = lv*(1+1.5*sg)); sl/bl/timeout clock/costs/priority unchanged. 4sg stop
  kept (assignment). Non-boosted fills mu=1.0. No second-bar data needed.
- V2 (patient timeout, boosted fills only, ONE extension, maker-first, taker
  fallback): if the BASE race (mu=1.0) ends in tp/stop/backstop (how != "time"),
  the V2 outcome IS the base outcome (same exit, same net; no second-bar data
  needed). A close5 signal at m=239 exiting at o2 counts as "stop", NOT
  extended (VERBATIM `oc_holdext`). If and only if BASE how == "time" (no TP,
  no close5 stop signal, no backstop touch in f+1..239), the rung keeps the SAME
  sl/bl/tp(mu=1.0) levels (frozen from the original lv and sg; backstop stays on
  as the catastrophic stop) and is evaluated over the next bar's minutes t in
  240..479 (offsets from T; same-coin H/L/C/O, NaN = no touch): backstop (first
  low <= bl) exits at min(bl,open(t)) taker; else TP (first high > tp, STRICT)
  exits at tp maker (maker-first); else close5 stop (clock minutes m in
  240..479 with (m+1)%5==0, same wall-clock grid, first close <= sl) exits at
  open(m+1) (or o3 if m=479) taker; else timeout at o3 = 1m open at T+480 taker
  (taker fallback). Same stop-first priority as BASE (backstop wins ties; TP
  only if strictly earlier than the stop; same-minute stop+TP -> stop). Same
  per-leg fees. Funding (longs pay 0.0001 per 8h settlement held): every
  extended exit held through the mid open T+240, so it pays 0.0001 if
  (T+240).hour in (0,8,16); an extended timeout at o3 additionally pays 0.0001
  if (T+480).hour in (0,8,16) (0, 1 or 2 x 0.0001 total). Intrabar BASE exits
  pay no funding (unchanged); BASE timeout/stop-at-240 pay the mid fund exactly
  as before. If second-bar data/exit missing (NaN o3 or window outside the
  store): V2 outcome = base timeout (no extension possible; conservative,
  counted as unknown-extension and disclosed; fills never dropped).
- Costs kept (gate): maker 0.0002, taker 0.00055, longs 0.0001/8h, strict
  trade-through, stop-first. Round-trip ~4-8bps bounds all effects (IDEAS7).
- Data for exits: existing 1m + state only (no new data): presample PRIMARY
  uses `data/raw/spot_1m_presample_20261007` (one coin in RAM at a time,
  float32); 2021-2026 SECONDARY uses `data/raw/btc_intraday_20260924` (BTC) +
  `data/raw/majors_intraday_20260924` (ETH/SOL/BNB/XRP) with the k2placebo
  ledger's O/sg sampling convention kept VERBATIM where applicable (see
  secondary script; disclosed). No Kaggle, no fetch.

## No fits (nothing estimated)

Threshold 4.0, windows (540/120), boost 1.5, N=7d, V1 TP 1.5sg, V2 one x2-clock
extension to T+480 with same sl/bl/tp, seeds (20261007+y / 20261008+y), BLOCK 42
are all frozen ex-ante round numbers/inherited conventions (TP/timeout from the
assignment, never scanned). No harness join, no quantiles, no embargo beyond
strict causality (trigger at tc uses only closes with close_time <= tc; boosted
flag uses only triggers with close < T; exits use only 1m up to the exit
minute). No statistic from any test year feeds any choice. Pre-sample years
were never used for any fit anywhere in this program (the rule has no fits).

## Frozen inputs (read-only, never edited, never refit)

- `research/tournament/oc_presampletilt/bars_4h_presample.parquet` (O/sg for
  levels via VERBATIM compute_sigma) + `tmp/ledger_presample.npz` +
  `tmp/bt_presample.npy` (D0+B1 replica; reproduction gate n == 9731, per-leg
  909/2986/3115/2721, base 4-phase-mean sums == (2.313362, 2.678870, 0.577643,
  0.297538) +- 1e-6 — variant-independent).
- `research/tournament/oc_cboostpre/boost_mult_presample.parquet` (B7 reference
  mults + boosted flags on the same grid; read-only head-to-head) +
  `tmp/stop_kinds.npz` (base-rule kinds in ledger order; read-only base stop
  split reference — V1/V2 kinds are recomputed, NOT reused).
- `data/raw/spot_1m_presample_20261007/` (presample 1m recompute; one coin at a
  time, float32; via heavy_slot).
- Secondary (read-only): `research/tournament/oc_kronoshidden/bars_4h_4shift.parquet`
  + `research/tournament/oc_cascadeboost/boost_mult_4shift.parquet` (B7 ref) +
  `research/tournament/oc_k2placebo/tmp/ledger.npz` + `tmp/bt_all.npy`
  (reproduction gate n == 22312, base sum5y == 7.718304 +- 0.002) +
  `data/raw/btc_intraday_20260924` + `data/raw/majors_intraday_20260924`.
- Engine (if gated): `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl` +
  `v421_result.json` row R2B1D17BFG2 (G2 baseline) + `research/tournament/oc_chronos/run_engine.py`
  mechanism (copied verbatim; only the dip mult lookup + boosted-exit branch change).

## PRIMARY — pre-sample replica + placebo + stop split (clean; 1m recompute + CPU replica)

- Per-fill patient outcomes (via heavy_slot, one coin at a time): for each of
  the 9731 ledger fills (phase=shift, T=bar open, coin BTC/ETH/BNB/XRP=0/1/2/3,
  rung k): O/sg from bars opens + VERBATIM compute_sigma; lv; fill f via VERBATIM
  find_fill (live 16..238 strict low trade-through); y_base (mu=1.0 ret + kind)
  via VERBATIM outcome_mu (with gate costs + settle funding); y_V1 (mu=1.5 ret +
  kind if boosted else y_base); y_V2 (extended ret + kind if boosted AND base
  how==time else y_base). Boosted flag = B7 window from the frozen cboostpre
  parquet (exact match on the shift grid, fallback to latest grid time <= T
  ffill causal; missing -> unboosted). Fills whose window/level cannot be
  rebuilt (missing 1m, NaN O/sg, no fill on rebuild): count as unknown-rebuild
  and disclosed; for sums fall back to ledger y10 (no patient effect,
  conservative; fills never dropped, n stays 9731); for stop rates use known
  kinds only. DISCLOSED CAVEAT (inherited): the ledger's O/sg were sampled as
  1m-open-at-T on its own grid while this recompute uses the frozen bars open
  series; the two agree whenever minute T is present (dense store) but may
  differ on gapped bars — the recompute is a like-for-like diagnostic with the
  fallback above (cboostpre stop recompute had 15 unknowns on the same join).
- Per pre-sample year y (Y2017/Y2018/Y2019/Y2020p; 4-phase means, same
  `phase_mean_sums` with n_years=4): base(y) from ledger y10, B7(y) from
  w*mult_B7*y10, V(y) from w*mult_B7*y_V (y_V = y_V1 or y_V2; same mults as B7),
  realised_mean(y) = mean mult_B7 over fills in y (same for B7/V1/V2),
  norm(y) = V(y)/realised_mean(y) (B7 norm likewise), gain_vs_base(y) =
  norm_V(y)-base(y), gain_vs_B7(y) = norm_V(y)-norm_B7(y) (isolates the exit
  effect: same ledger, same mults, same denominator; sizing cancels).
  "Helps vs base" iff gain_vs_base > 0; "beats B7" iff gain_vs_B7 > 0. Report n
  fills + boosted fill share + realised mean too. The COVID leg Y2020p is
  reported separately in its own row (it is the stress case: B7 gain -0.069,
  boosted stops +1.5pp there).
- Timing placebo per year (primary, joint null for the combined sizing+exit
  effect, inherited shape from oc_cboostpre): bar universe per (year y, shift s)
  = time-bars (s, T) on that shift's pre-sample grid with T in the year's
  [S_y, E_y) interval; per (y, s) the (mult, boosted-flag) pair series is
  permuted uniformly WITHIN (y, s) (1000 perms, seed 20261007+y with y=0..3;
  preserves per-shift boosted counts and cross-sym sharing); each fill maps to
  its (y, s) time-bar and takes the permuted mult AND the permuted flag's choice
  of y (y_pat if permuted-flag boosted else y_base, from its own precomputed
  pair). Percentile = 100*(1+#{perm<=actual})/1001; significant iff >= 95; perm
  norms use the ACTUAL realised-mean denominator. Block placebo per year: 42-bar
  chronological blocks per (y, s), permuted within (y, s) (seed 20261008+y;
  preserves window-length structure up to block edges). Same
  normalisation/percentile/significance. (For V1 the mult values are binary
  {1.0,1.5}; the joint permutation is over the binary flag; disclosed.)
- Boosted-fill stop/exit split (from the recomputed kinds, known kinds only):
  "hit the stop" = kind in {stop, backstop} (codes backstop=0/stop=2,
  unknown=-1; VERBATIM branch); base rate = stop-hit share over known-kind
  fills in the year (recomputed base kinds; cross-checked against read-only
  stop_kinds.npz, disclosed); boosted-patient rate = stop-hit share over boosted
  fills in the year under the variant's exit (V1 mu=1.5 kinds / V2 extended
  kinds); report delta (boosted-patient - base) per year + pooled. Also report
  TP share + timeout share as secondary rows (same split; V2 must cut timeouts
  mechanically — report the residual timeout rate). Rates over known kinds only;
  unknown-rebuild + unknown-extension counts disclosed.
- PRIMARY BEATER DEFINITION (frozen; the only gate to the engine): variant V
  beats plain B7 on the clean pre-sample years iff
  sum_{4y} norm_V(y) > sum_{4y} norm_B7(y) (strictly; normalised sums, like for
  like on the same 9731 fills). Supporting rows (helps-count vs base,
  timing-significant count, COVID-leg gain_vs_B7, pooled stop delta, timeout
  cut) are reported but do NOT change eligibility. If neither variant beats B7,
  STOP with no engine (negative result, valid).

## SECONDARY — 2021-2026 replica gate (contaminated, info only) + conditional engine

- Secondary replica (CPU + 1m recompute via heavy_slot, same method on the
  k2placebo ledger, 5 years 2021-2026, anchors 2021-09-24..2025-09-24): same
  join/method (B7 flags from the frozen cascadeboost parquet; y_base/y_V1/y_V2
  recomputed from btc/majors intraday 1m with the ledger's sampling convention
  kept VERBATIM where applicable, disclosed; fallback to ledger y10 on
  unknown-rebuild; fills never dropped) for V1/V2 with the B7 reference;
  per-year base/boosted/norm/gain_vs_base/gain_vs_B7 + 1000-perm timing/block
  placebos (seeds 20261007+y / 20261008+y, y=0..4; null = joint (mult, flag)
  permutation WITHIN (year, shift)). Report dSum5y vs base and vs B7 +
  sum-half counts, plus the assignment's replica gate rows (dSum5y >= +0.273,
  timing >= 95) labelled CONTAMINATED/INFO-ONLY. "Without losing the 2021-2024
  gains" is judged here as: dev4 (2021-2024) replica sum_V vs sum_B7 reported
  side by side (plus engine below if run). No selection is made here.
- Conditional 4-phase engine (ONLY for variants beating B7 on the PRIMARY
  pre-sample test, via heavy_slot, one job at a time; resume-safe caches
  tmp/runs_dev.pkl / tmp/runs_last.pkl; heartbeat every 600 s; nohup + tmp
  log): mechanism = exact copy of oc_cascadeboost/run_engine.py (= v414 pipe
  v321, corr-aware inv sizes kd=1.7, bear books, risk budget 0.26*1*1.7,
  sleeve_gross_cap G=2.0, win_start=5, gate costs maker 0.0002/taker 0.00055,
  longs 0.0001/8h, trade-through, minute-5 ban, stop-first) with TWO changes
  only: (i) dip rung size x mult_B7(T, shift) (1.5 in the 7d B7 window else 1.0,
  market-wide per (shift, T), VERBATIM B7); (ii) boosted-fill exit branch:
  V1 boosted rungs TP 1.5sg (same stop/backstop/timeout), V2 boosted timeout
  rungs extended one bar to T+480 with same sl/bl/tp (maker-first, taker
  fallback, funding as above). Book leg byte-identical to G2. Rows: REF + B7 +
  each eligible V variant (dev stage [2021-09-24, 2025-09-24); REF must
  reproduce v421 G2 dev years 0..3 R/DD to the digit, else STOP); last stage
  [DEV0, 2026-09-23) ONCE for REF + the dev4 robust pick only (robust pick on
  dev4 ONLY among DD <= 20 / no-losing-dev-year rows: prefer dev4 mean >= 5,
  then highest dev4 WORST-year, ties -> higher mean; post-release Y4 labelled
  scored-once DIAGNOSTIC). Metrics: per-year 4-phase reset %/mo + DD, dev4 geo
  mean, W, max yearly DD, losing count, 5y geo mean, full-path DD via v388.mix
  (max of marked/close), worst 1m-marked DD episode, win rates + fills/year +
  sized mean multiplier + boosted share + timeout share. If no variant is
  eligible, no engine rows are run at all.

## Leakage / checks (stated in REPORT)

- Feature timing (triggers: closes with close_time <= tc only; sigma window
  excludes the tested bar; boosted flag uses only triggers with close < T;
  exits use only 1m up to the exit minute; truncation-tested in
  tests/test_oc_b7patient.py), label windows (no labels fit anywhere), fit
  windows (no fits; frozen threshold/windows/boost/TP/timeout/seeds, no
  statistic from any test year feeds any choice), fill timing (replica live
  16..238 strict trade-through + stop-first inherited; engine win_start=5 +
  trade-through + stop-first if run; perms reassign (mult, flag) within
  (year, shift) only, seeds above). Gate costs inside the recomputed outcomes /
  engine. Coverage: disclose any skipped year / missing-mult count /
  unknown-rebuild / unknown-extension counts (fallback to ledger y10 keeps n).
  Spot-vs-perp caveat on every pre-sample number (SPOT fills/exits, perp gate
  costs).

## Compute plan (resume-safe, heartbeat every 600 s)

- `patient_rule.py`: pure helpers (`close_returns`, `trailing_sigma`,
  `triggers_of`, `boosted_mask`, `compute_sigma`, `find_fill`, `outcome_ret`
  (mu-param VERBATIM outcome_mu with costs+funding, returns kind+ret+x),
  `outcome_extended` (V2 one-bar extension VERBATIM holdext, returns kind+ret))
  — no data access; unit-tested. (Trigger arithmetic VERBATIM oc_cascadedelay
  `delay_rule.py` / oc_cascadeboost `boost_rule.py` / oc_cboostpre
  `cboostpre_rule.py` with WINDOW=540, MIN_PERIODS=120, THRESH=4.0, BOOST=1.5,
  B7_DAYS=7; exit VERBATIM `build_ledger_presample.outcome_mu` with MU_V1=1.5,
  M_SL=4.0, BACKSTOP=8.0, MAKER=0.0002, TAKER=0.00055, FUND=0.0001.)
- `compute_patient_outcomes.py`: 1m recompute (presample PRIMARY; via
  heavy_slot, one coin at a time, float32) -> `tmp/patient_outcomes.npz`
  (per-fill y_base/y_v1/y_v2/kind_base/kind_v1/kind_v2/boosted in ledger order
  + unknown counts; heartbeat every 600 s; resume-safe per-coin checkpoint).
- `compute_patient_presample.py`: CPU-only join + per-year sums/gains vs base
  AND vs B7 + 1000-perm joint timing/block placebos (time-bar within-(year,
  shift)) for V1 + V2 -> `tmp/patient_presample.json` (heartbeat every 600 s);
  stop/TP/timeout splits from the recomputed kinds -> same JSON (no extra 1m).
- `compute_patient_outcomes_4shift.py` + `compute_replica_patient.py`:
  secondary 2021-2026 outcomes + replica/placebo (same shapes as above, 5 years)
  -> `tmp/patient_outcomes_4shift.npz` + `tmp/replica_patient.json`
  (via heavy_slot for the 1m part; CPU for the replica part).
- `run_engine_patient.py` + `analyze_patient.py`: ONLY for PRIMARY-beating
  variants (same shape as oc_cascadeboost/run_engine.py + analyze.py, mult
  lookup = frozen B7 parquet + boosted-exit branch, market-wide per (shift, T);
  REF + B7 reproduction gates first; worst 1m-marked DD episode per row).
- Deliverables: PLAN.md (this file), patient_rule.py,
  compute_patient_outcomes.py, compute_patient_presample.py,
  (compute_patient_outcomes_4shift.py + compute_replica_patient.py for the
  secondary; run_engine_patient.py + analyze_patient.py only if gated),
  tmp/*.npz/json, results.json, REPORT.md,
  tests/test_oc_b7patient.py (>=1 causality/truncation test + >=1 hand-checked
  synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_b7patient.py -q`).

## Post-hoc log

- 2026-10-08 (after the PRIMARY replica outcome, before any engine outcome; no
  result row changed): V2 4-phase engine scoped to replica-only. Reason: the
  pipeline timeout is hardcoded in backend/history_tm.simulate (next-bar open);
  extending boosted timeouts to T+480 with mid+end funding and gross-cap
  interaction requires forking simulate, beyond the kw-only (sleeve_tp)
  override that V1 uses. Original rows kept; V2 replica rows unchanged; engine
  rows run for REF + B7 + V1 only (V2 raises NotImplementedError in
  run_engine_patient.py). Disclosed in REPORT.md.
