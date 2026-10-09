# oc_bybitfill PLAN (pre-registered BEFORE any outcome, 2026-10-08)

Assignment: `docs/opencode/OPENCODE_W_oc_bybitfill.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
(+ AGENTS.md, OPENCODE_VF_COMMON.md read). Write ONLY `research/tournament/oc_bybitfill/`
+ `tests/test_oc_bybitfill.py`. Engine runs via heavy_slot (one engine job at a time;
RAM tight). Progress heartbeat every 10 minutes (600 s). Scratch only under
`research/tournament/oc_bybitfill/tmp/`.

## Why (given)

oc_bybitgap: G2 loses ~0.5 %/month on Bybit prices (5y 5.410 -> 4.883) and the gap
rides the dip ladder: fewer rung fills (-25/-57) and fewer take-profit fills
(-34/-59) because Bybit 1m wicks are shallower; the engine only fills a limit on a
strict trade-through. A TP placed a few bps lower fills more often for a tiny price
give-up; a rung a few bps shallower fills more often.

## Variants (ONLY these two; everything else exactly G2)

- REF_S5 = G2 unchanged (R2B1D17BFG2: rule inv, k 1.0, kd 1.7, bear True, G 2.0,
  v321 pipe with R2 agents ON) run on Bybit prices (= S5 friction of
  research/parallel/rounds/parallel-20260906-r2 v421_audit / oc_c2bybit).
- TPm3: every dip take-profit limit 3 bps BELOW the G2 TP price (still a maker
  limit). Formal: let lv = G2 rung limit, mu = learned sleeve_tp, sg = sleeve sigma.
  G2 TP = lv*(1+mu*sg). Variant TP = G2_TP * (1 - 0.0003). Rung (lv), stop
  (lv*(1-4*sg)), sizes, books, costs unchanged. Fill price of a TP exit = TP.
- RUNp3: every dip rung limit 3 bps ABOVE the G2 rung price (shallower) PLUS TPm3.
  Formal: lv' = lv * (1 + 0.0003) (fill price = lv'); TP base from the SHIFTED rung
  TP0 = lv'*(1+mu*sg), then TP' = TP0 * (1 - 0.0003); stop from the shifted rung
  sl' = lv'*(1-4*sg) (same sigma multiple); backstop (close5 mode, 8 sigma) from lv'
  likewise. Everything else exactly G2 (sizes incl. kd 1.7 corr, budgets, books,
  bear filter, G 2.0, costs, win_start, stop-first).
- No other knob. If anything changes after seeing an outcome, the original row stays
  and the change is added as a disclosed extra row (none planned).

## Fixed settings (frozen)

- Gate costs inside the engine: maker 0.0002 (entries, TPs, dip fills), taker 0.00055
  (stops, market/timeout exits); longs pay 0.0001 per 8h settlement held (00/08/16
  UTC), shorts receive nothing. Limits fill only on a 1m strict trade-through
  (low < limit for dip buys; high > limit for dip TPs); no book fill in the first 5
  minutes after a 4h close (win_start=5); dip ladder live from sleeve_start=16
  (v321 default); stop-first when stop and TP are both touched in the same 1m bar.
- Mechanism = verbatim G2 pipe: 4 phases (shifts 0..3, 4h grid opens at s, s+4, ...
  UTC); pipe v321 via phase_offset_full.pipe_setup; corr-aware dip sizes
  mult 1/(1+n)*1.7*base (n = coins with C<=O*(1-2.5*sig) at minute f-1); risk_mult 1.0;
  sleeve_risk_budget 0.26*1*1.7; sleeve_gross_cap G=2.0; bear books (BTC 4h open <
  1200-bar mean halves LONG targets; standard rows, before shifted-clock ffill);
  close5 stop (m_sleeve_sl 4.0) + 8-sigma native backstop; rungs (2.5,3.0,3.5,4.0,5.0).
- Implementation of the offsets: a vendored engine_user.simulate copy inside this
  folder (`engine_patch.py`) with two extra params `dip_rung_mult` (default 1.0) and
  `dip_tp_mult` (default 1.0), applied at exactly the two price lines:
  `lv_doc = o1*(1-k*sig) * dip_rung_mult` (fill detection `L < lv_doc`, fill price
  lv_doc, stop/backstop from lv_doc) and `tp_doc = lv_doc*(1+mu*sg) * dip_tp_mult`
  (touch `H > tp_doc`, exit price tp_doc). All other lines byte-identical to
  research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py.
  REF rows use (1.0, 1.0) and must reproduce to the digit (validates the patch);
  TPm3 = (1.0, 0.9997); RUNp3 = (1.0003, 0.9997). TPm3 alone is exactly reproducible
  by a sleeve_tp-mu wrapper, but the single patched engine is used for all rows so
  REF and variants share one code path.
- Frictions:
  - base (Binance): `pod.minutes()`, standard index + shift, win_start=5.
  - S5 (Bybit): `bybit_minutes()` from data/raw/bybit_linear_1m_20261004/<SYM>_1m.parquet
    (open_time ms -> UTC), live0 = 2021-11-15 + shift; standard index filtered to >=
    2021-11-15 before shift; win_start=5. Year 2021 on S5 is a SHORT window from
    2021-11-15 (labelled everywhere). If Bybit files are missing/unreadable, report
    S5 as not reproducible (no silent fallback).
- Rows (6 engine rows x 4 phases = 24 phase sims): REF_base, TPm3_base, RUNp3_base,
  REF_S5, TPm3_S5, RUNp3_S5. Base rows are the Binance side row (labelled, NOT for
  selection); S5 rows are the selection set. REF_base is the gap anchor.
- Anchors 2021-09-24 .. 2025-09-24; dev4 = years 0..3 ([A,A+365d)); Y4 =
  2025-09-24..2026-09-23 scored ONCE, labelled (already scored once for G2 by v421,
  so every Y4 number here is a labelled re-score); 5y = years 0..4.
- Metrics: per-year 4-phase reset %/mo + DD via reset_metric.year_reset;
  dev4/5y geometric mean, W (worst-year R), max yearly DD, losing count; full-path DD
  via v388.mix equal-1/4 mix from 2021-09-24 (max of reset DDs and full-path for the
  gate); pooled book/rung/all win rates + fills/year + rung fills/TPs/stops/timeouts
  and TP rate per row (same event collection as oc_chronos run_engine.py).

## Reproduction gate (STOP if failed, scored BEFORE any variant claim)

- REF_base years 0..4 R/DD == v421_result.json R2B1D17BFG2
  [(2.588/10.86),(3.282/16.91),(6.045/15.81),(10.677/8.27),(4.648/12.90)] to the
  digit, 5y 5.410, full-path DD 16.82.
- REF_S5 years == oc_c2bybit REPORT/results.json REF_S5
  [(2.129/12.36),(2.735/18.11),(4.932/16.89),(10.377/9.22)] to the digit,
  Y4 4.443/12.37 (labelled), 5y 4.883, full-path DD 18.09.
- Bybit gap anchor: 5y 5.410 -> 4.883 = 0.527 pp/mo; dev4 5.601 -> 4.994 = 0.607.

## Selection / verdict rule (fixed)

- Compare and choose ONLY on dev4 (anchors 2021..2024). Robust criterion: DD <= 20
  and no losing dev year; prefer dev4 mean >= 5 %/month, then the highest dev4
  WORST-year monthly return, ties -> higher mean. Y4/5y are reported once, labelled,
  never selection inputs.
- Verdict reports: dev4 table on Bybit (REF_S5/TPm3/RUNp3), Y4 labelled once, 5y,
  full-path DD, fill/TP counts vs REF_S5 (rung fills, TP fills, TP rate, stops,
  timeouts), and the same two variants on Binance as a labelled side row.
  Recovery share = (variant_S5 - REF_S5) / (REF_base - REF_S5) per window.
  Vietnamese 3-line verdict: how much of the Bybit gap does each recover.

## Leakage / contamination (pre-registered checks, stated in REPORT)

- Feature timing: dip levels use O(T) + trailing sigma (minutes strictly before the
  holding bar); fills use live minutes only (book win_start=5, dip sleeve_start=16);
  TP/rung mults are constants (0.9997/1.0003), no fit, no threshold tuned on any year.
- Label windows: no labels fitted; engine uses the realised 1m path.
- Fit windows: no refit; R2 size/TP tables reused frozen (shift-specific, embargoed
  upstream); year y uses only its own bar lookups; S5 grid change is a price-source
  switch, not a fit. No statistic from any test year feeds any choice.
- Fill timing: strict trade-through (`low < lv_doc`, `high > tp_doc`) asserted in
  tests; win_start/sleeve_start per friction asserted; stop-first in shared 1m bar
  (inherited harness); no fill in the first 5 minutes after a 4h close.
- Contamination: no foundation model used here; dev years are research data, Y4 is
  the labelled post-release re-score (diagnostic).

## Compute plan (heavy_slot, resume-safe)

- `engine_patch.py`: vendored engine_user.simulate with dip_rung_mult/dip_tp_mult
  (defaults reproduce bit-for-bit; verified by REF gates).
- `compute_bybitfill_engine.py`: sequential shifts 0..3 per row (one heavy process
  at a time), heartbeat print every 600 s, caches `tmp/runs_<row>.pkl` (resume-safe:
  skip cached shifts), final merged dict. Invoked as
  `.venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_bybitfill_eng
  --min-free-gb 2.0 -- .venv/Scripts/python.exe
  research/tournament/oc_bybitfill/compute_bybitfill_engine.py [--row ...]`.
- `analyze_bybitfill.py`: CPU-only scoring (reset metric + v388.mix + wins/fills) ->
  `tmp/bybitfill_table.json`; REPORT.md + results.json written from that table only.
- Deliverables: PLAN.md (this file), engine_patch.py, compute_bybitfill_engine.py,
  analyze_bybitfill.py, results.json, REPORT.md, tests/test_oc_bybitfill.py
  (>=1 causality/truncation test + >=1 hand-checked synthetic case;
  `.venv/Scripts/python.exe -m pytest tests/test_oc_bybitfill.py -q`).
- Progress printed every 10 minutes during engine runs (heartbeat thread).
- Stop when done.

## Post-hoc log

- (empty; any change after an outcome is logged here with date + reason; the
  original row stays and the change is a disclosed extra row.)
