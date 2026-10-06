# Web review 2026-10-06: carry panel (read-only, pre-deploy)

Scope: backend/server.py GET /api/carry, backend/carry_view.py,
frontend/app.js renderCarry, frontend/index.html carry panel,
tests/test_web_carry.py. No code fixes: no real bug found.

- Auth (pass): server.py:292 route uses Depends(auth.require_viewer),
  same as other viewer routes; global require_api_access (server.py:30-31,
  auth.py:231-243) rejects anonymous (401) and pending (403); covered by
  tests/test_web_carry.py:156-175.
- Secret/path leaks (pass): carry_view.py:127-144 returns only
  tag/rule/sha/pairs/totals/updated_at/stale/has_data; no paths, no env,
  no tokens. rule is RULE_PARAMS (scripts/carry_paper.py:39-52: coins,
  thresholds, fees) with no paths. Cache key "carry" (server.py:295) is
  global, correct: payload holds no per-user data.
- Escaping (pass): app.js:543,546,550-559,566 every string via esc();
  numbers via Number().toFixed so no HTML injection; dates via dt() then
  esc(); done.length (app.js:557) is an array length, safe.
- Robust empty/corrupt (pass): carry_view.py:44-51 returns None on
  missing/corrupt/non-dict; summarize coerces positions/history/totals
  (62-70), skips non-dict rows (75,105), _num/_parse_time guard bad types;
  missing file -> has_data false, stale true, updated_at null.
- Number/date locale (pass): dates via dt() vi-VN (app.js:33,542,550,558);
  amounts toFixed(2)+" USDT", basis/MtM toFixed(2)+"%", days toFixed(0)+
  " ngày" — same style as pct/sgn/fmtPx elsewhere.
- Cache TTL (pass): 60 s (server.py:295), same band as pipelines_summary/
  overview; stale flag itself is 2 h ledger age (carry_view.py:14,123),
  so a 60 s delay never masks staleness materially.
- Isolation (pass): renderCarry try/catch (app.js:537-566) degrades to one
  muted line; loadTodo (app.js:433) does not await it, so other panels
  still render; logout clears carryBody/carryMeta (app.js:202); index.html:
 87-92 panel is static markup with no script of its own.
- Tests: tests/test_web_carry.py 7 passed (missing/corrupt/open/settled/
  stale-boundary/auth/empty-file). Only warnings are pre-existing
  FastAPI on_event deprecations.
- Cosmetic note (not a bug, ledger is server-local): corrupt numeric
  fields render as "NaN…" (Number(x).toFixed on non-numeric); consistent
  with fail-open read-only view, no fix needed.
