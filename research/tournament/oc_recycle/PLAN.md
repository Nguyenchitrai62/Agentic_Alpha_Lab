# oc_recycle PLAN (pre-registered BEFORE any outcome is computed, 2026-10-08 — FROZEN)

Assignment: `docs/opencode/OPENCODE_W_oc_recycle.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md, IDEAS6_20261008.md idea #8 read in full, CLOSED rows cited read first).
Write ONLY `research/tournament/oc_recycle/` + `tests/test_oc_recycle.py`. Scratch only under
`research/tournament/oc_recycle/tmp/`. GIT IS READ-ONLY: never stash/reset/checkout/restore/clean/
rm/commit/switch/rebase/merge. Engine / heavy 1m work via `scripts/heavy_slot.py` (one job at a time,
one coin at a time, float32). Long jobs: nohup + log under tmp/, poll the log; never inspect /proc or
folders outside the workspace. Progress print every 10 minutes. PLAN.md frozen BEFORE any outcome.

## Why (IDEAS6_20261008.md idea #8, rank 8 — quoted, not refit)

Mech: early TPs leave capital idle till next 4h open while fresh rungs print unfilled (velocity loss,
budget already committed). Recycle realised winners only, never average losers.
Rule: freed TP notional (<=95% phase budget) may fill the NEXT frozen rung signal same window at frozen
price/size (maker, minute-5 from original signal). V1 same coin; V2 any coin. One recycle per unit, no
compounding; stops market taker.
Data: existing 1m+state. Harness: replica+gate then engine. Effect: +0.0-0.05%/mo, DD +0.0-0.2 watch.
Prior 7%.
Leak: only REALISED cash (exit time<=fill minute-1); price/size frozen; 1m budget check.
CLOSED rows read first: `oc_rearm` (PLAN/REPORT/rearm.py+run_rearm.py — re-ARM the SAME rung after a FILL
inside the bar; this idea never refills the same rung, it recycles a WINNER's freed notional to the NEXT
frozen rung signal — opposite direction, kept distinct), `oc_bidttl` (PLAN/REPORT/bidttl.py — FIXED bid
TTL expiry of unfilled bids; this idea keeps the 16..238 live window unchanged and only re-uses realised
cash, kept distinct), `oc_fillttl` (PLAN/REPORT/fillttl.py — FIXED post-fill exit TTL; this idea keeps
D0 exits unchanged and only changes budget availability, kept distinct). Kept as distinct per IDEAS6.

## Variants (exactly two + base, frozen ex-ante, never fit)

- BASE = committed-budget D0+B1 replica: per (phase, bar) the risk budget stays COMMITTED till the next
  4h open (a kept fill counts against the cap for the whole window even after its TP exits — the
  "capital idle" baseline of the idea's mechanism).
- V1 = BASE + winner-recycle, SAME coin: a realised TP (how==tp, exit x<=fill minute-1, kind==0 only)
  frees its kept notional; the freed pool may fund the NEXT frozen rung signal of the SAME coin later
  in the same window. One recycle per unit (each freed w funds at most one recycled w; pool-depleting),
  no compounding (recycled fills, kind==1, never free further capital even if they TP).
- V2 = same as V1 but freed pool is cross-coin (ANY coin's winner funds any coin's next signal).
- No other variant, no threshold tuning, no price/size change (frozen lv/w), no exit change.

## Replica (deployed baseline, oc_dipexit/oc_placebo_dip/oc_rearm-exact, frozen)

- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
- 1m klines: `data/raw/btc_intraday_20260924` (BTC), `data/raw/majors_intraday_20260924`
  (others). Minutes used: t <= 2026-09-24 00:00 UTC. Missing minutes (NaN) never fill and never
  trigger an exit touch; a fill whose exit price is missing (NaN open/o2) gives NaN net and is
  dropped as a paired triple (base+V1+V2 share the identical candidate signal).
- 4 clock phases (oc_placebo_dip-exact): 4h grid from START = 2020-08-01 00:00 UTC + 0/1/2/3h
  offset (phase p bars open at START+p*1h+4h*j). Only bars with open T in
  [2021-09-24 00:00, 2026-09-24 00:00) UTC are traded (5 anchor years Y0..Y4 keyed by T).
- sigma_4h at bar j (known at the bar open): simple returns r_b = O_b/O_{b-1}-1 of 4h bar opens;
  sigma = std(r over 360 bars ending at j-1, min_periods 120, ddof=1) = v293/oc_dipexit
  definition. Bars with non-finite O_j or sigma<=0/NaN are skipped.
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0}. Level lv = O_j*(1-k*sigma(j)) FROZEN at the bar open.
  Resting limit BUY at lv, live window offsets 16..238 inclusive (minute-5 ban inherited: first
  fillable minute is offset 16). Fill at FIRST offset f with low(f) < lv (STRICT trade-through).
  Fill price px = lv (frozen), fee maker 0.0002. At most one base fill per (bar, coin, k).
  n_fill = correlation count (v399-exact, oc_rearm n_vector: other majors with
  C(T+m-1) <= O*(1-2.5*sg), NaN = no detect, own coin never counted). Size w = 1/(1+n_fill)
  FROZEN per signal (B1 size; recycled fills reuse the signal's own frozen lv/w — no re-price).
- BASE exits (long), oc_rearm/rearm.py outcome_from_fill-exact measured from px: sl = px*(1-4*sg),
  bl = px*(1-8*sg), tp = px*(1+1.0*sg). Evaluated on minutes t in f+1..239 then timeout at 240
  (next-bar open o2 = 1m open at T+240): backstop (first t low(t)<=bl) exits at min(bl,open(t))
  taker; else TP (first t high(t)>tp, STRICT) exits at tp maker; else close5 stop (clock minutes
  m with (m+1)%5==0 on absolute offsets, first m with close(m)<=sl) exits at open(m+1) (or o2 if
  m=239) taker; else timeout at o2 taker + funding 0.0001 if (T+4h).hour in (0,8,16). Priority
  stop-first: backstop wins ties (kb<=ks and kb<=kt); else TP only if strictly earlier (kt<ks);
  else stop; else timeout. Same-minute stop+TP -> stop. Fees: fill maker 0.0002; TP leg maker
  0.0002 (2*maker on TP); stop/backstop/time legs taker 0.00055. Nets are fractions of px.
  Recycled fills use the IDENTICAL exit machine (stops market taker per the idea).

## Budget walks (frozen, the ONLY thing that differs between arms)

- Candidate pool per (phase, bar): all base signals with finite nets, sorted by (f ASC, k ASC,
  coin ASC). Engine `sleeve_gross_cap` replica with G = 2.0 on size_mult weights in ALL arms
  (the "<=95% phase budget" of the idea; identical G isolates the recycle — cf. oc_rearm PLAN item 6).
- BASE walk (committed): process in order; committed = sum of w_kept of ALL previously kept fills
  in this bar (nothing is freed early — the idle-capital baseline); room = G - committed;
  skip when room <= 1e-12, else keep w_kept = min(w, room) (cut to room, engine-exact).
- RULE walk (V1/V2, winner-recycle): same order; committed = sum of w_kept so far;
  freed_total = sum of w_kept of previously kept fills with kind==0 AND how==tp AND exit x <= f
  (REALISED only: the TP touch minute is fully closed before f; V1 counts only same-coin TPs,
  V2 counts any coin) AND, for V1, grouped per coin (freed pool per coin; a coin's recycled fills
  consume only its own coin pool); recycled_used = sum of w_kept already consumed from the pool
  (the freed-funded portion of previously kept fills, same grouping); room = G - committed
  + (freed_total - recycled_used) (freed winners extend the room; stops/timeouts/backstops never
  free — realised winners only); skip when room <= 1e-12, else w_kept = min(w, room); the
  freed-funded portion consumed = max(0, w_kept - max(G - committed, 0)) is added to recycled_used
  (one recycle per unit: pool depletes; no compounding: kind==1 fills never enter freed_total even
  if they TP). A recycled fill is exactly a base-pool signal kept with freed money — its price lv,
  size w, fill minute f, exit (x, how, ret) are the signal's own frozen values.
- Paired candidate generation: a signal enters the pool iff its D0 net is finite (dropped
  identically in all arms otherwise). Arms differ ONLY in keep/skip/cut via the walks above.

## Scoring + gate (frozen, BINDING)

- Year key: entry-bar year (T in [anchor, anchor+365d)). Daily sums per arm per year: group w_kept*y
  by EXIT date (calendar UTC date of T+x). Per (phase, year) cell: S = sum of daily sums;
  DD = maxDD of the cumulative daily-sum path from 0 (same cell_stats as oc_placebo_dip);
  per year: 4-phase means S_bar, DD_bar. dSum5y(v) = sum_Y S_bar_v - sum_Y S_bar_base
  (4-phase-mean w*y units). sum_half(v) = #{Y: S_bar_v >= S_bar_base - 1e-12}.
  dd_half(v) = #{Y: DD_bar_v <= DD_bar_base + 0.01}.
- Gate (IDEAS6 header for dip ideas): full PROMISING legs (sum_half >= 4/5 AND dd_half >= 4/5)
  PLUS dSum5y >= +0.273 (pooled placebo p95, oc_placebo_dip). ALL THREE required.
  Engine runs ONLY for variants passing all three. If neither passes, STOP with no engine
  (negative result, valid — the oc_crashgate/oc_rungquality/oc_makerexit path).
- Fidelity report (not a gate, disclosed): base 4-phase-mean sums vs oc_placebo_dip
  [0.911, 0.833, 2.100, 3.197, 0.677] and base committed-cap sums disclosed separately
  (the committed cap binds by construction, unlike the never-binding V1 mapping in oc_rearm —
  expect base n below the 22312 uncapped count; the comparison is base-vs-rule under the IDENTICAL
  G so the delta isolates the recycle).

## Part 2 — 4-phase engine (ONLY for gate-passing variants; not expected)

- Mechanism = exact copy of oc_downshare/run_engine.py (= oc_chronos/run_engine.py = v414 pipe
  v321, kd=1.7 corr-aware inv sizes, bear books, risk budget 0.26*1*1.7, sleeve_gross_cap G=2.0,
  win_start=5, gate costs inside: maker 0.0002, taker 0.00055, longs pay 0.0001/8h, shorts 0;
  limit fill only on 1m trade-through; nothing in first 5 min after a 4h close; stop-first;
  dip budget replaced by the gated recycle rule: realised TP notionals (same-coin V1 / any-coin V2,
  one recycle per unit, no compounding) may fund the next frozen rung signal same window at frozen
  price/size, total <= 95% phase budget).
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

- Feature timing (sigma from 4h opens <= T-1 bar; n from 1m closes at T+m-1; freed pool from TP
  exits with x <= f only — realised cash; truncation-tested), label windows (no labels fit; exits
  mechanical), fit windows (no fits/thresholds anywhere; G=2.0 and V1/V2 grouping frozen ex-ante;
  no test-year statistic feeds any choice), fill timing (entry live 16..238 strict low<lv +
  minute-5 ban inherited via window start; recycled fills reuse the signal's own f >= 16; stop-first
  in shared minute; NaN minutes never fill/trigger). Gate costs inside all legs. No statistic from
  any test year feeds any choice.

## Compute plan

- `recycle.py`: pure-numpy core (n_vector + size_mult + find_fill + outcome_from_fill copy of
  oc_rearm/rearm.py verbatim constants + committed_walk + recycle_walk with per-coin/cross-coin
  freed pools), no I/O, unit-tested.
- `run.py`: per-coin loop (one coin H/L at a time, all-five O/C float32 for n), 4 phases,
  shared candidate pool + three budget walks (base/V1/V2) + exit-day sums -> `tmp/ledger.npz` +
  `results.json`. Heavy via heavy_slot, nohup + tmp log, heartbeat every 600 s, progress every
  10 min.
- `results.json` (replica gate output; engine rows only if gated), REPORT.md.
- Tests `tests/test_oc_recycle.py` (>=1 causality/truncation test + >=1 hand-checked
  synthetic case; `.venv/Scripts/python.exe -m pytest tests/test_oc_recycle.py -q`).

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the original row stays
  and the change is a disclosed extra row.)
