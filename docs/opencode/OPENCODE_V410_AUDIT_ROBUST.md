# v410 blind audit + robustness of R2B1D16BF and R2B1D18BF (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v410 (research/parallel/rounds/parallel-20260906-r2/v410; docstring = pre-registration).
Rows: R2B1D16 (= v406 cache), R2B1D16BF / R2B1D18BF (no risk_mult; B1 correlation-aware dip size x 1/(1+n) (n = other majors with
C[i,f-1,b] <= O[i,0,b](1 - 2.5 sig4[i][b])) times kd 1.6 / 1.8 on every rung; sleeve_risk_budget 0.26 x kd; book LONG targets x0.5 on standard rows where the BTC 4h open < its 1200-bar mean (opens up to the row), applied before the shifted-clock forward fill).
Harness: 4 phases 2021-09-24..2026-09-23, per-year reset metric research/diagnostics/r2_decompose5/
reset_metric.py, full-path conservative DD of the continuous 1/4 mix (v388.mix). Write only under
`research/parallel/rounds/parallel-20260906-r2/v410_audit/` and `tests/test_v410_audit.py`; at most 2 heavy processes; relative paths; do not
edit leader files.
PART 1 (blind, before opening v410_result.json / run.log / v410_runs.pkl): reproduce R2B1D18BF on phases 1 and 2 (also check the bear mask is causal: truncation test on 10 rows) with your
own wiring (phase_offset_full prep_idx on the full standard index + shift, pipe_setup("v321"), v376/tables_hidden r2 table, win_start 5);
save replication.json. PART 2: compare (final equity relative > 1e-6 = mismatch), recompute rows / folds / final / full-path DD -> COMPARISON.md
"## Verdict". PART 3 robustness for R2B1D16 and R2B1D18B08 exactly as v399_v400_audit/ROBUST.md did for R2B1_130 (read its script
robust_r2b1_130.py and reuse it): all-trade and book win rates per year and pooled; full-path DD; frictions S1 cost stress, S2 latency 15,
S3 latency 30, S4 stop slip 0.5, S5 Bybit prices (from 2021-11-15) with per-year %/month, 5y mean, max year DD, full-path DD. ROBUST.md with
the verdict vs the base gate (5y mean >= 5, every-year DD < 20, full-path DD <= 20, win > 55 %).
