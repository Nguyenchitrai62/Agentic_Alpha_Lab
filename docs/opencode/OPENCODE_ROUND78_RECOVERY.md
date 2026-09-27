# Resume interrupted R78, preserve completed worker evidence

Read OPENCODE_ROUND78_ASSIGNMENT.md and continue its integration/handoff in the
SAME session. This is a recovery, not a new research round or permission change.
Codex verified at 2026-09-11 13:06 UTC that wrapper PID24504, native CLI and all
Python jobs are gone, while the receipt and W2 pytest tool still say running.
Do not wait indefinitely on those orphaned statuses or edit the session DB.
The exact cause of process disappearance is unknown; stderr logs are empty.

W1 and W3 returned completed results. W2 produced summary.json and
divergence_diag.json in artifacts/research/opencode_r78_rolling/w2, then its
last pytest invocation was interrupted. Inspect these artifacts and its recent
session history; resume finalization instead of repeating the long inference
prefix or launching duplicate workers. All prior logs and artifacts must remain.

Codex has read W2's MISMATCH-DIAGNOSE report; it is NOT accepted as a successful
historical reproduction. R76 uses fold-10 checkpoints at every historical date,
while the published reference uses per-fold weights. Preserve the first numeric
divergence. Explicitly audit fit/end/available timestamps of models, scalers and
calibrators against inference dates. A future-trained checkpoint replaying old
data can be a labeled integration fixture only, never causal performance or
walk-forward validation. Do not silently swap checkpoints or fit anything to
match known profitable signals. Propose the precise next bounded vintage audit
after closing current engineering work.

Finish R78 leader integration: inspect W1/W3 actual runnable paths, run the final
full pytest suite (record counts and skip reasons), finish finite fresh smoke
and shifted-window resumes if missing, update the requirement matrix honestly,
and supersede R77's overclaim without deleting it. Record current final hashes,
limitations and exact commands. Retain tests for the rolling CLI bug and output
recovery. Do not declare global PASS with missing requirements.

No cloud, heavy training, live orders, model/provider/permission changes, edits
to ../Kronos or Codex registry/workers. Give Codex a concise Vietnamese handoff
when the bounded work is complete; Codex will review and assign the next round.
