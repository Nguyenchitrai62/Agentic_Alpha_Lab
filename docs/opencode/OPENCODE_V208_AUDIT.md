# v208 blind audit (read AGENTS.md (2026-09-27), .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v208_audit/` and `tests/test_v208_audit.py`. Use
relative paths without quoting. Do NOT open v208/ until part A is saved (`replication.json`). Base: your v205 replication.

A: the v205 pipeline (books = 0.5 * (A+B)/2 annual + 0.5 * (Aq+Bq)/2 quarterly v151 members, aligned sleeve x1.5/x0.5,
engine_user settings m_sl=4, m_sleeve_sl=5, sleeve risk budget 0.12, size_mult 1.5, limit window minutes 2..238) with four
execution policies for the BOOK orders only (the dip sleeve is unchanged). A book order exists exactly when the engine
already sends one (|target - current weight| * equity * 10k >= the symbol minimum notional, or closing to zero):
- ref: limit at the minute-0 open of the holding bar -/+ 0.10% (maker 0.0002), filled on a 1m trade-through, else expires.
- A: same limit rule with offset = max(0.10%, 0.25 * sigma_4h); sigma_4h = rolling std (360 bars, min 120) of 4h
  open-to-open returns, the value on the decision row (same array the engine calls sig4).
- B: A, except a MARKET fill at the holding bar's minute-0 open with taker fee 0.00055 when the order opens from flat
  (|current weight| < 0.005 and |target| >= 0.005) or flips side (signs differ, both |.| >= 0.005) AND |target| >= 0.10.
- C: B, plus: skip the order (keep the position, count as skipped) when it is neither closing (target == 0 and weight != 0)
  nor opening/flipping (definition in B) and |target - weight| < max(0.02, 0.25 * |target|).
For each policy report dev4 (geometric mean monthly of anchors 2021-2024), worst first-four-year monthly, gate DD
(max of 4h-close and 1m-marked, full path), fills, unfilled, market count, skipped count, fees. Selection = robust
criterion (AGENTS.md) over the four rows; report the most recent year ONLY for the selected row. Check causality: sigma_4h
and the current weight are known at the decision; market fills happen at minute 0 of bar t+1, never at bar t.
Save `replication.json`.
B: compare with `v208/v208_result.json` (tolerances: return > 0.01pp/month, DD > 0.05pp, counts exact). Write COMPARISON.md
with a PASS/FAIL verdict. Do not report the most recent year of non-selected rows. Do not edit leader files.
