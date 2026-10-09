# oc_makerexit PLAN (pre-registered BEFORE any outcome is computed, 2026-10-08 — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_makerexit.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md, IDEAS6_20261008.md idea #1 read in full, CLOSED rows cited read first).
Write ONLY `research/tournament/oc_makerexit/` + `tests/test_oc_makerexit.py`. Scratch only under
`research/tournament/oc_makerexit/tmp/`. GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/
rm/commit/switch/rebase/merge. Engine / heavy 1m work via `scripts/heavy_slot.py` (one job at a time,
one coin at a time, float32). Long jobs: nohup + log under tmp/, poll the log; never inspect /proc or
folders outside the workspace. Progress print every 10 minutes. PLAN.md frozen BEFORE any outcome.

## Why (IDEAS6_20261008.md idea #1, rank 1 — quoted, not refit)

Mech: 15-25% dip fills end in taker timeout exits (5.5bps+spread); resting reduce-only limit earns
spread instead. HOW not WHEN. Rule: at each 4h timeout, place reduce-only SELL limit at
close-mid+1tick, 60min, trade-through maker, minute-5 ban; remainder taker. V1 100% one limit;
V2 50% +1tick / 50% +3ticks. Data: existing 1m. Harness: replica (timeout-leg dSum+gate) then
engine vs G2. Effect: +0.02-0.08%/mo, DD flat/-0.2. Prior 18% (pure fee save). Leak: price from
closes<=open; fills min>=5 trade-through; stop-first kept.
CLOSED rows read first: `oc_holdext` (PLAN/REPORT/holdext.py — WHEN-hold +4h, timeout share,
paired-keep + funding-0/1/2x convention copied; this idea does NOT extend WHEN, only HOW the
timeout exits), `oc_condhold` (PLAN/REPORT — profit-gate + same-leg extension template; this idea
has NO profit gate, every timeout gets the maker limit), `oc_dipexit` (PLAN/REPORT/exits.py —
D0 replica outcome_mu + stop-first priority + fee/funding legs copied verbatim; this idea keeps
TP LEVEL at 1.0sg, only the timeout leg's execution changes). Kept as distinct per IDEAS6.

## Variants (exactly two + base, frozen ex-ante, never fit)

- BASE = deployed D0 timeout (taker at next-bar open o2, maker fill + taker exit + settle fund).
- V1 = 100% of the timeout notional at P1 = o2*(1+0.0001) (+1tick proxy, see tick note).
- V2 = 50% at P1 = o2*(1+0.0001) + 50% at P3 = o2*(1+0.0003) (+1tick / +3ticks proxy).
- No other variant, no threshold tuning, no re-pegging, no TP/stop-level change.

## Tick note (frozen proxy, conservative, disclosed)

Actual Binance perp ticks on majors are ~0.17-0.33 bps (BTC 0.1 @ ~60k, ETH 0.01 @ ~3k),
so +1 real tick sits INSIDE +1 bps. The replica has no tick table, so +1tick is proxied as
+1 bps (0.0001) and +3ticks as +3 bps (0.0003) above the timeout-open mid. The proxy limit is
FARTHER from mid than a real +1tick limit, so its maker fill rate is a LOWER bound and any
measured saving understates a real +1tick placement. Direction of bias is against the idea.

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

## Maker-timeout legs (frozen, HOW-only change, causal)

- Apply IFF BASE how == "time" (no TP, no close5 stop signal, no backstop touch in f+1..239;
  a close5 signal at m=239 exiting at o2 counts as "stop", NOT extended). Non-timeout fills:
  V1 net = V2 net = BASE net (same exit, same net; no second-bar data needed).
- Limit price (causal, known at T+240): P1 = o2*(1+0.0001); P3 = o2*(1+0.0003). o2 is the 1m
  open at T+240 (the timeout-open mid proxy; closes<=open per the IDEAS6 leak note).
- Maker window (minute-5 ban): live minutes t in 245..299 inclusive (offsets from T; first 5 min
  240..244 banned, no fills). Remainder taker at o3m = 1m open at T+300 (60 min after timeout).
  H/L/C/O of the same coin for t in 240..300; NaN = no touch / no fill at that minute.
- Stops KEPT during the window (user rule: every position has a stop; stop-first kept):
  SAME frozen sl/bl levels as BASE (from px and sg). Per-minute scan t = 245..299 in order:
  (1) backstop: if low(t) <= bl -> exit remaining at min(bl,open(t)) taker (backstop wins);
  (2) close5 stop: if (t+1)%5==0 (same wall-clock grid, continuous since 240%5==0) and
  close(t) <= sl -> exit remaining at open(t+1) taker (t+1 <= 300 always; t=299 exits at o3m);
  (3) maker: else, each still-open half with high(t) > P_half (STRICT trade-through) fills at
  P_half maker. Same-minute stop+maker -> stop wins (stop checked first). Halves share the
  stop/backstop race; maker fills are per-half independent.
- Exit accounting per half: maker fill -> px_half exit at P_half, net = P_half/px-1-maker-taker? NO:
  fill leg maker + exit maker = P_half/px-1-2*maker (same as a TP leg). Taker remainder / stop /
  backstop -> px exit, net = px_exit/px-1-maker-taker (same as base legs). Funding: every maker-
  window exit pays mid fund 0.0001 iff settle_mid = (T+240).hour in (0,8,16) (held through the
  settlement, identical to BASE; the 60-min window never crosses a second settlement since
  T+240 is 4h-aligned). V1 net = the single-half net. V2 net = 0.5*y(P1 half)+0.5*y(P3 half).
- Exit offset x: maker fill at t (245..299); stop/backstop at their minute (backstop t, stop
  t+1); remainder taker at 300. Base timeout x = 240.
- Kept fills (PAIRED): a fill is kept iff BASE net AND V1 net AND V2 net are all finite
  (non-timeouts need no window data so all finite together; timeouts near the data end with
  NaN o3m/window exit prices drop as triples, keeping arms exactly comparable).

## Scoring + gate (frozen, BINDING)

- Year key: entry-bar year (T in [anchor, anchor+365d)). Daily sums per arm per year: group w*y
  by EXIT date (calendar UTC date of T+x; maker exits can print up to +60 min after T's base date
  but stay attributed to the entry year). Per (phase, year) cell: S = sum of daily sums;
  DD = maxDD of the cumulative daily-sum path from 0 (same cell_stats as oc_placebo_dip);
  per year: 4-phase means S_bar, DD_bar. dSum5y(v) = sum_Y S_bar_v - sum_Y S_bar_base
  (4-phase-mean w*y units). sum_half(v) = #{Y: S_bar_v >= S_bar_base - 1e-12}.
  dd_half(v) = #{Y: DD_bar_v <= DD_bar_base + 0.01}.
- Gate (IDEAS6 header for dip ideas): full PROMISING legs (sum_half >= 4/5 AND dd_half >= 4/5)
  PLUS dSum5y >= +0.273 (pooled placebo p95, oc_placebo_dip). ALL THREE required.
  Engine runs ONLY for variants passing all three. If neither passes, STOP with no engine
  (negative result, valid — the oc_crashgate/oc_rungquality path).
- Fidelity report (not a gate, disclosed): phase-0 raw sums vs oc_dipexit ref
  [2.388, 0.183, 3.810, 2.579, 0.712]; base 4-phase-mean sums vs oc_placebo_dip
  [0.911, 0.833, 2.100, 3.197, 0.677] (tolerances +-0.05; pairing differs by the o3m-finite
  requirement on timeouts).

## Part 2 — 4-phase engine (ONLY for gate-passing variants; not expected)

- Mechanism = exact copy of oc_downshare/run_engine.py (= oc_chronos/run_engine.py = v414 pipe
  v321, kd=1.7 corr-aware inv sizes, bear books, risk budget 0.26*1*1.7, sleeve_gross_cap G=2.0,
  win_start=5, gate costs inside: maker 0.0002, taker 0.00055, longs pay 0.0001/8h, shorts 0;
  limit fill only on 1m trade-through; nothing in first 5 min after a 4h close; stop-first;
  timeout exits replaced by the gated maker rule: at each 4h timeout place the reduce-only
  maker limit(s) for 60 min with the same stops kept, remainder taker).
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

- Feature timing (sigma from 4h opens <= T-1 bar; n from 1m closes at T+m-1; P from o2 at
  T+240 only for timeouts; truncation-tested), label windows (no labels fit; exits mechanical),
  fit windows (no fits/thresholds anywhere; deltas 0.0001/0.0003 frozen ex-ante; no test-year
  statistic feeds any choice), fill timing (entry live 16..238 strict low<lv + minute-5 ban
  inherited via win_start; maker live 245..299 strict high>P + 240..244 ban; stop-first in
  shared minute; taker remainder). Gate costs inside all legs. No statistic from any test year
  feeds any choice.

## Compute plan

- `makerexit.py`: pure-numpy core (n_vector + size_mult + find_fill + outcome_mu copy +
  outcome_maker_window + outcome_pair triple), no I/O, unit-tested.
- `run.py`: per-coin loop (one coin H/L at a time, all-five O/C float32 for n), 4 phases,
  paired triple ledger + exit-day sums -> `tmp/ledger.npz` + `results.json`. Heavy via
  heavy_slot, nohup + tmp log, heartbeat every 600 s, progress every 10 min.
- `results.json` (replica gate output; engine rows only if gated), REPORT.md, fills parquet.
- Tests `tests/test_oc_makerexit.py` (>=1 causality/truncation test + >=1 hand-checked
  synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_makerexit.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the original row stays
  and the change is a disclosed extra row.)
