# Blind audit of two dev-only diagnostics (2026-10-05) (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)

Write only under `research/diagnostics/diag_20261005_audit/` and `tests/test_diag_20261005_audit.py`; relative paths without quoting;
at most 2 heavy processes; do not edit leader files or the two diagnostic folders.

## 1. research/diagnostics/rolling_anchor_dips (event study)
Spec = the module docstring of rolling_anchor_dips.py. Part A (blind): write your OWN implementation (do not import the leader module) of the
anchored rule A_s (s = 0..3, k = 3.0 only) and the rolling rule R_open (k = 3.0) for BTCUSDT and SOLUSDT, minutes < 2025-09-24, using the same
1m files (data/raw/btc_intraday_20260924/klines_1m_20*.parquet, data/raw/majors_intraday_20260924/SOLUSDT_1m_20*.parquet) and sigma = std of
4h open-to-open returns (resample("4h").first() of 1m opens) over 360 bars, min 120, value of the bar containing the minute. Exactly as the
docstring: strict trade-through fills at the level (low < L), anchored bids live minutes 16..238 of the bar, exits checked from the minute after
the fill, stop touch low <= L(1 - 8 sigma) at min(stop, minute open), TP high > L(1 + sigma), same-minute tie -> stop, anchored time exit at the
next bar open, rolling time exit at the open of minute fill + 241, rolling re-arm max(fill + 240, exit minute + 1); entry maker 0.0002, TP
maker 0.0002, stop / time taker 0.00055. Save part_a.json (per rule, coin, period: n, sum, mean) BEFORE opening rolling_anchor_dips.json /
run.log. Part B: rerun the leader script restricted to these two coins (import it and call anchored / rolling / summarize) and compare
(n must match exactly; sum within 0.01). Check look-ahead: the rolling anchor and sigma must use only data before the fill minute.

## 2. research/diagnostics/manual_human (MANUAL human schedule)
Spec = the docstring of manual_human.py. Part A (blind): reproduce rows M2_human and M5_human on phase s = 1 only, with your own wiring of
phase_offset_full prep_idx / pipe_setup and engine_user.simulate (night bar = holding bar starting at (20 + s) UTC: book policy returns "wait"
when flat and "hold" in a position, sleeve_filter 0; win_start 15, sleeve_start 16), dev years only; save part_a.json (yearly net % and 1m DD)
BEFORE opening manual_human.json / run.log / manual_human_runs.pkl. Part B: compare with the stored phase-1 rows (net > 0.1 pp or DD > 0.05 pp
= mismatch) and confirm M5_base on phase 1 equals v377's M5 phase 1 (research/parallel/rounds/parallel-20260906-r2/v377/run.log).
Check that the skip uses the holding-bar start hour (idx + 4h) and that no future data enters the policy.

Write COMPARISON.md with a "## Verdict" line per diagnostic (PASS / FAIL) and the mismatches, if any.
