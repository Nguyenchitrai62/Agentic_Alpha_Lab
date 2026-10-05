# v407 + v409 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Both versions run the correlation-aware dip-heavy BOT on the 5-year 4-phase harness (as v406 / v408; see their docstrings = pre-registration):
B1 dip size x 1/(1+n) (n = other majors with C[i,f-1,b] <= O[i,0,b](1 - 2.5 sig4[i][b])) times kd on every rung, sleeve_risk_budget 0.26 x kd,
trade book_mult bm. v407 rows: R2B1D16 (= v406 cache), R2B1D20 (kd 2.0), R2B1D20B11 (kd 2.0, bm 1.1). v409 rows: R2B1D16 (cache),
R2B1D15B08 (kd 1.5, bm 0.8), R2B1D16B06 (kd 1.6, bm 0.6), R2B1D13 (kd 1.3). Per-year reset metric research/diagnostics/r2_decompose5/
reset_metric.py; full-path conservative DD of the continuous 1/4 mix (v388.mix).
Part A (blind, before opening v407 / v409 result JSONs, run logs or pkls): reproduce R2B1D20 on phase 1 and R2B1D13 on phase 3 with your own
wiring (phase_offset_full prep_idx on the full standard index + shift, pipe_setup("v321"), v376/tables_hidden r2 table, win_start 5); save
replication.json. Part B: compare (final equity relative > 1e-6 = mismatch); recompute rows, folds, finals and full-path DDs from the pkls.
COMPARISON.md with "## Verdict" per version. At most 2 heavy processes. Write only under
`research/parallel/rounds/parallel-20260906-r2/v407_v409_audit/` and `tests/test_v407_v409_audit.py`; relative paths; no edits of leader files.
