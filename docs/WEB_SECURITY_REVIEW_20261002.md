# Web security review — 2026-10-02

Scope: local FastAPI/SQLite backend, static Vercel frontend, authorization and the five scheduled paper pipelines.
No live orders, production penetration test, deployment, credential rotation, or research model changes.

## Product access

Requested product rank: `monthly_last_year` descending, `gate_dd` ascending, `win_hidden` descending, pipeline ID as final tie-break.
This explicitly uses dashboard evidence for product access and execution priority; training and research selection are unchanged.
G2/v301 and CS/v295 are restricted to admins by default. Viewers see all historical evaluation metrics and a mailto link,
but no plan, signals, positions, orders, trades, equity path, or prospective paper results. Viewers can use CB/v285, C4/v269 and C5/v266.
Pending accounts still require approval. The mailto link does not send mail or automatically grant permissions.

Admins can persist display/execution order and independent per-pipeline locks through `/api/admin/pipelines`.
Settings apply to all viewers and are reread per request, including sessions issued before the change.
Only approved historical summary fields are serialized to the evaluation table; current plans/events are excluded for locked rows.
Full-catalog and boolean validation reject malformed settings before any write; an atomic SQLite revision check returns 409
for stale admin tabs. Empty viewer access is supported with 403 on default signal endpoints and an evaluation/contact UI.
Manual ordering does not change lock identities; automatic ordering can be restored while preserving configured locks.

## Findings addressed

| Finding | Change and verification |
| --- | --- |
| Viewer could read all five pipelines, including direct run IDs and shared admin cache | Central backend access checks cover each data endpoint before cache; aggregate locked rows contain only historical evaluation fields. Regression tests warm admin cache then attempt viewer reads. |
| Long session bearer token; no refresh or revocation | Access JWT expires after 15 minutes; randomized rotating refresh session expires after 7 days. SQLite keeps refresh hashes only. Replay revokes the session; logout invalidates access and refresh. |
| Token persisted in JavaScript-readable localStorage | Access stays in memory and is sent through the Authorization header. Refresh is a host-only HttpOnly/Secure cookie, omitted from JSON. Older storage keys are removed. |
| Broad default CORS allowed other Vercel tenants | Default exact origins only, credentials enabled for cookie refresh. Origin checks on cookie refresh/logout and API POST block cross-site requests. Current local configuration has no regex override. |
| Cookie authentication could introduce CSRF | Signal APIs accept Bearer access headers only. Cookie refresh/logout require an explicitly trusted Origin; API clients can use a refresh Bearer header. Tests reject untrusted and missing Origin with cookie authentication. |
| Potential script injection/token theft | CSP limits scripts to the existing widget sources and disallows inline scripts; unsafe dynamic KPI values are escaped. No credential persists in Web Storage. CSP does not guarantee protection from a compromised allowed third-party script. |
| Unbounded POST JSON payloads | 64 KiB body limit before parsing, including chunked requests. Tests confirm 413 rejection. |
| Client could spoof Cloudflare IP headers for rate limiting | Cloudflare IP is trusted only from a loopback proxy peer with CF-Ray, and must be a valid IP. Direct remote spoofing cannot bypass the bucket. |
| Silent scheduler failures/partial completion | All five plans are attempted. Cycle failure is recorded, retried after 60 seconds, with unfinished plans first. Completion markers survive restart. Job mutex releases even on DB failures. |
| Public documentation endpoints exposed API schema | Public `/docs`, `/redoc` and `/openapi.json` disabled; admin route authorization remains enforced. |

