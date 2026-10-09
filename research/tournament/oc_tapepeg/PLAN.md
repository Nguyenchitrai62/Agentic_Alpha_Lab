# oc_tapepeg PLAN (pre-registered BEFORE any outcome is computed, 2026-10-08 — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_tapepeg.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md, IDEAS6_20261008.md idea #4 read in full, CLOSED rows cited read first).
Write ONLY `research/tournament/oc_tapepeg/` + `tests/test_oc_tapepeg.py`. Scratch only under
`research/tournament/oc_tapepeg/tmp/`. GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/
rm/commit/switch/rebase/merge. Engine / heavy 1m work via `scripts/heavy_slot.py` (one job at a time,
one coin at a time, float32). Long jobs: nohup + log under tmp/, poll the log; never inspect /proc or
folders outside the workspace. Progress print every 10 minutes. PLAN.md frozen BEFORE any outcome.

## Why (IDEAS6_20261008.md idea #4, rank 4 — quoted, not refit)

Mech: Maker's Dilemma: fill-prob vs return is queue-position trade; bare sigma prices get picked
off mid-sweep. Same exposure, less adverse fill.
Rule: rung = min(frozen sigma price, trailing-60m 1m LOW - 1tick) at signal close; rest identical
(maker/sizes/stops/TP). V1 60m low; V2 low rounded DOWN to 5-tick.
Data: existing 1m. Harness: replica+gate then engine. Effect: +0.0-0.08%/mo, DD -0.0-0.3.
Prior 10%.
Leak: low from bars close_time<=signal close; never placement window; offset frozen.
CLOSED rows read first: `oc_rungspace` (PLAN/REPORT/rungspace.py/run.py — spacing MULT widens
DISTANCE between rungs 2.5/3.25/4.0/5.0/6.0, static B1 bids, NOT PROMISING on sums 1/5; this idea
keeps the R2 spacing and only anchors each rung's LEVEL to printed tape), `oc_b1deeper`
(PLAN — corr PRICE amendment deeper while n>=1, bot-amended per minute; this idea never amends
inside the window, the tape peg is frozen at the signal close), `oc_bookoffset` (PLAN — vol
OFFSET scales book entry distance 5..40 bps; this is DIP rung placement, not book offset).
Kept as distinct per IDEAS6.

## Variants (exactly two + base, frozen ex-ante, never fit)

- BASE = deployed D0 replica rung (frozen sigma price only, maker fill + D0 exits below).
- V1 = tape-anchored rung: min(sigma price, LOW60 - 1tick).
- V2 = tape-anchored rung with 5-tick rounding: min(sigma price, floor_to_5tick(LOW60 - 1tick)).
- No other variant, no threshold tuning, no re-pegging inside the live window, no TP/stop-level
  change, no spacing change (R2 rungs 2.5/3.0/3.5/4.0/5.0 kept).

## Tick note (frozen proxy, conservative, disclosed)

Actual Binance perp ticks on majors are ~0.17-0.33 bps (BTC 0.1 @ ~60k, ETH 0.01 @ ~3k), so
1 real tick sits INSIDE 1 bp. The replica has no tick table, so 1tick is proxied as 1 bp
(0.0001) of the trailing low: tick = LOW60 * 0.0001; peg1 = LOW60 - tick = LOW60 * 0.9999.
5-tick grid = 5 * tick; peg2 = floor(peg1 / grid) * grid (= 0.9995 * LOW60 whenever LOW60 is
finite and positive, i.e. 4 bps below the printed low). Both proxies sit FARTHER below the
low than a real 1-tick / 5-tick placement, so variant fill rates are LOWER bounds and any
measured adverse-fill saving is net of the maximum opportunity cost. Direction of bias is
against the idea (fewer fills, same as the oc_rungspace opportunity-cost lesson).

## Tape peg (frozen, causal)

- Signal close = bar open T (the 4h bar open minute; rung levels are frozen at T, known at T).
- LOW60(a,T) = min 1m `low` of coin a over the 60 fully closed 1m bars strictly before T,
  i.e. minutes [T-60m, T-1m] inclusive (absolute offsets [base-60, base-1] where base is the
  minute index of T). Causal: uses only bars with close_time <= T. NaN lows are ignored
  (never fill/trigger convention); if all 60 are NaN (or base < 60 at the grid start) LOW60
  is NaN and the rung falls back to the sigma price (no peg that bar).
- rung_px(BASE; a,T,k) = O_a(T) * (1 - k * sg_a(T)) (frozen sigma price, identical to the
  oc_dipexit/oc_placebo_dip/oc_makerexit replica).
- rung_px(V1) = min(sigma price, LOW60 - tick); rung_px(V2) = min(sigma price, peg2).
  The min() is per (bar, coin, rung): when the recent tape never printed below the sigma
  price the rung is unchanged; when a sweep already printed lower, the rung drops to just
  below the printed low (same exposure intent, less mid-sweep pick-off). Non-finite or
  non-positive pegs fall back to the sigma price. Frozen at T: never updated inside the
  live window (unlike oc_b1deeper amendment; like IDEAS6 "offset frozen").
- Rest identical per rung: resting limit BUY at rung_px, same live window, same size formula
  w = 1/(1+n_fill) with n_fill counted at the variant's own fill minute, same D0 exits
  measured from the variant's own fill price px (sl = px*(1-4sg), bl = px*(1-8sg),
  tp = px*(1+1.0sg)), same fees/funding/priority.

