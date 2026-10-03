# v351-v352 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Two versions in research/parallel/rounds/parallel-20260906-r2/ (docstrings = pre-registration): v351 adds four market-wide quarterly-basis features
(btc_qb_front, btc_qb_slope, btc_qb_chg24, eth_qb_front from artifacts/research/engine_real/qbasis_features_4h.parquet) to the v240 O1 A member
(annual v144 + quarterly v202 builders, features excluded from the vol models, as v244) -> member_A_qb / member_Aq_qb; v352 scores those books
with book_mult 0.60 and with half-demeaned members. Both are scored on the M3 structure with the kpack inputs (KPACK=artifacts/kaggle/kpack/pack347;
wiring = the audited v347 run_genome, CB seed reference dev4 6.233).
Part A (blind, before opening result JSONs / run logs): (1) check the basis feature timing: a value at the 4h bar keyed by open_time t must use only
hourly bars closed by t + 4h (read scripts/fetch_quarterly_basis.py and its tests; spot-check 20 random rows against the raw contract files);
(2) rebuild ONE anchor of member_A_qb (annual) yourself and compare with the cached member; (3) replicate every row, fold choice, transfer flag and
final of v351 and v352; (4) check that no most-recent-year number enters any choice. Save replication.json FIRST.
Part B: compare (monthly > 0.01 pp, DD > 0.05 pp, F > 0.001, win > 0.001, member weights > 1e-9 = mismatch, report all); COMPARISON.md with
"## Verdict" PASS/FAIL per version. Write only under `research/parallel/rounds/parallel-20260906-r2/v351_v352_audit/` and
`tests/test_v351_v352_audit.py`; relative paths without quoting. Do not edit leader files.
