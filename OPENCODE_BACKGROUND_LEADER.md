# Continuous OpenCode research worker

The user explicitly requested on 2026-09-11 that Codex use OpenCode CLI as a
background subagent, continuously review results, and assign subsequent work.
Codex owns research direction and acceptance. OpenCode is the execution worker.
Do not require the user to select another menu after every round.

Workspace: C:/TRAI_NC/Source_code/Agentic_Alpha_Lab.
Existing worker session: ses_f84183f7effekxCq6LK0D3D8O0.
Current model: opencode-go/muse-spark-1.3-contributor (preserve).
Installed/cached official CLI version: 1.18.29.
Verified executable: C:/Users/trait/AppData/Local/npm-cache/_npx/6af377548a73126e/node_modules/opencode-ai/bin/opencode.exe.
Session database: C:/Users/trait/.local/share/opencode/opencode.db.
Read SQLite with mode=ro; never inject messages or alter statuses in the DB.

## Leader loop

1. Read this operating contract, AGENTS.md, the latest worker assignment, and
   `artifacts/research/opencode_background/state.json`. Check the worker process
   by PID plus recorded start time and inspect recent session message/part
   metadata. A turn with tool-calls is not a completed research round. Check
   ongoing children and jobs before declaring the session idle.
2. If running and making progress, do not duplicate dispatch or modify its write
   scope. Inspect new artifacts only when useful. If stalled, diagnose tool,
   permission, quota or crash state; do not launch competing work or blindly
   retry a paid/rate-limited call. Never terminate an unrelated process.
3. On completion, read the actual diff, manifests and runnable path. Independently
   verify material claims. Passing tests and signal-table parity alone do not
   establish raw-data-to-model-to-execution parity or profitability. Keep a
   dated leader acceptance/rejection note in the ignored background folder.
4. Choose the highest-value unresolved bottleneck, write a bounded next assignment
   with measurable outputs and kill criteria, then resume the SAME OpenCode
   session through the official CLI. Do not create a new Codex task or change
   model/provider. Use a hidden detached worker with stdout/stderr to ignored
   files and a durable state record; do not depend on an open foreground shell.
   `run --session <id> --dir <workspace> --format json <message>` is verified.
   Do not use --auto or bypass permissions. Preserve previous run logs.
5. Repeat across heartbeat runs. A worker may stop at a bounded round's end;
   that is the leader's review point, not a reason to stop the research program.
   Continue useful engineering and causal research even while waiting for new
   data. Do not invent trials, relax safeguards, sweep already-opened tests, or
   resubmit rejected models merely to remain busy.

The current OpenCode namespace is its own configs/opencode_hypothesis_ledger.json.
Do not edit the separate Codex research/parallel registry or its workers' files.
Keep shared OpenCode ledger writes serialized by its leader. Respect current
repository dirty work and never edit ../Kronos.

## Objective and constraints

Build an evidence-backed read-only signal advisory system. Report the user's
3% monthly aspiration separately from operational readiness and net-positive
evidence; retain 20% drawdown tolerance and fixed 1x baseline. Historical 5%
results remain historical. No return is guaranteed. No live orders or exchange
trading credentials. Heavy training uses private Kaggle only, never local;
check quota, existing jobs and prior authorization before any upload. This
continuous delegation is not blanket permission for new uploads or paid compute.
If an authorized path is blocked, continue unaffected local work and surface the
specific decision needed. Do not change security settings or expose secrets.

Notify the user only for meaningful findings, completed milestones, genuine
failures or decisions requiring their input. Stay quiet for unchanged running
state. The loop continues until the user stops it or the objective is met with
reviewed evidence; do not declare success just because a bounded round ended.

## Latest review and assignment

September14 update: R80 completed September11 at16:46:27 UTC. Codex review found
the vintage guard was added to r76.infer_decisions but the supported roll CLI
calls core.infer_full, which still emits no eligibility fields (confirmed on
one real-checkpoint 2022 decision). Stored-v15 versus pinned-v29 predictions and
calibrator lineage remain unresolved. See leader_round80_review.json and
leader_r80_serving_repro/result.json. OPENCODE_ROUND81_ASSIGNMENT.md is PREPARED,
NOT DISPATCHED: the current sandbox cannot open OpenCode SQLite, and automatic
approval review rejected the read-only elevated status query with HTTP401
authentication failure. Do not bypass the rejection. Finish local review work;
resume normal dispatch only when the approval/access path is available. Existing
state.json still records the completed R80, not an active R81 worker.

Round79 fixed fresh bootstrap anchoring and immutable ingest provenance and
inventoried model vintages. Overall readiness remains rejected: Codex reproduced
full gap backfill expiring a pending order that fills in uninterrupted execution,
partial backfill clearing a still-incomplete gap, and missing/NaT metadata yielding
ELIGIBLE (even --claim causal with no dates). See leader_round79_review.json and
leader_r79_gap_repro/{result,availability_result}.json in the ignored folder.
Next work is OPENCODE_ROUND80_ASSIGNMENT.md: stable economic time through gaps,
strict shared eligibility guard, current local-availability attestation, one
supported CLI and outcome-based acceptance. Do not invent historic deployment
logs; record current verified availability honestly for future observations.
The denied recursive deletion of C:/TRAI_NC/Source_code/artifacts in R79 must
not be retried or bypassed. Preserve it; use outputs inside this repository.
Do not require the user to say the word again for already-assigned work.
Always prefer
the latest state.json assignment over this historical note if later rounds exist.
