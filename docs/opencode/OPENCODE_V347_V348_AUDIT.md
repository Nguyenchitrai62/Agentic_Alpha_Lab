# v347-v348 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Two searches in research/parallel/rounds/parallel-20260906-r2/ (docstrings = pre-registration), both on the deployed MANUAL structure M3 with the
kpack inputs (set KPACK=artifacts/kaggle/kpack/pack347; one simulation ~4 s): v347 = walk-forward GA over nine book-member weights (parts "folds"
and "final"), v348 = exhaustive 1296-rule grid of the dip-agent decision rules with flat-neighbourhood choice.
Do NOT rerun the full GA. Part A (blind, before opening any result JSON, run log or eval cache):
 1. reproduce the M3 reference (CB weights A2 B2 D1; v348 rules U / 2.0 / 1.5 / 0.0 / 0.5 / 0.001) dev4 6.233 with your own wiring of the
    engine calls (CB books x0.75 book_mult, pullback 0.75 sigma / 3 bars, bracket dip limits 3.0 / 4.0 sigma, size_mult 4.375, touch stop 8 sigma,
    budget 0.26, sleeve_start 16, v306 tables);
 2. recompute 15 random v347 genomes and 15 random v348 rule sets (seed 0) and the reported fold winners / finals, store per-year metrics;
 3. check the fitness formula, the flat-choice rules, that every choice uses only years [:k] (dev4 for the final) and that the most recent year is
    computed only for the final.
Save replication.json FIRST. Part B: compare with v347_result_*.json / v348_result.json and the eval caches (monthly > 0.01 pp, DD > 0.05 pp,
F > 0.001, win > 0.001 = mismatch, report all); COMPARISON.md with "## Verdict" PASS/FAIL per version.
Write only under `research/parallel/rounds/parallel-20260906-r2/v347_v348_audit/` and `tests/test_v347_v348_audit.py`; relative paths without quoting.
Do not edit leader files.
