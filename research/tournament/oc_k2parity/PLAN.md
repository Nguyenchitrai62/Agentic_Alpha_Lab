# oc_k2parity — PLAN (pre-registered 2026-10-08, before any outcome)

## Question
Does the LIVE Kronos K2 feed (scripts/kronos_shadow.py) reproduce the RESEARCH K2
features (research/tournament/oc_kronoshidden/run_inference_4shift.py from
1m-derived 4h bars)? The paper runner paper_d17bfg2k2 sizes dip rungs with
k2_mult from the live shadow file; the K2 evidence was computed by the research
path. A difference means the paper log tests a different signal.

## Fixed settings (no tuning)
- Window: T in [2026-09-01 00:00 UTC, 2026-09-24 00:00 UTC) (all hourly T the
  live path produces; each hour = one shift grid bar open). All 5 majors
  (BTC/ETH/SOL/BNB/XRP USDT), all 4 shifts.
- Live path: `scripts/kronos_shadow.py --once --backfill-hours N --now <t> --out
  research/tournament/oc_k2parity/kronos_features_live_backfill.parquet`
  (own --out; never touches artifacts/.../kronos_features_live.parquet).
  Settings frozen in that script (P=400,H=6,S=64,T=1.0,top_p=0.9,top_k=0,
  SIG_WIN=360, fits.json anchor-2025 direction=1 q20=0.5872428352509342
  q80=2.182801599162049, hi/lo=1.25/0.75).
- Research reference: research/tournament/oc_kronoshidden/kronos_features_4shift.parquet
  (frozen, read-only) + bars_4h_4shift.parquet for bar OHLC join.
- Join key: (sym, shift, T). Inner join only.
- GPU via heavy_slot (`--tag oc_k2parity`, never --leader); torch before pandas.

## Pre-registered metrics (computed once, reported as-is)
1. Bar OHLC equality of the live context vs research bars: max relative diff
   over (open,high,low,close) on joined (sym,shift,T) context bars; share exact.
2. sigma: Spearman + max abs diff + median abs diff.
3. low1: Spearman correlation + max abs diff + median abs diff.
4. k2_mult agreement: share of joined rows whose k2_mult differs (live vs research).
5. MC-noise baseline: re-run the RESEARCH math on the same joined rows with two
   different per-row seeds (hash seed A vs B, S=64) on a fixed subsample
   (first 60 joined rows by (T,shift,sym) to bound GPU), report its own k2_mult
   disagreement rate. Verdict compares (4) against (5).
- Verdict rule: PASS iff live-vs-research k2_mult disagreement <= MC baseline
  disagreement + small tolerance AND low1 rho >= 0.9 AND no systematic bias
  (median low1 diff ~ 0); else FAIL with a concrete fix proposal for the leader.
- Leakage: no forward returns computed for dates >= 2025-09-24 in this study;
  only feature parity (no outcome data). Fit constants frozen from fits.json
  anchor 2025 (fit window ends 2025-09-17, embargo 7d).

## Outputs (only these paths)
- research/tournament/oc_k2parity/{PLAN.md,DIFF.md,REPORT.md,results.json,
  kronos_features_live_backfill.parquet,tmp/}
- tests/test_oc_k2parity.py (causality/truncation + hand-checked synthetic case)
