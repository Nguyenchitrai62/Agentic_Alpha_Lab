# oc_d_stagger — PLAN (pre-registered 2026-10-08, BEFORE any outcome — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_d_stagger.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md, `docs/opencode/IDEAS12_20261008.md` idea #5 read in full).
Write ONLY `research/tournament/oc_d_stagger/` + `tests/test_oc_d_stagger.py`. No other file is
edited (registry, ledgers, CONTINUOUS_RESEARCH.md, NEXT_AGENT.md, docs/, bot/, backend/,
scripts/, other workers' folders, ../Kronos, git state untouched;
GIT READ-ONLY: never stash/reset/checkout/restore/clean/rm/commit/switch/rebase/merge).
Scratch only under `research/tournament/oc_d_stagger/tmp/`. Progress print every 10 min
(heartbeat every 600 s in long loops). Heavy 1m work (stagger rebuilds, kind recomputes;
any engine) via `scripts/heavy_slot.py` (RAM tight: one job at a time, one coin's 1m slice
in RAM at a time, float32 where possible); joins + placebos are CPU-only.
Long jobs: nohup + log file under tmp/; never inspect /proc or folders outside the workspace.

## Idea #5 EXACTLY as written (IDEAS12 §5)

Mech: the minute-0 print noise misprices the rung level (Lokin-Yu fill-prob vs
post-fill-return lit); two independent prints halve placement noise with no chasing (both
placed once, expire 60min, never re-pegged).

Rule: split each rung 50/50 at the same frozen sigma price: V1 second print at minute 35,
V2 at minute 95 (first print minute 5; frozen times, minute-5 ban + trade-through maker
kept). Exposure-identical by construction. No fit.

Data/harness: 1m prints (spot pre-sample OK); replica PRIMARY, engine SECONDARY.
Effect: +0.0-0.03%/mo, DD flat. Prior 7%.

Crash: none (same sizes/stops/cap; only print times differ).

Closest CLOSED: oc_booktwo (BOOK two PRICES, 5.456<5.601 — this is DIP two TIMES one
price) / oc_earlystart (before-close shift, fragile 2023 -0.68 — this stays inside the
window) / oc_tapepeg (+0.069<gate, different anchor).

## Frozen variants (ONLY these two + reference, no tuning, no refit)

- REF = base dip replica unchanged (single print, live 16..238, mult 1.0), reproduction
  row only.
- V1: each rung split 50/50 at the SAME frozen sigma price lv: half A live offsets
  5..64 inclusive (60 bars; first print minute 5), half B live offsets 35..94 inclusive
  (60 bars; second print minute 35). Both expire after 60 min, placed once, never
  re-pegged.
- V2: half A live 5..64 inclusive (first print minute 5), half B live 95..154 inclusive
  (60 bars; second print minute 95). Same 60-min expiry, placed once, never re-pegged.
- Times 5 / 35 / 95, split 50/50, expiry 60 min, same-price rule are frozen ex-ante from
  IDEAS12, never scanned. No book leg (dip-only placement overlay; presample replica has
  no book leg anyway). No other variant, no ensemble, no refit.
- "Minute 5" = offset 5 after the holding-bar open T (the 1m bar opening at T+5m);
  minute-5 ban respected: nothing at offsets 0..4 can fill in any arm. Strict
  trade-through, maker fills, stop-first inherited (see below).

## Stagger rule (frozen, causal, 1m prints only for placement)

- Level (frozen, identical in all arms): lv(a,T,k) = O_a(T) * (1 - k*sg_a(T)), k in
  {2.5, 3.0, 3.5, 4.0, 5.0} (ledger rung 0..4), O/sg from the era's frozen bar grid
  (pre-sample: `bars_4h_presample` opens + VERBATIM `build_ledger_presample.compute_sigma`
  pct_change rolling-360/min_periods-120/shift-1; 2021-2026: VERBATIM
  `compute_placebo_dip` bar opens/sigma). Bars with non-finite O/sg<=0 skipped (no rungs
  that bar). The price is frozen at T: never re-pegged inside any window (unlike
  oc_b1deeper amendment; like oc_tapepeg frozen peg).
