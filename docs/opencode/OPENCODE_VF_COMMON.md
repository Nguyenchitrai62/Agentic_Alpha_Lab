# vf helper rounds: common rules (read with your own assignment)

Leader: Claude Code owns all modelling and evaluation decisions. You build one
bounded, causal feature study. Read AGENTS.md and
`src/agentic_alpha_lab/patterns/common.py` (contract, assert_causal,
event_study). Do NOT edit common.py, other workers' files, configs, ledgers,
NEXT_AGENT.md, ../Kronos, or git state.

- Your module exposes `compute(bars) -> DataFrame` (float features, prefix
  given below, same index as bars, value at row t uses only information
  available at bars.close_time[t]) and `events(bars) -> DataFrame` (int8
  {-1,0,1} directional hypotheses). Must work for 1h, 4h, 1d BTCUSDT bars
  including the most recent year (the leader will join features over the full
  history), so inside compute you may load full external history, but align it
  strictly as-of each bar close (merge_asof backward on availability time).
- Studies: evaluate returns ONLY with `common.event_study` (it restricts to
  decisions before 2025-09-14). Never compute or look at forward returns for
  dates >= 2025-09-24.
- Tests in your own test file: `assert_causal` on real 4h and 1d bars
  (`load_bars(tf, include_opened_year=True)` is allowed ONLY for this causality
  test), plus hand-checked synthetic cases.
- Fix definitions before looking at results; log any post-hoc change.
- Outputs: CSV + SUMMARY.md (<= 15 lines) in your artifacts folder; state how
  many rows are stable_significant, effect sizes vs ~4-8 bps round-trip cost.
- Run your tests with `.venv/Scripts/python.exe -m pytest <file> -q`. Stop when done.
- HEAVY jobs (any 4-phase engine / harness run, any process expected > 0.4 GB): run them through the shared semaphore,
  `.venv/Scripts/python.exe scripts/heavy_slot.py run --tag <your tag> --min-free-gb 2.0 -- <cmd...>` (or
  `with heavy_slot("<tag>", max_slots=2, min_free_gb=2.0):` from scripts/heavy_slot.py); never `--leader`. Waiting for a slot is normal.
- GIT IS READ-ONLY FOR WORKERS (hard rule, 2026-10-06 incident): never run `git stash` (any form), `git reset`, `git checkout -- <path>`,
  `git restore`, `git clean`, `git rm`, `git commit`, `git switch`, `git rebase`, `git merge` or anything that changes the working tree, index,
  stash or HEAD. Other workers and the leader have uncommitted work in this tree; a stash/clean destroys it. To compare against the
  committed version use `git show HEAD:<path>` or `git diff`. To test "clean", copy files into your own scratch folder instead.
