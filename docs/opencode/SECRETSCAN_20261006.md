# Secret scan 2026-10-06 — audit_repo_secrets

Scope: LIGHT job, RAM < 1 GB, no engine runs. Read AGENTS.md, OPENCODE_VF_COMMON.md (GIT READ-ONLY: no stash/reset/checkout/restore/clean/commit; only `git ls-files`, `git show HEAD:<path>`, `git grep`, `git log -S` used). `.env` was never opened or printed (gitignored, untracked; `git log --all --oneline -- .env` = 0 hits).
Method: enumerated every tracked file via `git ls-files` (2803 files at scan time, HEAD `dba083e5`), read working-tree text (skipped `.env` basename; binary skipped for content, package-lock hashed separately), regex + entropy checks: private-key blocks, api-key/api-secret assignments, bybit/binance key refs, kaggle key/username refs, cloudflare/tunnel token refs, google oauth client id/secret, session-secret/secret-key assignments, password assignments, bearer tokens, discord/slack/telegram webhooks, email addresses, trycloudflare/cfargotunnel hostnames, generic secret/token assignments, known token prefixes (AKIA, gh*, sk-, xox*), high-entropy strings (>=32 chars, shannon>4.5) on lines mentioning secret/token/key/password. HEAD-vs-history: `git show HEAD:<path>` line comparison + `git log --all -S <pattern-type>` (keyword only, no values printed) + `git grep` checks for values. No secret values are printed in this file (file:line + pattern type only).

Verdict: ACTION NEEDED (owner action below). No API keys, tokens, private keys, passwords, webhooks, or Google credentials found as values in HEAD or as values in history — no key rotation needed. The only real exposure is a personal non-example mailbox committed in 4 places (in HEAD and in history); it violates AGENTS.md ("admin emails live only in the local `.env`; never commit them").

## Confirmed findings (real exposure, also in HEAD)

| file:line | pattern type | severity | HEAD / history |
|---|---|---|---|
| `.env.example:3` | email-address (personal non-example mailbox) | Medium | also in HEAD |
| `.env.example:4` | email-address (personal non-example mailbox) | Medium | also in HEAD |
| `backend/config.py:34` | email-address (same personal mailbox as hardcoded default fallback) | Medium | also in HEAD |
| `docs/WEB_DEPLOY.md:30` | email-address (same personal mailbox in docs example) | Medium | also in HEAD |

Owner action: replace all four with placeholders (e.g. `admin@example.com` / empty + comment "set in local `.env`"), keep real mailbox only in local gitignored `.env`. Note the mailbox is already in git history (`git log -S ADMIN_EMAILS` = 6 commits); decide whether to accept history exposure (spam/phishing risk, identity linkage) or rewrite history + force-push (coordinate with all workers; history rewrite is disruptive). No session/token/key rotation is required for this finding. Consider also removing the hardcoded default fallback in `backend/config.py` (fail closed or use placeholder) so the mailbox does not ship in code.

## Reference-only / false positives (no secret value, no action, also in HEAD unless noted)

All below matched keywords but carry no value: empty template assignments, `os.getenv` / `Get-EnvValue` reads, function signatures, docs saying "no keys" / "Bearer ...", test placeholders, public usernames/dataset slugs, integrity hashes, transformer `token` variables, SQL `BEGIN`. Severity Info. HEAD status verified via `git show HEAD:<path>` (working-tree line == HEAD line); history patches for tunnel/session/kaggle values show empty/comment-only (no values ever committed).

