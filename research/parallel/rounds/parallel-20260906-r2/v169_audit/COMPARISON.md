# v169 blind audit — COMPARISON.md (Part B)

Scope: `research/parallel/rounds/parallel-20260906-r2/v169_audit/` +
`tests/test_v169_audit.py` only. Base: cached v154 books, engine_real FULL
realism, target 0.25, governor on. No leader files edited.

Blind protocol: `replication.json` (`replicate_v169.py`,
`tests/test_v169_audit.py` passing 4/4) was saved BEFORE any `v169/` file was
opened. One correction happened while still blind (before opening `v169/`):
the no-stop row's `dd_1m` was recomputed over the full 1m path `0..239`
(per spec "or 0..239") instead of 0 — monthly/yearly/fullDD/stops were
unaffected. No Part A file was changed after opening `v169/` for Part B.

Key maps: blind `rows.{no_stop,k_3,k_2,k_4}` <-> leader
`v169_result.json` `{baseline_no_stop,primary_k3,sensitivity_k2,sensitivity_k4}`;
blind `dd_1m` <-> leader `dd_1m_mark`; blind `stop_counts` <-> leader
`stops_per_year`. Thresholds per assignment: return diff > 1pp, DD diff >
0.5pp must be explained (leader − blind).

## A. Number comparison (blind vs leader)

| row | blind monthly / fullDD / 1mDD / stops | leader monthly / fullDD / 1mDD / stops | Δ monthly | Δ DD |
|---|---|---|---|---|
| no_stop | 3.708 / 18.87 / 19.01 / 0 | 3.708 / 18.87 / 19.01 / 0 | 0 | 0.00pp |
| k_3 | 2.704 / 19.52 / 19.64 / 184 | 2.707 / 19.52 / 19.64 / 184 | +0.003pp | 0.00pp |
| k_2 | 1.995 / 19.79 / 20.03 / 591 | 2.015 / 19.75 / 19.84 / 590 | +0.020pp | −0.04pp |
| k_4 | 3.054 / 19.25 / 19.38 / 68 | 3.054 / 19.25 / 19.38 / 68 | 0 | 0.00pp |

No 1pp / 0.5pp threshold exceeded anywhere, so no mandatory explanation;
the residual deltas are still attributable (see B).

Yearly nets (blind vs leader): no_stop identical all 5 years
(19.17/45.40/96.18/60.37/63.04); k_4 identical all 5 years;
k_3 identical except 2021 (14.82 vs 15.03, same 32 stops that year);
k_2 2021 (9.97 vs 10.75, stops 114 vs 113) and 2024 (20.90 vs 21.42,
stops 116 = 116 — equity-path cascade, see B). Fills/mean_g match every
row/year (k_3 2026/2178/2187/2189/2183; k_2 2023/2178/2188/2189/2183;
k_4 2029/2179/2189/2190/2183). Stop counts per anchor year match except
k_2 2021 (114 vs 113).

## B. Why the small deltas — construction verified, one warmup nuance

- Loop: blind budget/carry-first/min-notional (BTC100/ETH20/other5 on
  10k USDT, keep prev_w, closes pass)/v135 entry exec/governor
  (j=i−2, 90-day peak)/carry untouched/prev_w=0 after a stop/funding=0 on
  stopped bars/extra cost sum|w|×0.001 ≡ leader `:99-146`. Leader
  EXIT_COST = 0.0005+0.0005 = 0.001 = spec 0.001. Pass.
- Holding bar/trigger/exit: T = t_i+4h, R(m) on 1m closes over base =
  engine 4h open of T, first m in 16..238, exit at 1m open of m+1 ≡
  leader `MON0=16`, `path[16:239]`, `O[i,m+1]` (`:118-135`). Pass.
- 1m DD: blind eq_min = eq[i−1]×(1+min(0,min R used)−exec_total),
  DD = max over live of 1−min(eq,eq_min)/running-max(eq) ≡ leader
  `:144,:149-150` (normalisation cancels in the ratio; both give
  no_stop 19.01). Pass.
- Known nuance (explains k_2/k_3 residuals, all far below thresholds):
  leader S_i uses `opens.reindex(books_idx).pct_change().rolling(360,
  min 120).cov()` — history starts at the first books bar, so cov is
  None for the first ~119 bars and the window is still growing until bar
  ~359. Blind S_i uses the full opens history from 2017 (same 360/min-120
  rule), so it is defined from bar 0. L therefore differs slightly on
  early bars (same 2021 window), producing one extra k_2 stop in 2021
  and a different exit minute on one k_3 2021 bar; the equity divergence
  then cascades through the governor/min-notional (k_2 2024 net). After
  the warmup both windows coincide and every other year/row matches
  exactly. Two further immaterial guards differ: leader skips the stop
  when L == 0 (`:125`) while blind would test R ≤ −0 (never binds with
  w ≠ 0 and positive-definite S), and leader requires finite exit-open
  else falls back to no-stop (`:129`) while blind fills a leading
  missing minute with the base (data are complete; never binds).

## C. Look-ahead audit — `v169/v169_intrabar_stop.py`, no look-ahead found

- Threshold (`:162-170` → `:123-125`): S_i at bar i uses 4h
  open-to-open returns ending at bar i (open[i] is known at the open of
  bar i, before the close-t decision). w is the post-budget/min-notional
  decision weight at i. Nothing past bar i enters L. This is the exact
  check the assignment asked for. Pass.
- Exit strictly after trigger (`:125-135`): trigger scans closes at
  minutes 16..238; exit prices the 1m open of minute m+1 (m+1 ≤ 239,
  inside the same holding bar). No same-minute fill. Pass.
- Base (`:118,:121`): o1[i] = engine open of T, known when T opens
  (after the decision, before monitoring) and used consistently for R
  and the exit gross. Pass.
- Cube timing (`:53-77`): each 1m row is bucketed by its own floored 4h
  start into that bar's 240 offsets; ffill runs m−1 → m inside the same
  bar only — no cross-bar leak. Monitoring starts at minute 16, after
  the v135 entry fill window (minutes 0..15). Pass.
- Costs/funding/carry/governor per AGENTS.md and the audited engine_real
  (entry exec kept, +0.001 exit cost, funding zeroed only on stopped
  bars, carry sleeve untouched, governor on stop-adjusted equity with
  the j=i−2 lag). No decision conditions on future 1m data. Pass.

## D. Manifest notes / verdict

- `v169/result_manifest.json`: track C, `rejected`, `live_approved:false`,
  primary k_3 2.707/19.52 (fills 10763/60mo), note matches the numbers
  (stops cut return: k_3 −1.0pp/mo and k_2 −1.7pp/mo vs no-stop 3.708;
  no row reduces DD: 19.52/19.75/19.25 vs 18.87 close-sampled, and 1m
  DD 19.64/19.84/19.38 vs 19.01). Blind reproduces the economics:
  the stop does not buy a DD reduction. Consistent with `rejected`.
- By-product confirmed blind: true 1m-marked DD of v154 = 19.01%
  (vs the conservative 4h bound 21.37%).
- Audit complete; leader files untouched.

## Files

- `replication.json` (Part A, blind, frozen), `replicate_v169.py`,
  `tests/test_v169_audit.py` pass 4/4, `COMPARISON.md` (this file).
