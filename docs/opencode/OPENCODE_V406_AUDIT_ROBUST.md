# v406 blind audit + robustness of R2B1D16 / R2B1D18B08 (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v406 (research/parallel/rounds/parallel-20260906-r2/v406; docstring = pre-registration; process_note.txt discloses a crash-and-rerun before
any result). Rows: R2B1_130 (= v400 cache), R2B1D16 (no risk_mult; B1 correlation-aware dip size x 1/(1+n) (n = other majors with
C[i,f-1,b] <= O[i,0,b](1 - 2.5 sig4[i][b])) times kd 1.6 on every rung; sleeve_risk_budget 0.26 x 1.6; book unchanged), R2B1D18B08 (kd 1.8,
budget 0.26 x 1.8, trade book_mult 0.8). Harness: 4 phases 2021-09-24..2026-09-23, per-year reset metric research/diagnostics/r2_decompose5/
reset_metric.py, full-path conservative DD of the continuous 1/4 mix (v388.mix). Write only under
`research/parallel/rounds/parallel-20260906-r2/v406_audit/` and `tests/test_v406_audit.py`; at most 2 heavy processes; relative paths; do not
edit leader files.
PART 1 (blind, before opening v406_result.json / run.log / v406_runs.pkl): reproduce R2B1D16 on phase 2 and R2B1D18B08 on phase 0 with your
own wiring (phase_offset_full prep_idx on the full standard index + shift, pipe_setup("v321"), v376/tables_hidden r2 table, win_start 5);
save replication.json. PART 2: compare (final equity relative > 1e-6 = mismatch), recompute rows / folds / final / full-path DD -> COMPARISON.md
"## Verdict". PART 3 robustness for R2B1D16 and R2B1D18B08 exactly as v399_v400_audit/ROBUST.md did for R2B1_130 (read its script
robust_r2b1_130.py and reuse it): all-trade and book win rates per year and pooled; full-path DD; frictions S1 cost stress, S2 latency 15,
S3 latency 30, S4 stop slip 0.5, S5 Bybit prices (from 2021-11-15) with per-year %/month, 5y mean, max year DD, full-path DD. ROBUST.md with
the verdict vs the base gate (5y mean >= 5, every-year DD < 20, full-path DD <= 20, win > 55 %).
