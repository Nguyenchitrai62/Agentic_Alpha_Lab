# v365-v367 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Three variants of the MANUAL pipeline M4 (M3 + book SL 5 / TP 10) in research/parallel/rounds/parallel-20260906-r2/ (docstrings = pre-registration),
kpack inputs (KPACK=artifacts/kaggle/kpack/pack347; wiring = the audited v347 run_genome with the CB seed; M4 reference dev4 6.392):
v365 = trade-mode partial_k / partial_frac (3 sigma half, 2 sigma third); v366 = v310 _policy9 genes loss_act tighten / lock 3 via v310.encode;
v367 = loss_act tighten / hold judged with the ORIGINAL v310 fitness (book win rate) - a disclosed post-hoc choice; its dev4 final LT became the
paper pipeline M5: check that backend/history_tm.py pipeline "v367" replays dev4 6.015 and that scripts/forward_trade.py --candidate v367_M5 applies
the same rule (signal flat + position under water -> "tighten").
Part A (blind, before opening result JSONs / run logs): replicate every row (dev4, per-year, F, book and all-trade win), fold choices, transfer flags
and finals with your own wiring; check the fitness each version uses (v365 / v366 all-trade win; v367 book win) and that no most-recent-year number
enters any choice. Save replication.json FIRST. Part B: compare (monthly > 0.01 pp, DD > 0.05 pp, F > 0.001, win > 0.001 = mismatch, report all);
COMPARISON.md with "## Verdict" PASS/FAIL per version. Write only under `research/parallel/rounds/parallel-20260906-r2/v365_v367_audit/` and
`tests/test_v365_v367_audit.py`; relative paths without quoting. Do not edit leader files.
