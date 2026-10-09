# oc_sleevealloc — PLAN (pre-registered 2026-10-08, BEFORE any outcome)

Assignment: `docs/opencode/OPENCODE_W_oc_sleevealloc.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md read). Write ONLY `research/tournament/oc_sleevealloc/`
+ `tests/test_oc_sleevealloc.py`. Engine/heavy work via `scripts/heavy_slot.py`
(one job at a time; RAM tight). Progress heartbeat every 10 min. Scratch only under
`research/tournament/oc_sleevealloc/tmp/` (never system temp, never /proc).

## Question (IDEAS10 #4, EXACTLY as written)

Cross-sleeve drawdown-budget allocator (G2-book / G2-dip / carry weights).
Today book, dip and carry combine at FIXED f=0.25 carry; the frontier shows
return∝DD on every dial (FRONTIER_MAP_VI) — the untested dial is ALLOCATION
across sleeves by risk contribution, rebalanced slowly.

## Pre-registered variants (ONLY these; no tuning, no extra knob)

- REF = G2 unchanged (R2B1D17BFG2: 5.41 %/mo 5y, max yearly DD 16.91,
  full-path DD 16.82, from `v421/v421_result.json`). Reproduce to the digit first.
- REF_CARRY = G2 + carry f=0.25 compounding account (`oc_carrycompound`:
  5.634 %/mo, maxDD 16.75, full 16.66). Reference only, never selected.
- V1 = yearly weights proportional to 1/trailing-4y sleeve maxDD
  (pre-anchor, 7d embargo); rebalance yearly; carry weight capped 0.5.
- V2 = yearly weights proportional to 1/trailing realized-vol
  (same window/embargo); rebalance yearly; carry weight capped 0.5.
- CTRL-EQ = exposure-matched control: FIXED (1/3, 1/3, 1/3) capital-split,
  rebalanced yearly (same exposure=1.0, static; isolates dynamic vs static).
- S5-APPROX = Bybit-price diagnostic for the dev4 pick ONLY (see Mechanism S5).

## Frozen inputs (read-only, never edited)

- `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl` +
  `v421_result.json` row R2B1D17BFG2 (G2 baseline).
- `research/parallel/rounds/parallel-20260906-r2/v388/v388_bot_stop_distance.py`
  (`hourly`, `mix`, ANCH 2021..2025-09-24, Y1 2026-09-23).
- `research/diagnostics/r2_decompose5/reset_metric.py` (`year_reset` arithmetic).
- `research/tournament/oc_bookattrib/tmp/bookonly_runs.pkl` (G2 book-only,
  sleeve=False, 4 phases; same v421 mechanism/gate costs).
- `research/tournament/oc_cashcarry/results.json` (33 entered frozen carry
  trades, fees spot 0.001/side + fut 0.00055/0.0002) + `oc_carrycompound/
  analyze_carrycompound.py` mtm logic (causal hourly closes, held to delivery,
  spanning rebased at resets).
- `research/tournament/ext/hourly_ext.parquet` (spot hourly closes),
  `data/raw/qbasis_20261003/um_*_1h.parquet` (futures hourly),
  `data/raw/spot_majors_20260925/BTCUSDT_spot_4h.parquet` (delivery grid).
- `research/tournament/oc_c2bybit/tmp/runs_S5.pkl` (REF G2 on Bybit prices,
  S5) + `tmp/c2bybit_table.json` (REF_S5 baseline numbers, read-only context).
- CLOSED rows read first: oc_corrbudget + oc_idiocap (WITHIN-sleeve scaling —
  this is ACROSS-sleeve), oc_governor (kill-switch — this is continuous
  weights), oc_phaserebal (rebalances the SAME strategy — this reallocates
  across sleeves), oc_carrymore (carry cap/borrow: peak 2.0x spot needs borrow).

## Mechanism (frozen; overlay, no new strategy engine except one gap-fill)

- GAP-FILL (data construction, NOT a variant): G2 dip-only standalone equity
  does not exist (book-only does). Run ONE dip-only 4-phase engine exactly
  mirroring `oc_bookattrib/run_bookonly.py` except books×0.0 with sleeve ON
  (same v421 overrides: inv rule, kd 1.7, risk_mult 1.0, budget 0.26×1×1.7,
  cap G=2.0, bear books, win_start=5, gate costs maker 0.0002/taker 0.00055,
  longs 0.0001/8h shorts 0, limit trade-through, stop-first). Output
  `tmp/diponly_runs.pkl` (t/eq/eq_min per shift). No selection on it.
- Hourly sleeve equities on grid GRID0=2021-09-24 04:00 .. G1=Y1+12h via
  `v388.hourly`: E_book, M_book (from bookonly), E_dip, M_dip (from diponly),
  E_g2, M_g2 (from v421, validation only).
- Carry unit sleeve: same per-trade hourly mtm as oc_carrycompound at f_unit=1.0
  per pair entry (N=1.0× sleeve capital; linear in f so f=0.25 series ×4;
  fees/delivery identical), rebased to 0 at each year start (fresh allocation).
  Standalone carry year equity from 1.0: E_carry via capital-split recursion
  below with w_c=1. Carry marks are causal hourly closes (lower bound, no
  intra-hour low); state borrow flag (peak concurrent notionals, cf oc_carrymore).
- Allocator accounting (capital-split, exposure always 1.0): at each anchor A,
  weights (w_b, w_d, w_c) sum 1 (cap applied, see below). Intra-year, each
  sleeve compounds independently from 1.0 at A+; combined close/marked:
  A(t)=w_b·E_b(t)+w_d·E_d(t)+w_c·E_c(t),
  M(t)=w_b·M_b(t)+w_d·M_d(t)+w_c·M_c(t) (M_c uses carry close marks, lower bound).
  Year R from A_end (geometric monthly), DD from M vs peak of A (v421 convention).
  Full-path: product of yearly factors for R; continuous A from grid start with
  yearly rebalancing (no transfer cost assumed, stated) for full-path DD
  (max of marked/close DD). Per-sleeve gross/net reported (book/dip legs already
  net of fees+adverse funding; carry net of entry/delivery fees; no cost smuggled).
- Weight rule (frozen): trailing window W(A)=[A−1460d, A−7d] intersected with
  grid; if available length <180d use equal weights (1/3 each, cap moot).
  V1 metric per sleeve = maxDD over W on sleeve equity (rebased 1.0 at W start,
  DD=max of close/marked, v421 formula; floor 0.5% to avoid div-0).
  raw w_i=(1/DD_i)/Σ(1/DD). V2 metric = std of hourly simple returns (close
  equity) over W (floor 1e-6); raw w_i=(1/vol_i)/Σ(1/vol). Cap: if raw w_c>0.5,
  set w_c=0.5 and rescale w_b,w_d to 0.5 preserving their ratio; renormalize.
  Rebalance dates fixed at anchors (year starts). Weights use ONLY data ending
  before anchor−7d (fits/thresholds: none; no test-year statistic feeds any choice).
- Exposure-matched control: CTRL-EQ fixed (1/3,1/3,1/3) with identical accounting
  (same exposure 1.0, same rebalancing, same carry unit). No other control.
- S5-APPROX (dev4 pick only, diagnostic, labelled): BOT leg = Bybit-based G2
  total hourly (REF from runs_S5.pkl via v388.hourly); carry leg = same hourly
  marks (venue-independent); pick's yearly carry weights (frozen from Binance
  pre-anchor fit) reused WITHOUT refit; book/dip split on Bybit NOT re-estimated
  (stated limitation — full sleeve-split S5 would need 8 extra Bybit phase sims).
  Additionally quote REF_S5 baseline (dev4 4.994/W 2.129/maxDD 18.11, from
  oc_c2bybit, read-only) for context. S5 never selects.

## Windows / metrics (fixed)

- Anchors 2021..2025-09-24; dev4 = years 0..3 ([A,A+365d)); Y4 = 2025-09-24..
  2026-09-23 scored ONCE, only for the robust pick + REF (+REF_CARRY as labelled
  ref); 5y = years 0..4 (reported, never selected).
- Per-year 4-phase reset %/mo + DD (reset_metric arithmetic on the combined
  capital-split path); dev4/5y geo mean, W (worst-year R), max yearly DD, losing
  count; full-path DD continuous from 2021-09-24 (max of reset DDs and full-path
  for the gate). No trade/win-rate rows (overlay has no fills; engine legs
  inherit gate fills; state it).
- Reproduction gate (STOP if failed): f=0 / REF path reproduces v421_result G2
  years [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27),(4.648/12.90)]
  to the digit, 5y 5.410, full-path DD 16.82; carry f=0.25 leg reproduces
  oc_carrycompound G2_f0.25 years to the digit (validates mtm reuse).
- Verdict rule (fixed robust criterion): among V1/V2 with dev4 DD≤20 and no
  losing dev year, prefer dev4 mean≥5 (if any), then highest dev4 WORST, ties→mean.

## Leakage / contamination (pre-registered checks, stated in REPORT)

- Feature timing: sleeve equities are engine outputs on causal 4h/1m data
  (win_start=5, trade-through, stop-first inherited); allocator reads sleeve
  values only up to anchor−7d for weights; intra-year A(t) uses sleeve values
  at t (overlay scoring, not a feature).
- Label windows: no labels fit here; carry trades frozen (t_exit<A−7d inherited).
- Fit windows: weights from W(A) only (ends anchor−7d); year y uses anchor-y
  weights only, never later; S5 reuses frozen weights (no refit on Bybit).
- Fill timing: no fills in overlay; engine legs use gate fills (asserted by reuse
  of frozen runners; diponly mirrors bookonly source).
- Truncation test: recompute year weights from truncated sleeve tables — identical
  on kept prefix; cap logic covered by synthetic hand-check.

## Compute plan (heavy_slot, resume-safe)

- `compute_diponly.py`: dip-only engine (mirrors run_bookonly.py, books×0),
  via `heavy_slot run --tag oc_sleevealloc_dip --min-free-gb 2.0`, heartbeat
  every 600 s, writes `tmp/diponly_runs.pkl` + `tmp/diponly_years.json`.
- `analyze_sleevealloc.py`: CPU-only overlay (hourly grid ~44k rows, 4h+1h only,
  no 1m) → `tmp/sleeve_table.json`; REPORT.md + results.json written from it only.
- Deliverables: PLAN.md (this file), compute_diponly.py, analyze_sleevealloc.py,
  results.json, REPORT.md, tests/test_oc_sleevealloc.py.

## Post-hoc log

- 2026-10-08, before any result was written: fixed a double-/100 in `metric_dd`
  in `analyze_sleevealloc.py` (`dd_of` already returns a fraction; the extra /100
  pinned every sleeve at the 0.5% floor so V1 printed equal weights) plus a
  dict-index KeyError on the Y4 REF row. The first run crashed before writing
  `results.json`; no selection had been made. Variants, windows, rules unchanged.
