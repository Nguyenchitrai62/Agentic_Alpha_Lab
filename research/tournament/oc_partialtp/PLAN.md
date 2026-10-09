# oc_partialtp PLAN (pre-registered BEFORE any outcome is computed, 2026-10-08 — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_partialtp.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md, IDEAS6_20261008.md idea #2 read in full, CLOSED rows cited read first).
Write ONLY `research/tournament/oc_partialtp/` + `tests/test_oc_partialtp.py`. Scratch only under
`research/tournament/oc_partialtp/tmp/`. GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/
rm/commit/switch/rebase/merge. Engine / heavy 1m work via `scripts/heavy_slot.py` (one job at a time,
one coin at a time, float32). Long jobs: nohup + log under tmp/, poll the log; never inspect /proc or
folders outside the workspace. Progress print every 10 minutes. PLAN.md frozen BEFORE any outcome.

## Why (IDEAS6_20261008.md idea #2, rank 2 — quoted, not refit)

Mech: `oc_ladderfill` 8% stops erase ~50 TPs each; banking half early funds the tail, keeps proven
1.0sg runner. STRUCTURE not faster TP. Rule: stop 4sg + runner 1.0sg kept; sell HALF at P on maker
limit (stop-first on remainder). V1 P=0.5sg; V2 P=0.75sg. Sizes/rungs unchanged. Data: existing
1m+ledgers. Harness: replica+gate then engine. Effect: +0.0-0.10%/mo, DD -0.0-0.4, win up.
Prior 13%. Leak: partial from fill price only; trade-through+minute-5; no re-peg.
CLOSED rows read first: `oc_tpbyn` (PLAN/REPORT/analyze_tpbyn.py — conditional FULL TP switch
1.5sg-if-n>=2 else 1.0; this idea never switches the runner, it SELLS HALF early and keeps 1.0sg),
`oc_deeptp` (PLAN/REPORT/run.py — FULL quick TP 0.5sg on deep rungs only; this idea is HALF at
0.5/0.75sg on EVERY rung with the runner kept), `oc_beartp` (PLAN/REPORT — FULL faster TP 0.5sg on
bear bars; this idea has NO regime gate, every fill gets the half-early limit), `oc_dipexit`
(PLAN/REPORT/exits.py — D0 replica outcome_mu + E1 split 0.5+1.5 FULL halves + stop-first priority
copied verbatim; E1 splits into two FULL exits with shared race, this idea banks HALF at P and lets
the RUNNER re-race stops/1.0sg/timeout afterwards), v365 partial was BOOK M4 (book side; this is DIP
partial with runner). Kept as distinct per IDEAS6.

## Variants (exactly two + base, frozen ex-ante, never fit)

- BASE = deployed D0 rung (TP 1.0sg, sl 4sg close5, bl 8sg, timeout next-bar open o2).
- V1 = HALF at Pp=px*(1+0.5*sg) maker + runner halves re-race (sl/bl/1.0sg TP/timeout).
- V2 = HALF at Pp=px*(1+0.75*sg) maker + runner halves re-race (sl/bl/1.0sg TP/timeout).
- No other variant, no threshold tuning, no re-pegging, no size/rung change.

## Replica (deployed baseline, oc_dipexit/oc_placebo_dip-exact, frozen)

- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- 1m klines: `data/raw/btc_intraday_20260924` (BTC), `data/raw/majors_intraday_20260924`
  (others). Minutes used: t <= 2026-09-24 00:00 UTC. Missing minutes (NaN) never fill and never
  trigger an exit touch; a fill whose timeout open o2 is NaN is dropped (paired-keep below).
- 4 clock phases (oc_placebo_dip-exact): 4h grid from START = 2020-08-01 00:00 UTC + 0/1/2/3h
  offset (phase p bars open at START+p*1h+4h*j). Only bars with open T in
  [2021-09-24 00:00, 2026-09-24 00:00) UTC are traded (5 anchor years Y0..Y4 keyed by T).
- sigma_4h at bar j (known at the bar open): simple returns r_b = O_b/O_{b-1}-1 of 4h bar opens;
  sigma = std(r over 360 bars ending at j-1, min_periods 120, ddof=1) = v293/oc_dipexit
  definition. Bars with non-finite O_j or sigma<=0/NaN are skipped.
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0}. Level lv = O_j*(1-k*sigma(j)). Resting limit BUY at lv,
  live window offsets 16..238 inclusive. Fill at FIRST offset f with low(f) < lv (STRICT
  trade-through). Fill price px = lv, fee maker 0.0002. At most one fill per (bar, coin, k).
  n_fill = correlation count (v399-exact, oc_placebo_dip n_vector: other majors with
  C(T+m-1) <= O*(1-2.5*sg), NaN = no detect). Size w = 1/(1+n_fill) (B1 size, all arms).
