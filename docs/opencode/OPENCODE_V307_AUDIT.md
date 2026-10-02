# v307 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v307 = walk-forward genetic algorithm over MANUAL (book-only) genes, script research/parallel/rounds/parallel-20260906-r2/v307/v307_manual_book_evolution.py
(read its docstring = pre-registration). It is too expensive to re-run the GA; audit the EVALUATION and the PROTOCOL instead.
Write only under `research/parallel/rounds/parallel-20260906-r2/v307_audit/` and `tests/test_v307_audit.py`; relative paths without quoting.
Part A (blind; do NOT open v307/v307_result.json, v307/evolution.log or v307/run.log before replication.json is saved): from the eval cache
v307/eval_cache.jsonl take (1) the 11 SEEDS of the script (encode them yourself from the docstring / SEEDS dict) and (2) 10 random cached genomes
(seed 7307); re-simulate each with YOUR OWN implementation of the genome -> engine_user call (members = annual + quarterly averages of the 8 member
files named in init_worker, weighted and normalised; trade = v216.GRID with the cool-down grid policy and the genome's theta / k_off / tighten /
be_k / partial; engine kwargs v221.KW with m_sl / m_tp / target / cap, sleeve False, win_start 5) and your own per-year book-trade extraction
(v213 net definition, entry-time year); compare with the cache rows (net / DD / n_book / w_book per dev year). Then verify in the code: the fitness
only reads years [:k] in folds and [0..3] in the final; the most recent year (index 4) is produced only by run_genome(full=True) for the final M;
the cached rows of non-final genomes contain 4 years only; fold winners are scored on year k only; the seeds' baseline uses the same fitness.
Save replication.json FIRST. Part B: open v307_result.json; recompute the fold test F values and the final M metrics (dev4 and most recent year)
from your re-simulation of the listed winner genomes; mismatch = monthly > 0.01 pp, DD > 0.05 pp, F > 0.001. COMPARISON.md with feature timing,
label windows, fit windows (no fitting here; members are walk-forward caches), fill timing and "## Verdict" PASS/FAIL. Do not edit leader files.
