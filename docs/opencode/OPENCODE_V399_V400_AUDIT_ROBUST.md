# v399 + v400 blind audit and robustness of the candidate R2B1_130 (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Versions research/parallel/rounds/parallel-20260906-r2/v399 and v400 (docstrings = pre-registration). Correlation-aware dip size: at the fill
minute f of a rung of coin a in holding bar i, n = number of OTHER majors b with C[i, f-1, b] <= O[i, 0, b] * (1 - 2.5 * sig4[i][b])
(prep cubes from phase_offset_full.prep_idx); size x 1/(1+n) (B1) or x0.5 if n >= 2 (B2), times the deployed agent size; v400 adds
risk_mult k on the governor and sleeve_risk_budget 0.26 k. Harness: 4 phases, 2021-09-24..2026-09-23, per-year reset metric
research/diagnostics/r2_decompose5/reset_metric.py. Write only under `research/parallel/rounds/parallel-20260906-r2/v399_v400_audit/` and
`tests/test_v399_v400_audit.py`; at most 2 heavy processes; relative paths; do not edit leader files.
PART 1 (blind, before opening v399/v400 result JSONs, run logs or pkls): (a) check the n computation is causal (minute f-1 only; the engine
calls sleeve_fill_size(i, a, r, f) with f = the fill minute - read engine_user.simulate to confirm); (b) reproduce R2B1 (v399) on phase 0 and
R2B1_130 (v400) on phases 1 and 3 with your own wiring; save replication.json. PART 2: compare (final equity relative > 1e-6 = mismatch),
recompute rows / folds / final from the pkls -> COMPARISON.md "## Verdict" per version.
PART 3 (robustness of R2B1_130, after Part 2; one scenario at a time, 4 phases each, events collected): (i) all-trade win rate (book trades
via v221.v216.v213.trade_stats + dip rungs rung_tp / rung_sl / rung_timeout, as phase_offset_full.book_win) per year and pooled, and the book
win rate; (ii) full-path conservative DD of the equal 1/4 mix started 2021-09-24 (v388.mix) and the max of yearly reset DDs; (iii) frictions as
research/diagnostics/r2_4p_robust5 (S1 cost stress, S2 latency 15, S3 latency 30, S4 stop slip 0.5, S5 Bybit prices from 2021-11-15) - per
year %/month, 5y geometric mean, max year DD; (iv) the same for R2 (baseline) win rate only. Write results to robust.json and ROBUST.md with a
verdict against the user base gate (>= 5 %/month 5y mean, every-year DD < 20, win > 55 %).