- BASE exits (long), oc_dipexit outcome_mu-exact measured from px: sl = px*(1-4*sg),
  bl = px*(1-8*sg), tp = px*(1+1.0*sg). Evaluated on minutes t in f+1..239 then timeout at 240
  (next-bar open o2 = 1m open at T+240): backstop (first t low(t)<=bl) exits at min(bl,open(t))
  taker; else TP (first t high(t)>tp, STRICT) exits at tp maker; else close5 stop (clock minutes
  m with (m+1)%5==0 on absolute offsets, first m with close(m)<=sl) exits at open(m+1) (or o2 if
  m=239) taker; else timeout at o2 taker + funding 0.0001 if (T+4h).hour in (0,8,16). Priority
  stop-first: backstop wins ties (kb<=ks and kb<=kt); else TP only if strictly earlier (kt<ks);
  else stop; else timeout. Same-minute stop+TP -> stop. Fees: fill maker 0.0002; TP leg maker
  0.0002 (2*maker on TP); stop/backstop/time legs taker 0.00055. Nets are fractions of px.

## Partial legs (frozen, STRUCTURE-only change, causal)

- Partial level from FILL price only (no re-peg): Pp(V1) = px*(1+0.5*sg), Pp(V2) = px*(1+0.75*sg).
  Resting maker SELL limit at Pp from minute f+1 (minute-5 ban inherited: f>=16 always).
  Touch = STRICT high(t) > Pp. No re-peg, no second placement.
- Pre-partial race on t in f+1..239 (stop-first, base-extended): kb = first low<=bl,
  ks = first close5 (same (t+1)%5==0 grid), kp = first high>Pp, kt = first high>tp (kt>=kp).
  (1) backstop wins if kb exists and kb<=ks-or-None and kb<=kp-or-None -> whole backstop
  (same price/fee as BASE); (2) else if kp exists and (ks None or kp<ks) -> partial fills at kp,
  remainder re-races below; (3) else if ks exists (ks<kp, ks==kp same-minute, or kp None) ->
  whole stop (same as BASE); (4) else timeout whole at o2 (same as BASE).
  Same-minute stop+partial -> stop wins (kp<ks strict required). Same-minute backstop+partial ->
  backstop wins. Same-minute partial+runner (high>tp implies high>Pp): partial fills and the
  runner fills the same minute (both maker, net = average; implemented as remainder kt2==kp
  scan returning tp).
- Remainder race on t in kp+1..239 with SAME frozen sl/bl and runner tp = px*(1+1.0*sg):
  kb2/ks2 (same grids)/kt2 first touches; priority backstop (kb2<=ks2, kb2<=kt2) > runner TP
  (kt2<ks2) > stop > timeout at o2. Prices/fees per half as in BASE (maker fill + maker TP leg /
  taker stop/time leg). Partial half: r_part = Pp/px-1-2*maker (intrabar, never any funding).
  Remainder half: r_rem = tp/px-1-2*maker (TP) or px_exit/px-1-maker-taker (stop/backstop/time,
  minus FUND iff its exit x==240 and settle). Combined net = 0.5*r_part + 0.5*r_rem, so a
  remainder held through settlement pays 0.5*FUND total (disclosed, realistic: the exited half
  is not held at the settlement). If the runner TP is never touched and no stop fires, the
  remainder times out at o2 exactly like BASE.
- If Pp is never touched, V1 == V2 == BASE exactly (no partial, whole exit as BASE).
- Exit offset x = remainder x (partial x <= remainder x always); exit-day attribution uses the
  remainder x (conservative, later date). how = "part_tp"/"part_stop"/"part_backstop"/"part_time"
  for split fills; whole exits keep BASE hows ("tp"/"stop"/"backstop"/"time").
- Kept fills (PAIRED): a fill is kept iff BASE net AND V1 net AND V2 net are all finite
  (non-finite only from missing exit opens/o2; partial legs themselves always price-finite).

## Scoring + gate (frozen, BINDING)