Implementation follows the [OWASP REST guidance](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
and [session guidance](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).

## Dependency audit

OSV queries for 18 installed backend/runtime packages found advisories affecting `requests==2.32.5` and `urllib3==2.7.0`.
Upgraded to `requests==2.33.0` and `urllib3==2.8.0`, updated root/backend requirements and package metadata.
Rechecking the same 18 packages returned no recorded advisories; `pip check` passed.
The dependency query was repeated before commit with the same clean result. The 23 code/docs files selected for commit
were checked for credential patterns and exact secret values from the local `.env`; no matches were found.

Maintainer advisories: [Requests temporary-file reuse](https://github.com/psf/requests/security/advisories/GHSA-gc5v-m9x4-r6x2),
[urllib3 proxy TLS](https://github.com/urllib3/urllib3/security/advisories/GHSA-8988-9cw3-xx77),
[deflate loop](https://github.com/urllib3/urllib3/security/advisories/GHSA-gh4c-6fx4-qh6g),
[unbounded chunk header](https://github.com/urllib3/urllib3/security/advisories/GHSA-vxq7-64xx-v4gw).
Local, ignored reports are in `artifacts/web/dependency_audit.json` and `dependency_advisories.json`.

## Validation and rollout limits

58 web/auth/scheduler/FE pytest cases passed, including an adapter running eight JavaScript behavior cases.
Browser QA used an isolated temporary DB: admin moved G2 below CS, opened its viewer access, saved settings,
and verified persistence across restart. A fresh viewer session showed four selectable pipelines and all historical metrics
for the remaining locked CS row, including the mailto contact link. The original default is still two locked / three selectable.
Admin settings use no-store responses; logout clears their draft and table from frontend memory/DOM.
Market/TradingView loaded without CSP errors.
The preview is not production paper evidence. The full repository suite was run without exclusions before commit:
`.venv/Scripts/python.exe -m pytest -o addopts='' -q --tb=short` — **1577 passed, 2 skipped**, no failures (452.67 seconds).
The v90 smoke test writes to pytest's per-test temporary directory, without deleting the fixed research output directory
or existing checkpoints. All existing smoke assertions are unchanged. The two skips are intentional r76/r77 absence gates:
W1/W2 inputs are present, so the verify-time comparison tests own those checks.

Roll out BE and FE together, retain a strong `AUTH_SESSION_SECRET`, configure exact owned CORS origins and `WEB_ADMIN_CONTACT_EMAIL`.
Existing session tokens require sign-in again. The deployed site itself and the Google login flow were not tested against production.
Browsers blocking third-party cookies may block refresh on a Vercel domain; use the existing custom FE domain on the same site as the API.
Local no-auth remains an explicit localhost option and rejects cross-site browser requests, forwarded headers and public Host values.
This audit does not establish that the whole system has no security vulnerabilities.

## Scheduler recovery follow-up

Startup now always checks and repairs actual inputs before running the five plans. The 4h cycle and 15-minute refresh use
the same ordered prerequisites: candles, archive/live flow, as-of member gap repair, member validation, then all five plans.
Unfinished plans retain product/admin priority. A failed prerequisite blocks new plans and the scheduler retries after 60 seconds;
a failed plan still allows the other four attempts. Stale plan artifacts and failed paper-history writes cannot complete a plan.
Sleeping across multiple closes wakes into recovery immediately. `/health` exposes status and the failed step only, without signal
payloads or private exception text in the new `input_check` field.

Backfill includes every required decision from the frozen paper starts, without a 14-day cap, including a fresh/partially written
log and the newest closed decision. Failed member rows remain retryable. As-of environment settings are restored after each attempt;
delayed rows remain labelled backfill. The shadow writer checks lock-owner liveness: a crashed process can recover immediately,
an active process retains its lock even after an hour, and a busy lock returns failure rather than false success.
Windows process status uses WinAPI, avoiding the process-termination semantics of `os.kill(pid, 0)` on Windows.

Candle checks cover internal gaps and tails. Coinbase/spot recovery repairs interior holes and paginates long outages.
Flow and Coinbase/spot checks cover the frozen paper input/warmup range from March 2026 onward, preserving older research gaps.
Missing archive rows invalidate manifest completeness; replaying a source replaces its aggregates rather than doubling them.
REST backlog saves a cursor and fails until closed-data coverage is reached, even if the API returns a short page with gaps.
A legacy partial JSON cursor is rebuilt from the archive end; new cursor writes use an atomic file replacement.
Replay and agent inputs reject missing closed 4h/1m bars.

Read-only local inspection found no missing closed candles in the web DB, three missing O1 decisions, and no pipeline completion
markers yet. Flow archives also contain older research gaps; these are not fabricated or used to block the current frozen window.
The inspection did not execute production recovery or inference. Local ignored details: `artifacts/web/scheduler_state_audit.json`.

Added recovery tests cover startup despite current markers, sleep/resume, prerequisite failure, individual plan failure, old/fresh
shadow gaps, partial log writes, lock recovery, live cursor continuation, source replacement, and Coinbase/spot pagination.
No dependency or authentication configuration was changed by this follow-up. Actual runtime recovery requires restarting BE
with the new code and `WEB_SCHEDULER_ENABLED=true`; upstream outages remain failures until those public sources are available.

Final follow-up validation: **36 recovery tests passed**. The full suite, without exclusions, then passed:
`.venv/Scripts/python.exe -m pytest -o addopts='' -q --tb=short` — **1613 passed, 2 intentional skips**,
no failures (448.12 seconds). The 126 warnings are existing FastAPI/Starlette deprecations.
`pip check` and the staged whitespace check passed. The exact 13-file follow-up scope was scanned against credential patterns
and local `.env` secret values, with no matches. Models, downloaded data, audit outputs and unrelated research changes are excluded.
