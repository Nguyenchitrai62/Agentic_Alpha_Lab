# Pre-push audit 2026-10-06 (local main vs origin/main)

Range: `git log origin/main..main` = 253 commits; `git diff origin/main..main --stat` = 752 files changed, 60772 insertions, 37 deletions; raw diff ~4,088,181 bytes (~3.9 MiB). Uncommitted working-tree edits/untracked files exist but are NOT part of the push range and were excluded.

## (1) Secret scan on added lines
Method: `git diff origin/main..main -U0` piped through case-insensitive regex (AKIA…, GOCSPX-, BEGIN PRIVATE KEY, api_key/api_secret/session_secret/auth_token assignments with quoted values, password assignments, bybit key pairs, Kaggle tokens, google client secrets) + email harvest + long-base64 (>=60 chars) entropy pass.
Findings (pattern type only, no values):
- `bot/*`, `tests/test_bot_*.py`, `tests/test_*.py`: only ENV VAR NAMES (e.g. BYBIT_*_API_KEY/SECRET, AUTH_SESSION_SECRET) read via env(), and test-fixture placeholder values under `monkeypatch.setenv` — no real credentials.
- `docs/**`, `research/**`, task files: secret-related words appear only as variable names, scan-report prose ("0 key=value hits"), or redacted placeholders (`BYBIT_TESTNET_API_KEY=...`, `<owner>` placeholder). No `.env` content, no `kaggle.json` content, no Google client secret, no private key block.
- Emails in added lines: only `*@example.com` test fixtures and `+@pytest.fixture` / `+@app.get` / `+@torch.no` false positives from the `@` regex — no real personal emails beyond the already-public commit author.
- Entropy pass: only 2 hits, both 64-char hex SHA-256 digests in `research/.../v428/prereg_sha256.txt`-style prereg lines (checksums, not secrets).
Result: NO real secrets found.

## (2) Files that should not be tracked (AGENTS.md: data, parquet/pkl/zip, model files, large json > 1 MB, .env*, artifacts/)
- `git diff origin/main..main --name-only` filtered for `.env|artifacts/|data/|parquet|pkl|zip|.pt$|.pth$|models/`: ZERO hits — nothing in those classes is being added.
- JSON sizes at HEAD: `research/parallel/registry.json` 889,887 B (< 1 MB, modified tracker, acceptable); `research/tournament/oc_phasedisp/results.json` 2,135 B; `research/.../v427+v428/cloud_submission.json` < 1 KB each. No added JSON > 1 MB.
- All 752 changed paths are code (`bot/`, `backend/`, `scripts/`, `tests/`), docs (`docs/**`, `research/**/REPORT.md|PLAN.md`, `CONTINUOUS_RESEARCH.md`, `NEXT_AGENT.md`), `frontend/`, `.gitignore` — commit code/docs only, compliant.

## (3) Total size added
- 752 files, +60,772 / -37 lines; raw unified diff 4,088,181 bytes (~3.9 MiB). Largest single modified tracker `research/parallel/registry.json` stays < 1 MB. No binaries, no data blobs.

## (4) Frontend changes (Vercel auto-deploy)
- Changed: `frontend/app.js` (+39/-1), `frontend/index.html` (+6). Only new network call in the diff: `api("/api/carry")` inside new `renderCarry()`, routed through the existing authenticated `api()` helper (frontend/app.js:80-88: Bearer header + credentials handling).
- Backend (same push) adds the matching route: `GET /api/carry` in `backend/server.py` guarded by `auth.require_viewer` (60 s cache) served by new read-only `backend/carry_view.py` (reads `artifacts/bot/paper_carry/state.json`, never writes/network/orders). Read-only carry panel; no new public/unauthenticated route; no other fetch/endpoint changes.

## (5) Local absolute paths / private tunnel hostname in frontend code
- `git diff origin/main..main -- frontend/` filtered for `trycloudflare|cfargotunnel|tunnel|127.0.0.1|localhost|C:\\|C:/`: NO hits. (The only "tunnel" word in frontend/app.js:1 is the pre-existing generic comment "FastAPI backend (Cloudflare tunnel)" — no hostname.)
- `127.0.0.1:8724`, `C:/Users/...Temp/opencode/...`, backend-local notes appear ONLY in `docs/`, `scripts/`, `tests/` (ops runbooks/health checks) — not in `frontend/` and not deployed to Vercel.

Verdict: SAFE TO PUSH — no secrets, no data/artifact/model/.env files, no oversized JSON, frontend delta is a read-only panel on one new authenticated route, no local paths or tunnel hostname in frontend code.