## Replica (deployed baseline, oc_dipexit/oc_placebo_dip/oc_makerexit-exact, frozen)

- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- 1m klines: `data/raw/btc_intraday_20260924` (BTC), `data/raw/majors_intraday_20260924`
  (others). Minutes used: t <= 2026-09-24 00:00 UTC. Missing minutes (NaN) never fill and never
  trigger an exit touch; a fill whose timeout open o2 is NaN is dropped per arm independently
  (arms have independent fill sets, so no cross-arm pairing; comparability comes from the
  identical bar universe + gate on yearly sums, same as oc_rungspace).
- 4 clock phases (oc_placebo_dip-exact): 4h grid from START = 2020-08-01 00:00 UTC + 0/1/2/3h
  offset (phase p bars open at START+p*1h+4h*j). Only bars with open T in
  [2021-09-24 00:00, 2026-09-24 00:00) UTC are traded (5 anchor years Y0..Y4 keyed by T).
- sigma_4h at bar j (known at the bar open): simple returns r_b = O_b/O_{b-1}-1 of 4h bar opens;
  sigma = std(r over 360 bars ending at j-1, min_periods 120, ddof=1) = v293/oc_dipexit
  definition. Bars with non-finite O_j or sigma<=0/NaN are skipped (no rungs that bar).
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0}. Resting limit BUY at the arm's rung_px, live window
  offsets 16..238 inclusive. Fill at FIRST offset f with low(f) < rung_px (STRICT
  trade-through). Fill price px = rung_px, fee maker 0.0002. At most one fill per
  (bar, coin, k, arm). n_fill = correlation count (v399-exact: other majors with
  C(T+m-1) <= O*(1-2.5*sg), NaN = no detect). Size w = 1/(1+n_fill) (B1 size, all arms).
- Exits (long), oc_dipexit outcome_mu-exact measured from px: sl = px*(1-4*sg),
  bl = px*(1-8*sg), tp = px*(1+1.0*sg). Evaluated on minutes t in f+1..239 then timeout at 240
  (next-bar open o2 = 1m open at T+240): backstop (first t low(t)<=bl) exits at min(bl,open(t))
  taker; else TP (first t high(t)>tp, STRICT) exits at tp maker; else close5 stop (clock minutes
  m with (m+1)%5==0 on absolute offsets, first m with close(m)<=sl) exits at open(m+1) (or o2 if
  m=239) taker; else timeout at o2 taker + funding 0.0001 if (T+4h).hour in (0,8,16). Priority
  stop-first: backstop wins ties (kb<=ks and kb<=kt); else TP only if strictly earlier (kt<ks);
  else stop; else timeout. Same-minute stop+TP -> stop. Fees: fill maker 0.0002; TP leg maker
  0.0002 (2*maker on TP); stop/backstop/time legs taker 0.00055. Nets are fractions of px.