- Year key: entry-bar year (T in [anchor, anchor+365d)). Daily sums per arm per year: group w*y
  by EXIT date (calendar UTC date of T+x; remainder x for partials). Per (phase, year) cell:
  S = sum of daily sums; DD = maxDD of the cumulative daily-sum path from 0 (same cell_stats as
  oc_placebo_dip); per year: 4-phase means S_bar, DD_bar. dSum5y(v) = sum_Y S_bar_v -
  sum_Y S_bar_base (4-phase-mean w*y units). sum_half(v) = #{Y: S_bar_v >= S_bar_base - 1e-12}.
  dd_half(v) = #{Y: DD_bar_v <= DD_bar_base + 0.01}.
- Gate (IDEAS6 header for dip ideas): full PROMISING legs (sum_half >= 4/5 AND dd_half >= 4/5)
  PLUS dSum5y >= +0.273 (pooled placebo p95, oc_placebo_dip). ALL THREE required.
  Engine runs ONLY for variants passing all three. If neither passes, STOP with no engine
  (negative result, valid — the oc_crashgate/oc_rungquality path).
- Fidelity report (not a gate, disclosed): phase-0 raw sums vs oc_dipexit ref
  [2.388, 0.183, 3.810, 2.579, 0.712]; base 4-phase-mean sums vs oc_placebo_dip
  [0.911, 0.833, 2.100, 3.197, 0.677] (tolerances +-0.05; pairing differs by the
  V1/V2-finite requirement).

## Part 2 — 4-phase engine (ONLY for gate-passing variants; not expected)

- Mechanism = exact copy of oc_downshare/run_engine.py (= oc_chronos/run_engine.py = v414 pipe
  v321, kd=1.7 corr-aware inv sizes, bear books, risk budget 0.26*1*1.7, sleeve_gross_cap G=2.0,
  win_start=5, gate costs inside: maker 0.0002, taker 0.00055, longs pay 0.0001/8h, shorts 0;
  limit fill only on 1m trade-through; nothing in first 5 min after a 4h close; stop-first;
  dip exits replaced by the gated partial rule: every filled rung sells HALF at Pp on a maker
  limit (STRICT trade-through, no re-peg) with the same frozen stops kept and the runner at
  1.0sg; same-minute stop+partial -> stop).
- Rows run (ONLY): REF (= G2 unchanged, v421 R2B1D17BFG2) first + each gate-passing variant
  (V1 and/or V2). REF must reproduce v421 G2 dev years R/DD to the digit
  [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27)] + Y4 (4.648/12.90), 5y 5.410,
  full-path DD 16.82 — else STOP.
- Stages: dev [2021-09-24, 2025-09-24) then last [2021-09-24, 2026-09-23) ONCE for REF + the
  dev4 robust pick only (every Y4 number labelled scored-once). Metrics/selection per
  OPENCODE_W_COMMON_20261007 (dev4 robust pick: DD<=20, no losing dev year; prefer mean>=5,
  highest WORST, ties->mean). Via heavy_slot, one job at a time; resume-safe caches.
- If Part 2 runs, REPORT carries the assignment's per-year table (dev 2021-2024; Y4 scored
  ONCE for the dev4 robust pick + REF only, labelled), dev4 robust pick, 5y, full-path DD
  (max of 4h-close and 1m-marked), win rates, fee/funding split, leakage checklist, and the
  3-line Vietnamese verdict.

## Leakage / checks (stated in REPORT)

- Feature timing (sigma from 4h opens <= T-1 bar; n from 1m closes at T+m-1; Pp/tp/sl/bl from
  px+sg only; truncation-tested), label windows (no labels fit; exits mechanical),
  fit windows (no fits/thresholds anywhere; 0.5/0.75 frozen ex-ante; no test-year
  statistic feeds any choice), fill timing (entry live 16..238 strict low<lv + minute-5 ban
  inherited via win_start; partial live f+1..239 strict high>Pp + runner strict high>tp;
  stop-first in shared minute; no re-peg). Gate costs inside all legs. No statistic from any
  test year feeds any choice.

## Compute plan

- `partialtp.py`: pure-numpy core (n_vector + size_mult + find_fill + outcome_mu copy +
  outcome_partial + outcome_pair_partial triple), no I/O, unit-tested.
- `run.py`: per-coin loop (one coin H/L at a time, all-five O/C float32 for n), 4 phases,
  paired triple ledger + exit-day sums -> `tmp/ledger.npz` + `results.json`. Heavy via
  heavy_slot, nohup + tmp log, heartbeat every 600 s, progress every 10 min.
- `results.json` (replica gate output; engine rows only if gated), REPORT.md, fills parquet.
- Tests `tests/test_oc_partialtp.py` (>=1 causality/truncation test + >=1 hand-checked
  synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_partialtp.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the original row stays
  and the change is a disclosed extra row.)