- Fills per half (frozen): resting limit BUY at lv. Half h fills at most once, at the
  FIRST offset f in its window with low(T+f) < lv (STRICT trade-through; touch == never
  fills). Fill price = lv, maker fee 0.0002. NaN 1m minutes never fill (inherited).
  Windows as Python slices on the 240-min bar array (off = minute index of T):
  A = [off+5 : off+65) (offsets 5..64), B_V1 = [off+35 : off+95) (35..94),
  B_V2 = [off+95 : off+155) (95..154). REF = [off+16 : off+239) (16..238, inherited).
- Weights (frozen, B1 at own fill minute): w_h = 0.5 * 1/(1+n(f_h)) with n = v399-exact
  correlation count at the half's OWN fill minute f_h (other majors b != a with finite
  O_b(T), finite C_b(T+f_h-1), finite sg_b(T) > 0 AND C_b <= O_b*(1-2.5*sg_b); closes use
  the 1m close at minute T+f_h-1 = last fully closed minute; own coin never counted;
  coins-present-only). Unfilled half contributes w = 0, y = 0 (no trade). Base w from the
  reused ledger (REF sums) / rebuilt base (2021 REF reproduction).
- Outcomes per filled half (frozen, VERBATIM `outcome_mu` at mu = 1.0): sl = lv*(1-4*sg),
  bl = lv*(1-8*sg), tp = lv*(1+1.0*sg); evaluated on minutes t in f_h+1..239 then timeout
  at 240 (next-bar open o2 = 1m open at T+240): backstop touch (first t with low(t) <= bl)
  exits at min(bl, open(t)) taker; else TP touch (first t with high(t) > tp, STRICT) exits
  at tp maker; else close5 stop (clock minutes m with (m+1)%5 == 0, first m with
  close(m) <= sl) exits at open(m+1) (or o2 if m = 239) taker; else timeout at o2 taker +
  funding 0.0001 if (T+4h).hour in (0,8,16). Priority stop-first: backstop wins ties
  (kb<=ks and kb<=kt); else TP only if strictly earlier (kt<ks); else stop; else timeout.
  Same-minute stop+TP -> stop. Fees: fill maker 0.0002; TP leg maker 0.0002 (2*maker on
  TP); stop/backstop/time legs taker 0.00055. Nets are fractions of lv. A half is kept
  iff its y09/y10/y11 are ALL finite (same paired-leg rule per half; missing exit price
  -> drop that half only). Halves scored independently (no cross-half pairing; same
  independence precedent as oc_tapepeg arms; comparability comes from the identical bar
  universe + gate on base sums).