- Kept fills: a fill is kept iff its exit net is finite (missing exit price -> drop that arm's
  fill only; arms are scored independently, no triple pairing).

## Scoring + gate (frozen, BINDING)

- Year key: entry-bar year (T in [anchor, anchor+365d)). Daily sums per arm per year: group w*y
  by EXIT date (calendar UTC date of T+x). Per (phase, year) cell: S = sum of daily sums;
  DD = maxDD of the cumulative daily-sum path from 0 (same cell_stats as oc_placebo_dip /
  oc_makerexit). Per year: 4-phase means S_bar, DD_bar. dSum5y(v) = sum_Y S_bar_v - sum_Y
  S_bar_base (4-phase-mean w*y units). sum_half(v) = #{Y: S_bar_v >= S_bar_base - 1e-12}.
  dd_half(v) = #{Y: DD_bar_v <= DD_bar_base + 0.01}.
- Gate (IDEAS6 header for dip ideas): full PROMISING legs (sum_half >= 4/5 AND dd_half >= 4/5)
  PLUS dSum5y >= +0.273 (pooled placebo p95, oc_placebo_dip). ALL THREE required.
  Engine runs ONLY for variants passing all three. If neither passes, STOP with no engine
  (negative result, valid — the oc_crashgate/oc_rungquality/oc_makerexit path).
- Fidelity report (not a gate, disclosed): phase-0 raw sums vs oc_dipexit ref
  [2.388, 0.183, 3.810, 2.579, 0.712]; base 4-phase-mean sums vs oc_placebo_dip
  [0.911, 0.833, 2.100, 3.197, 0.677] (tolerance +-0.05).

## Part 2 — 4-phase engine (ONLY for gate-passing variants; not expected)

- Mechanism = exact copy of oc_downshare/run_engine.py (= oc_chronos/run_engine.py = v414 pipe
  v321, kd=1.7 corr-aware inv sizes, bear books, risk budget 0.26*1*1.7, sleeve_gross_cap G=2.0,
  win_start=5, gate costs inside: maker 0.0002, taker 0.00055, longs pay 0.0001/8h, shorts 0;
  limit fill only on 1m trade-through; nothing in first 5 min after a 4h close; stop-first;
  rung placement replaced by the gated tape-peg rule: rung = min(sigma price, LOW60-1tick)
  (V1) or min(sigma price, floor_to_5tick(LOW60-1tick)) (V2), frozen at the signal close).
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

- Feature timing (sigma from 4h opens <= T-1 bar; LOW60 from 1m lows in [T-60m,T-1m] only;
  n from 1m closes at T+m-1; truncation-tested), label windows (no labels fit; exits
  mechanical), fit windows (no fits/thresholds anywhere; tick 1bp / grid 5bp frozen ex-ante;
  no test-year statistic feeds any choice), fill timing (entry live 16..238 strict low<px +
  minute-5 ban inherited via win_start; stop-first in shared minute; NaN minutes never
  fill/trigger). Gate costs inside all legs. No statistic from any test year feeds any choice.

## Compute plan

- `tapepeg.py`: pure-numpy core (n_vector + size_mult + find_fill + outcome_mu copy +
  tape_peg + rung_px triple), no I/O, unit-tested.
- `run.py`: per-coin loop (one coin H/L at a time, all-five O/C float32 for n), 4 phases,
  independent per-arm ledgers + exit-day sums -> `tmp/ledger.npz` + `results.json`. Heavy via
  heavy_slot, nohup + tmp log, heartbeat every 600 s, progress every 10 min.
- `results.json` (replica gate output; engine rows only if gated), REPORT.md.
- Tests `tests/test_oc_tapepeg.py` (>=1 causality/truncation test + >=1 hand-checked
  synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_tapepeg.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the original row stays
  and the change is a disclosed extra row.)
