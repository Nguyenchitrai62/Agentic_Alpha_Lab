# oc_oos12d — PLAN (G2 on genuinely-new 2026-09-24 .. last complete day)

## Window
- OOS = 2026-09-24 00:00 UTC .. end of last complete UTC day at runtime
  (2026-10-05 inclusive expected; if 2026-10-06 completes, extend and state).
- Tiny sample (~12 days, ~72 4h bars), clean: never used in research (all research ≤ 2026-09-23).

## Honesty decision (no refit, no parameter change)
- Frozen members end 2026-09-23 (`member_A_O1_orders`, `members_v154` D, etc.).
- `shadow.jsonl`: v240_O1 valid prospective rows sparse + 429 errors, start 2026-09-28;
  v285_CB is member-D only, start 2026-09-29. Full-window G2 book (0.8×O1+0.2×D,
  `forward_v205.research_books_d2`) can NOT be reconstructed honestly → **dip sleeve
  alone (rule-based), books=0**, stated in REPORT/results.
- R2/G2 agent tables (`v321_r2_table`, `v301_g2_table`) are walk-forward fits ending
  2026-09-23 with no OOS rows → NOT used (size 1.0, default TP). No `ADVISOR_ASOF`
  backfill rows (`mode=backfill`) used as evidence; prospective-only if books were used.

## Engine (G2 dip component, gate costs, 4 phases)
- `engine_user.simulate` with books=0, 4 clock shifts s=0/1/2/3h (same as
  `oc_expiry4p`/`eval_candidate` harness: ffill books→trivially zero, `win_start=5`).
- Dip params frozen: v321 rules via `history_tm.KW_OVERRIDE["v321"]`
  (rungs 2.5/3.0/3.5/4.0/5.0, `sleeve_risk_budget` 0.26, `sleeve_stop_mode` close5,
  backstop 8.0, `m_sleeve_sl` 4.0) + v421 G2 overlays (`inv` corr size kd=1.7,
  budget ×k×kd, `sleeve_gross_cap` G=2.0). No agent size/TP lookup.
- Gate costs: maker 0.0002 / taker 0.00055, adverse funding longs 0.0001/settlement,
  shorts 0; stop-first; 1m-marked DD. Trade-mode `trade=v216.GRID` policy object is
  passed but inert with books=0 (book fills expected 0; asserted).
- Warmup: sig4/vol need history → read existing `data/raw/*intraday*` (read-only) +
  new OOS 1m; features at bar t use only minutes ≤ t+4h holding bar (engine cube).

## Data (only new files allowed)
- New 1m ONLY under `data/raw/majors_1m_oos_20261006/`: public Binance
  `data.binance.vision` daily kline zips (FUTURES um/daily/klines, 1m) for the five
  majors USD-M, CHECKSUM-verified, polite rate + retry. 4h opens derived from 1m
  in-memory (no extra data files).
- Expected last-complete-day coverage asserted per symbol (1440 minutes/day);
  gaps → fail loudly, no fill-forward across days except engine's intrabar ffill.

## Expectation band
- Bootstrap historical 12-day (72-bar) windows from `v421_runs.pkl` G2
  (`R2B1D17BFG2`) 4-phase per-year-reset equity (same `reset_metric`/`v388.mix`
  convention as v421 where feasible; fallback: per-shift equity resampled to daily,
  documented): N=10000 random windows, report total-return p5/p50/p95 + percentile
  of OOS return, plus median 12-day max-DD band. OOS is ONE tiny sample → no gate
  claim.

## Outputs (ONLY these paths)
- `research/diagnostics/oc_oos12d/PLAN.md` (this), `oc_oos12d.py`, `REPORT.md`,
  `results.json` + `tests/test_oc_oos12d.py`. No commits. Run is small (<0.4 GB);
  no `heavy_slot` needed (stated; use it if the engine exceeds the threshold).