- `.env.example:8` — session-secret-assignment (empty template, no value) — Info — also in HEAD
- `archive/legacy_web_dashboard/package-lock.json:3148` — high-entropy-string (package integrity hash) — Info — also in HEAD
- `archive/legacy_web_dashboard/package-lock.json:7553` — high-entropy-string (package integrity hash) — Info — also in HEAD
- `archive/legacy_web_dashboard/public/og.png:13` — email-address (binary embedded cert, false positive) — Info — also in HEAD
- `archive/legacy_web_dashboard/public/og.png:28` — email-address (binary, false positive) — Info — also in HEAD
- `archive/legacy_web_dashboard/public/og.png:33` — email-address (binary, false positive) — Info — also in HEAD
- `archive/legacy_web_dashboard/public/og.png:128` — email-address (binary, false positive) — Info — also in HEAD
- `archive/legacy_web_dashboard/public/og.png:133` — email-address (binary, false positive) — Info — also in HEAD
- `archive/legacy_web_dashboard/public/og.png:4840` — email-address (binary, false positive) — Info — also in HEAD
- `archive/legacy_web_dashboard/public/og.png:16419` — email-address (binary, false positive) — Info — also in HEAD
- `backend/auth.py:79` — generic-secret-assignment (runtime-generated secret, no hardcoded value) — Info — also in HEAD
- `backend/config.py:37` — session-secret-assignment (env-var read, no value) — Info — also in HEAD
- `backend/config.py:62` — session-secret-assignment (empty-check, no value) — Info — also in HEAD
- `backend/server.py:175` — generic-secret-assignment (request header variable, no value) — Info — also in HEAD
- `backend/server.py:179` — generic-secret-assignment (cookie variable, no value) — Info — also in HEAD
- `backend/server.py:186` — generic-secret-assignment (refresh variable, no value) — Info — also in HEAD
- `bot/bybit_v5.py:302` — api-key-assignment (function signature, no value) — Info — also in HEAD
- `bot/bybit_v5.py:311` — api-key-assignment (constructor signature, no value) — Info — also in HEAD
- `bot/bybit_v5.py:311` — api-secret-assignment (constructor signature, no value) — Info — also in HEAD
- `bot/run.py:5` — bybit-api-reference (docs comment naming env vars, no value) — Info — also in HEAD
- `bot/run.py:336` — bybit-api-reference (comment "no keys", no value) — Info — also in HEAD
- `bot/run.py:342` — bybit-api-reference (variable pass-through, no value) — Info — also in HEAD
- `configs/opencode_v105_dossier5.json:87` — kaggle-json-username-key (public dataset owner name, not a secret) — Info — also in HEAD
- `configs/opencode_v105_dossier5.json:94` — kaggle-json-username-key (public dataset owner name) — Info — also in HEAD
- `configs/opencode_v114_dossier6.json:93` — kaggle-json-username-key (public dataset owner) — Info — also in HEAD
- `configs/opencode_v114_dossier6.json:100` — kaggle-json-username-key (public dataset owner) — Info — also in HEAD
- `configs/opencode_v118_dossier7.json:99` — kaggle-json-username-key (public dataset owner) — Info — also in HEAD
- `configs/opencode_v118_dossier7.json:106` — kaggle-json-username-key (public dataset owner) — Info — also in HEAD
- `configs/opencode_v120_dossier8.json:99` — kaggle-json-username-key (public dataset owner) — Info — also in HEAD
- `configs/opencode_v120_dossier8.json:106` — kaggle-json-username-key (public dataset owner) — Info — also in HEAD
- `configs/opencode_v126_dossier9.json:99` — kaggle-json-username-key (public dataset owner) — Info — also in HEAD
- `configs/opencode_v126_dossier9.json:106` — kaggle-json-username-key (public dataset owner) — Info — also in HEAD
- `configs/opencode_v139_dossier11.json:120` — kaggle-json-username-key (public dataset owner) — Info — also in HEAD
- `configs/opencode_v139_dossier11.json:127` — kaggle-json-username-key (public dataset owner) — Info — also in HEAD
- `configs/opencode_v141_dossier12.json:128` — kaggle-json-username-key (public dataset owner) — Info — also in HEAD
- `configs/opencode_v141_dossier12.json:135` — kaggle-json-username-key (public dataset owner) — Info — also in HEAD
- `configs/opencode_v150_dossier13.json:136` — kaggle-json-username-key (public dataset owner) — Info — also in HEAD
- `configs/opencode_v150_dossier13.json:143` — kaggle-json-username-key (public dataset owner) — Info — also in HEAD
- `configs/opencode_v153_dossier13.json:144` — kaggle-json-username-key (public dataset owner) — Info — also in HEAD
- `configs/opencode_v153_dossier13.json:151` — kaggle-json-username-key (public dataset owner) — Info — also in HEAD
- `configs/opencode_v157_dossier14.json:144` — kaggle-json-username-key (public dataset owner) — Info — also in HEAD
- `configs/opencode_v157_dossier14.json:151` — kaggle-json-username-key (public dataset owner) — Info — also in HEAD
- `configs/opencode_v23_fundingfeat.json:2` — binance-api-reference (long prose line, no key) — Info — also in HEAD
- `configs/opencode_v23_fundingfeat.json:2` — high-entropy-string (same prose line, false positive) — Info — also in HEAD
- `configs/opencode_v46_ethfilter.json:13` — binance-api-reference (text "NO key", no value) — Info — also in HEAD
- `docs/WEB_DEPLOY.md:117` — bearer-token (docs prose, placeholder, no value) — Info — also in HEAD
- `docs/WEB_DEPLOY.md:129` — cloudflare-token-reference (docs naming env var, no value) — Info — also in HEAD
- `docs/WEB_DEPLOY.md:129` — tunnel-token-reference (same docs line, no value) — Info — also in HEAD
- `docs/WEB_DEPLOY.md:146` — bearer-token (docs placeholder `Bearer ...`, no value) — Info — also in HEAD
- `docs/WEB_DEPLOY.md:181` — bearer-token (docs prose, no value) — Info — also in HEAD
- `docs/WEB_DEPLOY.md:182` — bearer-token (docs prose, no value) — Info — also in HEAD
- `docs/WEB_SECURITY_REVIEW_20261002.md:26` — bearer-token (review prose, no value) — Info — also in HEAD
- `docs/WEB_SECURITY_REVIEW_20261002.md:29` — bearer-token (review prose, no value) — Info — also in HEAD
- `docs/WEB_SECURITY_REVIEW_20261002.md:114` — bearer-token (review prose, no value) — Info — also in HEAD
- `docs/WEB_SECURITY_REVIEW_20261002.md:138` — bearer-token (review prose, no value) — Info — also in HEAD
- `docs/WEB_SECURITY_REVIEW_20261002.md:158` — bearer-token (review prose, no value) — Info — also in HEAD
- `docs/WEB_SECURITY_REVIEW_20261002.md:210` — bearer-token (review prose, no value) — Info — also in HEAD
- `docs/legacy/KRONOS_TRADING.md:63` — kaggle-key-reference (instruction "do not commit", no value) — Info — also in HEAD
- `docs/legacy/KRONOS_TRADING.md:67` — kaggle-key-reference (path outside repo, no value) — Info — also in HEAD
- `docs/opencode/KAGGLE_PREP_20261006.md:65` — kaggle-key-reference (scan description, no value) — Info — also in HEAD
- `docs/opencode/KAGGLE_PREP_20261006.md:67` — kaggle-key-reference (scan description, no value) — Info — also in HEAD
- `docs/opencode/OPENCODE_W_audit_repo_secrets.md:2` — bearer-token (this task brief word list, no value) — Info — also in HEAD
- `docs/opencode/OPENCODE_W_audit_repo_secrets.md:2` — cloudflare-token-reference (same brief word list, no value) — Info — also in HEAD
- `docs/opencode/PREPUSH_AUDIT_20261006.md:6` — bybit-api-reference (audit method description, no value) — Info — also in HEAD
- `docs/opencode/PREPUSH_AUDIT_20261006.md:6` — kaggle-key-reference (same method description, no value) — Info — also in HEAD
- `docs/opencode/PREPUSH_AUDIT_20261006.md:10` — email-address (decorator false positives + example domains only) — Info — also in HEAD
- `docs/opencode/PREPUSH_AUDIT_20261006.md:23` — bearer-token (audit prose, no value) — Info — also in HEAD
- `frontend/app.js:58` — generic-secret-assignment (in-memory session variable, no value) — Info — also in HEAD
- `frontend/index.html:203` — email-address (generic placeholder mailbox, not personal) — Info — also in HEAD
- `research/data_fetch/bybitq/REPORT.md:3` — bybit-api-reference (text "no keys", no value) — Info — also in HEAD
- `research/data_fetch/liqhist/REPORT.md:64` — binance-api-reference (text "no key", no value) — Info — also in HEAD
- `research/mj/fetch_um_metrics.py:1` — binance-api-reference (docstring "no key", no value) — Info — also in HEAD
- `research/tournament/oc_utamargin2/REPORT.md:27` — bybit-api-reference (text "no keys", no value) — Info — also in HEAD
- `run_backend.ps1:10` — cloudflare-token-reference (comment naming env var, no value) — Info — also in HEAD
- `run_backend.ps1:10` — tunnel-token-reference (same comment, no value) — Info — also in HEAD
- `run_backend.ps1:49` — cloudflare-token-reference (env-var read, no value) — Info — also in HEAD
- `run_backend.ps1:49` — generic-secret-assignment (local variable receiving env read, no value) — Info — also in HEAD
- `run_backend.ps1:49` — tunnel-token-reference (same env read, no value) — Info — also in HEAD
- `run_backend.ps1:52` — cloudflare-token-reference (missing-value warning, no value) — Info — also in HEAD
- `run_backend.ps1:52` — tunnel-token-reference (same warning, no value) — Info — also in HEAD
- `scripts/bot_preflight.py:408` — bybit-api-reference (variable pass-through, no value) — Info — also in HEAD
- `scripts/bot_preflight.py:412` — bybit-api-reference (variable pass-through, no value) — Info — also in HEAD
- `scripts/fetch_binance_premium.py:3` — binance-api-reference (text "no key", no value) — Info — also in HEAD
- `scripts/fetch_quarterly_basis.py:1` — binance-api-reference (docstring "no keys", no value) — Info — also in HEAD
- `scripts/fetch_um_universe_2020.py:1` — binance-api-reference (docstring "no keys", no value) — Info — also in HEAD
- `scripts/opencode_crawl_1m.py:1` — binance-api-reference (docstring "no key", no value) — Info — also in HEAD
- `scripts/opencode_crawl_eth.py:1` — binance-api-reference (docstring "no key", no value) — Info — also in HEAD
- `scripts/opencode_crawl_forward.py:4` — binance-api-reference (comment "no key", no value) — Info — also in HEAD
- `scripts/opencode_crawl_funding.py:101` — binance-api-reference (argparse "public, no key", no value) — Info — also in HEAD
- `scripts/opencode_r10m_rankloss_package.py:242` — kaggle-key-reference (secret-clean marker list, no value) — Info — also in HEAD
- `scripts/opencode_r17b_rankonly_package.py:241` — kaggle-key-reference (secret-clean marker, no value) — Info — also in HEAD
- `scripts/opencode_r19m_v39_package.py:253` — kaggle-key-reference (secret-clean marker, no value) — Info — also in HEAD
- `scripts/opencode_r21b_v55b_package.py:245` — kaggle-key-reference (secret-clean marker, no value) — Info — also in HEAD
- `scripts/opencode_r25m_v40_package.py:256` — kaggle-key-reference (secret-clean marker, no value) — Info — also in HEAD
- `scripts/opencode_r26b_v55c_package.py:246` — kaggle-key-reference (secret-clean marker, no value) — Info — also in HEAD
- `scripts/opencode_r30m_v41_package.py:258` — kaggle-key-reference (secret-clean marker, no value) — Info — also in HEAD
- `scripts/opencode_r32m_transformer_package.py:263` — kaggle-key-reference (secret-clean marker, no value) — Info — also in HEAD
- `scripts/opencode_r37m_student_package.py:254` — kaggle-key-reference (secret-clean marker, no value) — Info — also in HEAD
- `scripts/opencode_r40b_v55bfix_package.py:251` — kaggle-key-reference (secret-clean marker, no value) — Info — also in HEAD
- `scripts/opencode_r48m_attndistill_package.py:256` — kaggle-key-reference (secret-clean marker, no value) — Info — also in HEAD
- `scripts/opencode_r50m_v106rebuild_package.py:256` — kaggle-key-reference (secret-clean marker, no value) — Info — also in HEAD
- `scripts/opencode_r55b_ethscout_crawl5m.py:1` — binance-api-reference (docstring "public", no value) — Info — also in HEAD
- `scripts/opencode_r56b_maelabels_package.py:300` — kaggle-key-reference (secret-clean marker, no value) — Info — also in HEAD
- `scripts/opencode_r56m_regime_package.py:266` — kaggle-key-reference (secret-clean marker, no value) — Info — also in HEAD
- `scripts/opencode_r69m_regimemoe_package.py:274` — kaggle-key-reference (secret-clean marker, no value) — Info — also in HEAD
- `scripts/opencode_r6m_bigmodel_model.py:79` — generic-secret-assignment (transformer variable named `token`, no secret) — Info — also in HEAD
- `scripts/opencode_r6m_bigmodel_model.py:81` — generic-secret-assignment (same transformer variable) — Info — also in HEAD
- `scripts/opencode_r6m_bigmodel_package.py:186` — kaggle-key-reference (secret-clean marker, no value) — Info — also in HEAD
- `scripts/opencode_r7a2_multitask_package.py:176` — kaggle-key-reference (secret-clean marker, no value) — Info — also in HEAD
- `scripts/opencode_r9m_nextarch_package.py:231` — kaggle-key-reference (secret-clean marker, no value) — Info — also in HEAD
- `src/agentic_alpha_lab/models/tcn_fusion_value.py:64` — generic-secret-assignment (transformer variable, no secret) — Info — also in HEAD
- `src/agentic_alpha_lab/models/tcn_fusion_value.py:66` — generic-secret-assignment (transformer variable, no secret) — Info — also in HEAD
- `src/agentic_alpha_lab/models/transformer_value.py:30` — generic-secret-assignment (transformer variable, no secret) — Info — also in HEAD
- `src/agentic_alpha_lab/models/transformer_value.py:31` — generic-secret-assignment (transformer variable, no secret) — Info — also in HEAD
- `src/agentic_alpha_lab/models/transformer_value.py:34` — generic-secret-assignment (transformer variable, no secret) — Info — also in HEAD
- `tests/test_web_frontend.cjs:44` — generic-secret-assignment (test fixture variable, no value) — Info — also in HEAD
- `tests/test_web_frontend.cjs:63` — bearer-token (test placeholder `Bearer new`, no value) — Info — also in HEAD
- `tests/test_web_frontend.cjs:76` — bearer-token (same test placeholder) — Info — also in HEAD
- `tests/test_web_frontend.cjs:141` — bearer-token (test name prose, no value) — Info — also in HEAD
- `tests/test_web_frontend.cjs:146` — bearer-token (same test placeholder) — Info — also in HEAD
- `tests/test_web_frontend.cjs:278` — bearer-token (same test placeholder) — Info — also in HEAD
- `tests/test_web_frontend.cjs:301` — bearer-token (test name prose, no value) — Info — also in HEAD
- `tests/test_web_frontend.cjs:310` — bearer-token (same test placeholder) — Info — also in HEAD
- `tests/test_web_frontend.cjs:387` — bearer-token (test name prose, no value) — Info — also in HEAD
- `tests/test_web_frontend.cjs:391` — bearer-token (same test placeholder) — Info — also in HEAD

Explicit non-findings (zero hits in HEAD and no values in history): private-key blocks (only SQL `BEGIN IMMEDIATE` and secret-clean marker strings), passwords, `AKIA` / `gh*` / `sk-` / `xox*` token prefixes (only docs mentions and `risk-` false positives), `GOCSPX-` (only audit-method mention), Google client IDs (no `apps.googleusercontent` value), discord/slack/telegram webhooks with tokens, `trycloudflare` / `cfargotunnel` hostnames (none found), tunnel-token values (template empty; history patches empty/comment-only), session-secret values (template empty; history empty), Kaggle key values / `kaggle.json` files (none tracked; history shows only env-var reads and public dataset slugs), Bybit/Binance key values (only public endpoints and "no key" notes). Custom public hostnames (API/FE domains) appear in docs/config/frontend by design and are not counted as private-tunnel leaks; no secret is co-located with them.
