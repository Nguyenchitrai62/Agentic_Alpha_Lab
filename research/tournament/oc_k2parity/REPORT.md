# oc_k2parity — REPORT (2026-10-08)

## Question
Does the LIVE feed (scripts/kronos_shadow.py backfill) reproduce the RESEARCH
features (research/tournament/oc_kronoshidden/kronos_features_4shift.parquet)?
Paper runner paper_d17bfg2k2 sizes dip rungs with live k2_mult; the K2 evidence
was computed on the research path.

## Method (pre-registered in PLAN.md, no changes after outcomes)
- Live: kronos_shadow.py --once --backfill-hours 552 --now 2026-09-23T23:00Z,
  own out research/tournament/oc_k2parity/kronos_features_live_backfill.parquet
  (2760 rows, 5 syms x 552 hourly T, all 4 shifts, mode=backfill). GPU via
  heavy_slot --tag oc_k2parity. Never touched
  artifacts/research/kronos_shadow/kronos_features_live.parquet (read-only).
- Research ref (frozen, read-only): kronos_features_4shift.parquet (260,325 rows)
  + bars_4h_4shift.parquet. Join on (sym, shift, T): 2745 rows; 15 live rows
  (2026-09-23 21/22/23, shifts 1/2/3) have no research counterpart — expected:
  research 1m ends 23:59 so those trailing bars are incomplete and dropped;
  live with October server time sees them complete. Not a code difference.
- Code diff: DIFF.md (8 areas). Only intended difference = per-row seeds
  (live hash-seed vs research sequential seed 1234 + resumed XRP s2-3 stream).
- MC baseline: research math re-run on first 60 joined rows with two seeds
  (tmp/mc_research_rerun.py, S=64, GPU): own k2 disagreement rate.

## Results
- Bar OHLC equality (live 1h-agg vs research 1m-agg, joined T): max rel diff
  0.0 EXACT on open/high/low/close, all syms/shifts (tmp/bar_compare.json).
- sigma: Spearman 1.0000, max abs diff 4.2e-16, median 8.3e-17 — bit-identical.
- low1: Spearman 0.9820 overall (BNB 0.9848 / BTC 0.9840 / ETH 0.9721 /
  SOL 0.9753 / XRP 0.9878), median abs diff 0.0723, max abs 0.8577.
  Same ballpark as the known S=64 sampling scatter (oc_kronoshidden shift-0
  overlap: rho 0.9686, medabs 0.0699).
- k2_mult (frozen anchor-2025 rule, recomputed both sides; live stored column
  verified identical): disagreement 4.55% (125/2745).
- MC baseline (research vs itself, different seeds, n=60): k2 disagreement
  10.0% (6/60, Wilson 95% CI 4.7-19.9%), low1 med abs 0.0665, rho 0.956.
- Live-vs-research (4.55%) is BELOW the MC point estimate (10.0%) and inside
  its CI; low1 med-abs matches MC to 0.006. No symbol/shift outlier, no bias
  (sigma exact rules out any bar/scale systematic).
- model_sha live f73e6a5a081e matches the running shadow file's rows.

## Verdict: PASS
Live == research up to Monte-Carlo noise. No code fix needed. The paper log
tests the same signal that was researched (modulo S=64 sampling scatter, which
moves k2_mult on ~5-10% of rows either way). Note for the leader: future
live/research joins should expect ~5% k2_mult flicker from seeds alone; do not
mistake it for a data bug. The 15 extra Sep-23 live rows are a benign edge
effect of the research 1m cutoff.

## Vietnamese verdict
K2 live khớp research tới nhiễu Monte-Carlo: bar/sigma khớp từng chữ số,
low1 rho 0,982, k2 khác 4,55% (thấp hơn mức nhiễu nội tại 10%).
Kết luận: PASS — paper_d17bfg2k2 đang test đúng signal đã nghiên cứu.
Đề xuất: không sửa code, chỉ ghi nhận flicker ~5% k2 do seed khi join sau này.
