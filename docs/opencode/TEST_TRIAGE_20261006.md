# Test triage 2026-10-06 (ops_testtriage)

Helper: `scripts/test_triage.py` (stdlib only). Method per file: `git status --short tests/` discovery,
static dep scan (`research/tournament|x`, `research/diagnostics`, `research/parallel`,
`data|artifacts|models|reports`) with `git ls-files` (tracked?) + `git check-ignore`
(gitignored?) + existence, then alone: `.venv/Scripts/python.exe -m pytest -q -x -v <file>`
(300 s timeout, sequential, BELOW_NORMAL priority; `-v` added because pyproject
`addopts="-q"` makes bare `-q -x` suppress the summary line — verdict identical).
RAM gate: skip when free < 2 GB, retry in a 2nd pass. Raw logs/JSON in temp dir
(`triage2.log/json`, `scan_final.log/json`), not in git.

## Verified pytest runs (actually executed; all COMMIT)

| file | result | tests | runtime | deps | class |
|---|---|---|---|---|---|
| tests/test_bot_parity.py | pass | 5 passed | 32.9 s | (static: none matched) | COMMIT |
| tests/test_tournament_oc_kpi.py | pass | 9 passed | ~26 s | parallel-20260906-r2 tracked; oc_kpi untracked-exists | COMMIT |
| tests/test_oc_tsmom.py | pass | 5 passed | ~21 s | parallel-20260906-r2 + tournament/ext tracked | COMMIT |

Note: `test_tournament_oc_kpi` passes despite its `oc_kpi` folder being untracked —
static heuristics alone would misfile it, which is why the run matters.

## Full sweep: DEFERRED (box under load, gate held)

Pass 1 + retry pass (after 900 s) over the 172-file snapshot: **172/172
`deferred-low-ram`**, 0 executed. Free RAM sampled 0.89–1.6 GB (load 89–94%),
never >= 2 GB. Per AGENTS.md the gate was not overridden. Evidence:
temp `triage2.json` (172 rows, all `status=deferred-low-ram`).

## Static dep scan (final snapshot: 177 untracked tests; count drifts as workers add files)

- **COMMIT? (preliminary, needs a run): 144.** Deps are tracked code, or
  gitignored-but-present local data (AGENTS.md: `data/raw`, `artifacts`,
  `research/diagnostics`, `*_result.json` stay local): e.g. engine_real
  artifacts, `data/raw/*` parquets, `research/parallel/rounds/...` (tracked),
  `research/tournament/ext` (tracked), `research/tournament/oc_*` with tracked files.
- **DROP-CANDIDATE? (33):** every `research/tournament/<x>` dep has 0 tracked
  files (closed-screen folders, untracked-exists):
  adaptsig, b1deeper, b1soft, bookbrake, bookdipnet, bookevent, bookvol, bullbook,
  bullshort, carrytopup, contrib, cooldown, deepcheck, deeptp, dombook, earlystart,
  eventblk, filltime, holdext, idea5, idea9, idiocap, ladderfill, mcdd, outage,
  premfill, recent, rolling17, skewbook, usdtshort, velocity, venuegap
  (all `test_oc_*`), plus `test_tournament_oc_kpi` (see run note above — COMMIT).
- **COMMIT-WITH-SKIP: 0 by static scan** (no missing-dep refs; expect some to
  emerge once runs execute against absent local outputs). **STALE: 0.**
- `tests/mock_bybit_v5.py` is a helper, not a test (excluded from runs).
- During this triage the wd mutated under concurrent workers (144→179 untracked;
  one scan crashed on a file deleted mid-run — helper now records `vanished`).

## Exact `git add` list for COMMIT rows (verified passes only)

```sh
git add tests/test_bot_parity.py tests/test_tournament_oc_kpi.py tests/test_oc_tsmom.py
```

Nothing else is COMMIT today: the 144 COMMIT? files need one passing run each;
the 33 DROP-CANDIDATE? files need a fail/error-against-untracked-folder
confirmation (or a pass, which promotes to COMMIT, cf. oc_kpi).

## Rerun (when free RAM >= 2 GB)

```sh
.venv/Scripts/python.exe scripts/test_triage.py --json C:/Users/trait/AppData/Local/Temp/opencode/triage.json
.venv/Scripts/python.exe scripts/test_triage.py --scan-only --json C:/Users/trait/AppData/Local/Temp/opencode/scan.json
.venv/Scripts/python.exe -m pytest   # required before handoff (AGENTS.md)
```

No tests/research code touched, no commits, no deletions by this task. Line count: this file.
