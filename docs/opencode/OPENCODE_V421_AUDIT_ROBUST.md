# v421 blind audit + robustness of R2B1D17BFG2 (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v421 (research/parallel/rounds/parallel-20260906-r2/v421; docstring = pre-registration). Rows: R2B1D17BF (= v411 cache), R2B1D17BFG3, R2B1D17BFG2 =
R2B1D17BF (B1 x 1/(1+n) at 2.5 sigma, kd 1.7, budget 0.26 x 1.7, bear-book longs x0.5) + the NEW engine hook sleeve_gross_cap G (3.0 / 2.0): a new dip
rung is cut to the room left under G (sum of notional/equity t[7] of the rungs still open at the fill minute, per phase) and skipped when no room
is left. Check the engine diff (git log -p -- research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py: G None must be
bit-for-bit the old code).
Harness: 4 phases 2021-09-24..2026-09-23, reset metric research/diagnostics/r2_decompose5/reset_metric.py, full-path conservative DD of the
continuous 1/4 mix (v388.mix). Write only under `research/parallel/rounds/parallel-20260906-r2/v421_audit/` and `tests/test_v421_audit.py`;
at most 1 heavy process; relative paths; do not edit leader files.
PART 1 (blind, before opening v421_result.json / run.log / v421_runs.pkl): reproduce R2B1D17BFG2 on phases 1 and 3 with your own wiring; save
replication.json. PART 2: compare (final equity relative > 1e-6 = mismatch), recompute rows / folds / final / full-path DD -> COMPARISON.md with
"## Verdict" and a line "v421: PASS" or "v421: FAIL". PART 3 robustness for R2B1D17BFG2 exactly as v411_audit/ROBUST.md did for R2B1D17BF (reuse its
script): all-trade and book win rates per year and pooled; full-path DD; frictions S1 cost stress, S2 latency 15, S3 latency 30, S4 stop slip 0.5,
S5 Bybit prices (from 2021-11-15) with per-year %/month, 5y mean, max year DD, full-path DD; put R2B1D17BF's numbers from v411_audit/ROBUST.md
next to them. Also report the max dip gross notional / equity per phase for G2 vs D17BF. ROBUST.md with the verdict vs the base gate
(5y mean >= 5, every-year DD < 20, full-path DD <= 20, win > 55 %).
