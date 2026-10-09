# oc_nativeclock PLAN (pre-registered BEFORE any outcome, 2026-10-07)

## Question
Do the three shifted clocks (s=1,2,3h) earn timing value from OWN fresh book
signals computed on their own 4h grids, instead of the deployed forward-filled
standard-grid book rows?

## Deployed reference (frozen)
- G2 = `R2B1D17BFG2` in `research/parallel/rounds/parallel-20260906-r2/v421`
  (`v421_runs.pkl` per phase 0..3 `t`/`eq`/`eq_min`, `v421_result.json` rows).
  Expected 5y reset metric R/W/DD/full: 5.41 / 2.588 / 16.91 / 16.82, years
  (R,DD) = (2.588,10.86), (3.282,16.91), (6.045,15.81), (10.677,8.27),
  (4.648,12.90). Reproduce exactly first (same check as
  `oc_carrycompound/analyze_carrycompound.py`: `v388.hourly` + `reset_metric`
  per-year reset + continuous full-path DD); if reproduction fails, stop.
- Everything else = G2: v421 RUNS rule inv, k 1.0, kd 1.7, bear True, G 2.0
  (`v421_gross_cap.py:worker`, incl. `corr_size` inv, risk_mult k,
  budget 0.26*k*kd, sleeve_gross_cap G, `pipe_setup("v321")`, `trade` from
  `v216.GRID` + `grid_policy`, `win_start=5`).

## Pre-registered variants (ONLY these two, then close the direction)
1. REF = G2 forward-filled books (exact `v421_gross_cap.py:worker` replica:
   `std_books = fw.research_books_d2(eu)` on the STANDARD grid after the v421
   bear filter, `books = std_books.reindex(idx, method="ffill")` per shift).
2. NATIVE = same as REF except: for each shift s in {1,2,3}, the book members'
   predictions are computed on that clock's own 4h bars (bars opening at
   s, s+4, ...; features recomputed from the 1m stores on the shifted grid
   with the SAME feature code; the frozen per-anchor member models applied
   unchanged, no retraining), blended exactly as `research_books_d2` does,
   same bear filter, fed to phase s instead of the forward-filled standard
   rows. Phase 0 unchanged (identity).
   - Member fallback (fixed here): if a member's features cannot be computed
     on a shifted grid from the available stores (e.g. daily inputs, options
     flow, quarterly refits whose per-anchor models are not persisted),
     that member stays forward-filled and is listed in REPORT.md. If ALL
     members stay forward-filled, NATIVE == REF bit-exact by construction
     (reported as a valid negative/feasibility result, no second tuning).

## Inputs (read-only, no edits outside this folder + test file)
- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (engine order).
- Book members behind `research_books_d2` (= `research_books_o1` + D):
  A=`member_A_O1_orders`, Aq=`member_Aq_O1_orders`, B=`member_B_tv`,
  Bq=`member_Bq_tv`, D=`members_v154[D]`, Dq=`members_quarterly_D`
  (from `artifacts/research/engine_real/`); blend `o1=0.5*(A+B)/2+0.5*(Aq+Bq)/2`,
  `d2=0.8*o1+0.2*(D+Dq)/2`, union index, missing -> 0.0.
- Years: dev Y0..Y3 = anchors 2021/2022/2023/2024-09-24 +365d each
  ([A, A+365d)); most-recent Y4 = 2025-09-24..2026-09-23 scored ONCE, only for
  the chosen variant (+ reference), labelled, never used for the verdict.
- Member audit inputs: `models/frozen/*.pkl` (+ manifest), `scripts/v240_advisor.py`,
  `scripts/v233_advisor.py`, `v240/v240_order_level_flow.py`,
  `v236/flow_features.py`, `v233/v233_tv_all_members.py`, `v111/v111_coinbase_premium.py`,
  `v150/v150_options_flow.py`, `v202/v202_quarterly_retrain.py` (walk-forward
  model persistence check).

## Fixed engine construction (both variants)
- `books154, _opens_std = eu.er.v154_books()`; standard books
  `std = fw.research_books_d2(eu).reindex(books154.index).fillna(0)[cols]`.
- Bear flag (v421 lines 69-72): `btc=_opens_std["BTCUSDT"]`,
  `bear=(btc < btc.rolling(1200,min_periods=600).mean())`; `sb=std.copy()`,
  `sb[bear] = sb[bear].where(sb[bear]<=0, sb[bear]*0.5)` (longs x0.5).
- Per shift s: `M=pod.minutes()`; `opens,prep=pof.prep_idx(M,books154.index+sh,
  s,cols)` (identical to engine incl. float32 ffill, settle flags).
- REF books per shift: `sb.reindex(idx,method="ffill").fillna(0)`.
- NATIVE books per shift: phase 0 = REF phase 0; phases 1..3 = native-blended
  `sb_native.reindex(idx)` where computable (= identity reindex when the
  native frame already sits on the shifted grid), forward-filled members
  ffill'd as in REF. Causality: native row at decision bar t uses only 1m
  minutes < t+4h bar close (features) and models fit before anchor - 7d.
- `hist.R2_TABLE = v376/tables_hidden/r2_table_s{shift}.parquet`; `kw,trade` =
  `pof.pipe_setup("v321",...)` + v421 `corr_size/kd=1.7/risk_mult/k=1.0/
  budget 0.26*1*1.7/G=2.0`; `eu.simulate(books, opens, prep, trade=trade,
  win_start=5, events=ev, **kw)`.

## Gate costs / execution (inside `eu.simulate`, unchanged)
Maker 0.0002 (entries/TP/limit exits), taker 0.00055 (stops/market), longs
pay 0.0001/8h settlement in (T,T+4h] window, shorts 0, limit fill only on 1m
trade-through, no fill minutes 0-4 after 4h close, stop-first in same bar.

## Scoring (fixed)
- Per-year reset metric (`reset_metric.year_reset` per anchor year, fresh 1.0
  per year, 4-phase mean) + max yearly DD + full-path DD (continuous,
  max of marked/close per v421/v388 `mix`) + book turnover/fees per year
  (turnover = mean |dW| per decision bar from the fed book frames; engine
  book fills/win from `events` on the heavy run) + per-phase table
  (phase 0 NATIVE must equal REF).
- Selection ONLY on dev Y0..Y3 per the robust criterion (DD <= 20, no losing
  dev year; prefer dev4 mean >= 5 %/mo; among those highest dev4 WORST-year
  monthly; ties -> higher mean). Most-recent year scored once for the frozen
  finalist (+ REF) and labelled.
- Verdict rule (assignment): NATIVE beats G2 on dev4 mean AND worst year with
  DD <= G2 + 0.5 -> registered candidate; else reject. 3-line Vietnamese
  verdict in REPORT.md.

## Outputs
`reproduce_g2.py` (light validation), `audit_members.py` (member computability
audit), `run_nativeclock.py` (heavy engine via heavy_slot, REF + NATIVE),
`results.json`, `REPORT.md` (per-year + per-phase tables, member list, what
failed, leakage/execution statement, Vietnamese verdict). Test
`tests/test_oc_nativeclock.py` (causality/truncation + hand-checked
synthetic). Write ONLY `research/tournament/oc_nativeclock/` + that test.
