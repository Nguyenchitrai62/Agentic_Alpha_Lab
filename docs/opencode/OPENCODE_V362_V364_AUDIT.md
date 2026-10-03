# v362-v364 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Three versions in research/parallel/rounds/parallel-20260906-r2/ (docstrings = pre-registration), kpack inputs (KPACK=artifacts/kaggle/kpack/pack347):
v362 = M3 with engine m_sl / m_tp 3/6 and 5/10 (MANUAL fitness; the dev4 choice S5T10 became the paper pipeline M4; check that backend/history_tm.py
pipeline "v362" replays dev4 6.392 with the same settings and that scripts/forward_trade.py --candidate v362_M4 uses m_sl 5 / m_tp 10 and the
pending-order SL / TP use those multiples); v363 = BOT R2 (v306 seed) with m_sl / m_tp 5/10 and 6/12 (v306 BOT fitness, folds k = 1, 2, 3);
v364 = M4 neighbours SL5/TP8 and SL4/TP10.
Part A (blind, before opening result JSONs / run logs): replicate every row (dev4, per-year, F), fold choices, transfer flags and finals with your own
wiring; check that no most-recent-year number enters any choice. Save replication.json FIRST. Part B: compare (monthly > 0.01 pp, DD > 0.05 pp,
F > 0.001, win > 0.001 = mismatch, report all); COMPARISON.md with "## Verdict" PASS/FAIL per version.
Write only under `research/parallel/rounds/parallel-20260906-r2/v362_v364_audit/` and `tests/test_v362_v364_audit.py`; relative paths without quoting.
Do not edit leader files.