- Exposure note (pre-registered): the 50/50 split at the same price is
  exposure-identical BY DESIGN (both halves sum to the base size when both fill at the
  same n). Realised exposure differs via fills (only-A / only-B / neither when the touch
  falls outside one half's 60-min window). There is NO mult normalisation: gain is the
  raw 4-phase-mean difference stagger - base, with the realised exposure ratio
  E(y) = sum(w_stag)/sum(w_base) + the fill split (both / only-A / only-B / neither, and
  base fill rate) reported as diagnostics. The engine-stage constant control isolates the
  exposure part (see ENGINE).

## Pre-sample years + ledger (fixed, inherited VERBATIM from oc_presampletilt/oc_cboostpre)

- Years (bars with open in the interval; exits may realise after):
  Y2017 = [2017-10-16, 2018-01-01), Y2018 = [2018-01-01, 2019-01-01),
  Y2019 = [2019-01-01, 2020-01-01), Y2020p = [2020-01-01, 2020-09-01).
  Coins/warm-up inherited via the bar grids (Y2017 BTC+ETH only incl. warm-up; Y2018+
  BTC/ETH/BNB + XRP from 2018-07-03; SOL absent). No re-filtering here.
- REF ledger (read-only, never edited, never rebuilt):
  `oc_presampletilt/tmp/ledger_presample.npz` + `oc_presampletilt/tmp/bt_presample.npy`
  (D0+B1 replica same as oc_k2placebo: RUNGS 2.5/3/3.5/4/5, live 16..238 strict
  trade-through, w=1/(1+n) coins-present-only, outcome_mu TP 0.9/1.0/1.1 close5+backstop,
  gate costs inside, stop-first, kept iff y09/y10/y11 ALL finite; NO budget/cap; SPOT
  fills/exits, perp gate costs — spot-vs-perp caveat on every number). Reproduction gate:
  n == 9731, per-leg 909/2986/3115/2721, and base 4-phase-mean sums ==
  (2.313362, 2.678870, 0.577643, 0.297538) +- 1e-6 (copied from
  `oc_presampletilt/results.json`). If the gate fails: STOP and report.
- Stagger legs (built HERE, stored HERE under `tmp/stagger_presample_V1.npz` /
  `tmp/stagger_presample_V2.npz` + kind arrays): VERBATIM presample core
  (`build_ledger_presample`: same ORIGIN 2020-01-01 + s h grid, same spot 1m store
  `data/raw/spot_1m_presample_20261007`, same compute_sigma, same warm-up, same
  years/coins, same n_vector DETECT_K = 2.5, same outcome branch, same costs/settle/
  stop-first, same kept rule per half), with ONLY the live windows split as above and
  weights halved per half. Resume-safe per-leg checkpoints in MY tmp only, via
  heavy_slot, one coin's 1m slice in RAM at a time, float32.
- Bar universe for stagger = the same (shift, T, coin, rung) universe the REF ledger was
  built on (same grids/sigma/warm-up/skips); stagger never adds a (bar, coin, rung) the
  base grid skips (O/sg non-finite -> no halves either).

## Replica + placebo (fixed)

- Per pre-sample year y (4-phase means, same `phase_mean_sums` as k2placebo/voltilt/
  chronos/cascadedelay/cascadeboost/cboostpre with n_years = 4 on ledger year 0..3):
  base(y) from the REF ledger, stag_V(y) = 4-phase-mean sum of half contributions
  (w_A*y_A + w_B*y_B at mu = 1.0), gain(y) = stag_V(y) - base(y). "Helps" in a year iff
  gain(y) > 0. Report n base fills, n stagger half-fills (A / B / both-halves bars),
  fill split, and realised exposure ratio E(y) too.
  dSum_pre = sum gains over 4 pre-sample years (diagnostic; the +0.273 gate is the
  2021-2026 secondary gate, not applied to pre-sample).
- Timing placebo per year (PRIMARY null: this IS a timing rule — placement times place
  half the size at specific minutes): B-half permutation WITHIN (year, shift) — the
  per-row B-half P&L (w_B*y_B, with unfilled B = 0) is permuted uniformly across rows in
  the same (y, s) (1000 perms, seed 20261007+y with y = 0..3; preserves per-shift B-leg
  marginal fill/P&L distribution and the market-wide A-leg; fills keep their A-half;
  perm stagger = A + permuted-B). Perm gains use the SAME base(y) (constant denominator;
  no normalisation). Percentile = 100*(1+#{perm<=actual})/1001; significant iff >= 95.
  This null breaks the link between a bar's 1m path position and its B-half outcome while
  keeping everything else fixed; it is CPU-only (no 1m rescan). DISCLOSED LIMIT: it does
  not sweep alternative B starts (a full start-time sweep needs 1m rescans and is not
  done); the V1-vs-V2 contrast (35 vs 95) is the direct start-time diagnostic.
- Block placebo per year: B-half P&L permuted in chronological 42-row blocks per
  (coin, shift) within (y, s) (seed 20261008+y; preserves local persistence up to block
  edges). Same percentile/significance.
- PRIMARY pass (pre-registered): gain > 0 in >= 3/4 pre-sample years AND Y2020p (COVID
  leg) gain > 0 (must survive the COVID leg) AND pooled stagger filled-half stop-rate
  delta <= +1pp (see crash section). Timing significance is REPORTED per year (this is a
  timing rule) but does not gate beyond the gains/stop checks (disclosed); helping years
  with timing < 95 are labelled weak-timing. If PRIMARY fails for both variants:
  SECONDARY replica is still computed (cheap CPU joins on the rebuilt stagger legs
  already built) for completeness, but ENGINE is only for a variant that helps on the
  pre-sample AND passes the secondary gate.
- Round-trip ~4-8 bps bounds all effects (stated in REPORT).

## Crash risk (fixed; stop-hit share of stagger filled halves vs base rate)

- "Hit the stop" = kind in {stop, backstop} at mu = 1.0 (close5 stop or backstop;
  TP/timeout otherwise), VERBATIM `outcome_mu` kind branch with stop-first ordering
  (backstop > tp > stop). Kinds are recorded DURING the stagger rebuild itself (same 1m
  arrays, per-half f_h; no second pass needed); base kinds use the VERBATIM recompute on
  REF fills (same levels lv from bars opens + compute_sigma, same live 16..238 find_fill,
  same kind branch; fills never added/dropped).
- Groups (frozen): base fills vs stagger filled halves (A + B pooled; plus A-only and
  B-only rows as diagnostics). Report per-year + pooled stop-hit shares, deltas
  (stagger - base), plus TP shares as a secondary row. "Skipped" diagnostic: base-filled
  rungs where BOTH halves miss (stagger skips a base winner/loser) — count + mean base y
  of skipped fills per year (opportunity-cost row, same spirit as oc_rungspace).
  FAIL if pooled stagger stop-given-fill rises > +1pp over base (b7breaker standard,
  pre-registered; same as oc_d_ddrank/oc_d_calendar/oc_d_riskparity).
- Fill windows: strict low trade-through in each half's window; NaN 1m gaps never
  fill/trigger/exit (inherited). Unknown windows (missing 1m) counted, rates over known
  kinds only.
- COVID leg separately: Y2020p stop deltas + skipped row reported on their own row;
  Y2020p gain must be > 0 (survival) per PRIMARY pass above.

## SECONDARY: 2021-2026 replica gate (fixed)

- REF ledger (read-only, never edited, never rebuilt): `oc_k2placebo/tmp/ledger.npz` +
  `oc_k2placebo/tmp/bt_all.npy` (oc_placebo_dip D0+B1 4-phase replica, 5 anchor years
  2021-09-24..2026-09-23; RUNGS 2.5-5, live 16..238 strict trade-through, B1 w=1/(1+n),
  gate costs inside, stop-first). Reproduction gate: n == 22312 and base 4-phase-mean
  sums == (0.911273, 0.832599, 2.099814, 3.197390, 0.677229), sum5y == 7.718304 +- 0.002
  (copied from `oc_k2placebo/results.json`). If the gate fails: STOP and report.
- Stagger legs (built HERE, `tmp/stagger_2021_V1.npz` / `tmp/stagger_2021_V2.npz`): VERBATIM
  `compute_placebo_dip.build_base` core (same START 2020-08-01 grid, same perp 1m stores
  `data/raw/btc_intraday_20260924` + `data/raw/majors_intraday_20260924`, same bar
  opens/sigma pct_change rolling-360/min_periods-120/shift-1, same TRADE_START/YEAR_END,
  same n_vector DETECT_K = 2.5, same costs/settle/stop-first, same kept rule per half),
  with ONLY the window split + halved weights above. Resume-safe per-(coin, phase)
  checkpoints in MY tmp only, via heavy_slot, one coin in RAM at a time, float32.
- Per year y = 0..4 (anchors 2021..2025-09-24, year = [A_y, A_{y+1}), A_5 = 2026-09-24):
  base(y), stag(y), gain(y) = stag(y) - base(y). dSum5y = sum gains over 5 years.
  sum-half = count gain > 0 (HELP in >= 4/5 required). SECONDARY pass (pre-registered):
  dSum5y >= +0.273 AND sum-half >= 4/5 (assignment: "dSum5y >= +0.273 and sum-half >=
  4/5"). B-half timing / block placebos reported per year (same nulls, seeds + y = 0..4:
  timing 20261007+y, block 20261008+y) but do not gate beyond the dSum/sum-half rule
  (disclosed).
- Exposure note: no mult normalisation (exposure-identical by design); E(y) + fill split
  reported; the constant control is engine-stage only.

## ENGINE (only for a variant that helps on the pre-sample AND passes the secondary gate)

- If and only if a variant achieves PRIMARY pass AND SECONDARY pass, run the 4-phase
  engine vs G2 for that variant (+ REF + exposure-matched constant control + Bybit S5
  row):
  - REF reproduction gate first: v421 R2B1D17BFG2 dev4 robust pick 5.41 %/month 4-phase
    reset metric, max yearly DD 16.91, full-path DD 16.82 (assignment: "reproduce 5.41 /
    16.91 / 16.82 first"; COMMON header: 5.41 %/mo reset, max yearly DD 16.91, full-path
    DD 16.82; hourly equity in `v421/v421_runs.pkl`; overlay A(t) = A(t-1)(1+r_bot(t)) +
    dSleeve(t)); reset metric `research/diagnostics/r2_decompose5/reset_metric.py`;
    full-path DD via `v388.mix`). If the gate fails: STOP and report.
  - Candidate leg: each dip rung split into two half-prints at the same engine rung price
    (book byte-identical to G2; G2 dip gross cap 2.0 and every other G2 limit bind
    enforced inside the engine; gate costs maker 0.0002/taker 0.00055/stop-taker, longs
    pay 0.0001/8h, shorts 0; limit fill only on 1m trade-through; nothing in first 5 min
    after a 4h close (win_start = 5); stop-first). Half sizes 0.5 x B1 at own fill minute;
    exits from each half's own fill (same D0 stops/TP/timeout/funding). Mechanism = exact
    copy of oc_cboostctrl/run_engine.py (= oc_cascadeboost = v414 pipe v321, corr-aware
    inv sizes kd = 1.7, bear books, risk budget 0.26*1*1.7, sleeve_gross_cap 2.0).
  - Exposure-matched constant control: CTRL_C = single print at the same rung price live
    over the UNION window (V1: offsets 5..94; V2: offsets 5..154) with FULL weight w
    (B1 at its fill; same price, same total size if filled, no split timing;
    non-tradable decomposition control by construction, labelled; never feeds any
    tradable choice). Share split exposure = (CTRL-REF)/(CAND-REF),
    timing = (CAND-CTRL)/(CAND-REF) when CAND > REF.
  - Bybit S5 leg: price-source switch only (Bybit 1m from 2021-11-15; y2021 short
    window); same candidate vs REF on Bybit-S5 dev4 under the robust rule (DD <= 20, no
    losing dev year, then highest WORST, ties -> mean) AND full-path DD <= 20
    (oc_confirmgate Leg1 definition).
  - Stages: dev [2021-09-24, 2025-09-24) for selection (robust rule on dev4 ONLY), last
    year 2025-09-24..2026-09-23 scored ONCE for the pick AND REF only (labelled). 5y +
    full-path DD reported. If PRIMARY or SECONDARY fails: NO ENGINE (valid negative
    result; REPORT states which gate failed and stops — no engine claim).
- Candidate-credibility checks (applied in REPORT): (1) sign-stable / fit-free rule (this
  rule has NO fits, NO thresholds on returns — frozen times/split/expiry only; passes by
  construction); (2) beats the exposure control (CAND > CTRL_C on dev4 mean, else the
  gain is window-length exposure); (3) Bybit leg (must not lose robustly / DD-breach on
  S5); (4) pre-sample leg (PRIMARY pass above). All four must hold to adopt; else REJECT
  / needs-prospective.

## Leakage / checks (stated in REPORT)

- Feature timing (stagger uses NO market features — the rung price uses O/sg available
  at T only; placement times are constants; halves fill only on 1m lows at offsets >= 5
  with strict trade-through; exits use minutes > f_h only; truncation-tested in
  tests/test_oc_d_stagger.py), label windows (no labels fit anywhere; exits mechanical),
  fit windows (no fits; 5/35/95 starts, 60-min expiry, 50/50 split, seeds
  20261007/20261008, BLOCK 42 all frozen ex-ante, never scanned; no statistic from any
  test year feeds any choice; pre-sample years never used for any fit), fill timing
  (strict trade-through + minute-5 ban + stop-first inherited; perms reassign B-half P&L
  within (year, shift) only). Gate costs inside all rebuilt outcomes (maker
  0.0002/taker 0.00055, adverse long funding 0.0001/8h). Coverage: disclose any skipped
  year / rebuilt-vs-ledger base delta / unknown-kind count. Spot-vs-perp caveat on every
  pre-sample number (SPOT fills/exits, perp gate costs).

## Compute plan (resume-safe, heartbeat every 600 s)

- `stagger_rule.py`: pure helpers (`windows_V1`, `windows_V2`, `find_fill_in`,
  `n_at`, `outcome_mu` VERBATIM replica branch + kind, `phase_mean_sums`) — no data
  access; unit-tested.
- `build_stagger_presample.py`: heavy spot-1m stagger rebuild (VERBATIM presample core +
  split windows/halved weights; per-leg checkpoints; base REF reproduction gate first) ->
  `tmp/stagger_presample_V1.npz` + `tmp/stagger_presample_V2.npz` (+ kinds + base-check).
  Via heavy_slot, one coin in RAM at a time, float32.
- `compute_stagger_presample.py`: CPU-only REF join + per-year base/stag/gain/E/fill-split
  + 1000-perm B-half timing/block placebos (V1 + V2) -> `tmp/stagger_presample.json`.
- `compute_kind_presample.py`: folded into the rebuild (kinds recorded per half) + base
  REF kind recompute (VERBATIM) -> stop/skipped tables in `tmp/stagger_presample.json`.
- `build_stagger_2021.py` + `compute_stagger_2021.py`: same frozen split on the perp 1m
  stores + join to the reused k2placebo REF (reproduction gate first) ->
  `tmp/stagger_2021.json` (CPU placebos; heavy rebuild via heavy_slot).
- Engine (`run_engine.py` + `analyze.py` + `compute_ctrlC.py`) ONLY if PRIMARY +
  SECONDARY pass (else not written; REPORT states the stop). Bybit S5 only in that
  branch.
- Deliverables: PLAN.md (this file), stagger_rule.py, build/compute scripts,
  tmp/*.json/npz, results.json, REPORT.md,
  tests/test_oc_d_stagger.py (>=1 causality/truncation test + >=1 hand-checked synthetic
  case; `.venv/Scripts/python.exe -m pytest tests/test_oc_d_stagger.py -q`).
- No selection on the most recent year except the frozen engine branch (dev4 robust pick
  only; post-release year scored ONCE for the pick and REF).

## Post-hoc log

- 2026-10-08: `compute_stop_presample.py` first run thrashed (fills processed in
  ledger order = coin-interleaved, so the spot 1m parquet was reloaded per fill
  group; killed via tmp/kill_stop.ps1, regrouped loop by coin = one 1m load per
  coin). Same find_fill/outcome arithmetic, no threshold/window touched; the rerun
  reproduces oc_cboostpre kinds exactly (5729/3445/480/62/15). No result row changed.
- 2026-10-08: disclosed EXTRA diagnostic rows added in analyze/REPORT (exposure-
  normalised stag/E - base per year + helps counts). Frozen raw-gain rows stay the
  primary gate rows; extras never gate.
