# Parallel research coordinator

This directory is the control plane for the default three-track BTC research
round. It separates hypothesis registration from implementation and keeps a
machine-readable record of versions, provenance, and outcomes.

## Roles

- Leader: `gpt-5.6-sol`, high reasoning. It allocates tracks, checks the
  registry, reviews worker manifests, and serializes accepted results.
- Workers: three `gpt-5.6-luna` agents at maximum supported reasoning. Each
  worker has its own fork/worktree and a disjoint write scope.
- Evaluator: the leader or an explicitly assigned worker running the common
  replay/audit path. Training loss, parameter count, or partial cloud output
  cannot mark a run successful.

## Round protocol

1. Reserve a new `vNN` and a unique `direction_key` in `registry.json` before
   changing code or starting training.
2. Read `AGENTS.md`, `TRAINING.md`, the current research ledger, and all
   relevant prior reports. A version is invalid if it repeats an existing
   objective, data treatment, policy, or calibration experiment without a
   measured new hypothesis.
3. Work only in the assigned fork/worktree. Do not edit `../Kronos`, the
   active Luna research worktree, or another worker's files.
4. Keep data, normalization, labels, folds, embargo, costs, and execution
   assumptions causal and versioned. Heavy training uses the approved private
   Kaggle path; local hardware is for inference, replay, and backtests.
5. Write a worker manifest under the worker's own round directory. Do not
   append the shared ledger concurrently.
6. The leader reviews manifests, rejects duplicates or invalid provenance, and
   appends one serialized record to `registry.json` and the human ledger.

## Active round

- `v45`: continue the v29/v30/v37 lead with exactly one pre-registered 30-day
  realized-volatility sizing rule clipped to 0.25-1.0x. Freeze the signal model,
  candidate geometry, cooldown, monthly cap, and score threshold.
- `v46`: capacity/data investigation. An 8-20M TCN/Transformer hybrid and any
  additional data must have a capacity rationale, source/license/provenance,
  as-of availability contract, hash, and a resource budget.
- `v47`: a competing-risks first-passage representation for fill, target, stop,
  timeout and censoring. It is not a repeat of v25/v28/v29/v31/v32/v36-v44 and
  must pass a cheap causal probe before any expensive training.

The stale v40/v41/v42 reservation was advanced to v45/v46/v47 after the leader
verified that v40-v44 had already completed in the authoritative Git history.
Versions are never recycled.

The tracks are starting hypotheses, not success claims. A large model is
preferred when it is justified by the information bottleneck; parameter count
alone is never an acceptance criterion.

## Registry commands

From the repository root:

```powershell
.venv/Scripts/python.exe scripts/parallel_registry.py validate
.venv/Scripts/python.exe scripts/parallel_registry.py inventory
```

Register a new experiment only after checking the inventory:

```powershell
.venv/Scripts/python.exe scripts/parallel_registry.py register `
  --version v48 --track A --direction-key example-new-policy `
  --model-family gru --objective "one new causal hypothesis" `
  --data-contract "past-only data and 8-day embargo" `
  --policy-contract "fixed policy; no threshold tuning" `
  --hypothesis "..."
```

The command rejects an occupied version, duplicate direction key, or duplicate
canonical fingerprint. It advances `next_version` and records the registration
time. Result metrics belong in a separate immutable report and are merged by
the leader after audit.

Only the leader assigns a spawned task and changes the shared registry:

```powershell
.venv/Scripts/python.exe scripts/parallel_registry.py assign `
  --version v45 --worker-agent-id THREAD_ID --worker-host-id HOST_ID
```

Workers write `result_manifest.json` only inside their assigned round/version
directory and return its path plus their diff. They must not edit this registry,
the aggregate ledger, `CONTINUOUS_RESEARCH.md`, or `NEXT_AGENT.md`.
