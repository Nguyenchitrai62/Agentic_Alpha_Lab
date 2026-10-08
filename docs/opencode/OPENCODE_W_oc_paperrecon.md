# OpenCode task oc_paperrecon - does the live paper runner reproduce the research engine on the same days? (P&L reconciliation)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/diagnostics/oc_paperrecon/` and `tests/test_oc_paperrecon.py`.
artifacts/bot/* are READ-ONLY (copy what you need). Public market-data GETs only. Print progress every 10 minutes. Engine via heavy_slot.

## Why
All research numbers come from the engine; the decision about G2 / K2 / C2 will come from paper runners (bot/paper.py on live Bybit klines).
If paper and engine disagree on the same days, either the evidence or the engine is biased. bot_parity / oc_planparity checked rules and plans,
not P&L.

## Method
Window: the paper period of artifacts/bot/paper_d17bfg2 (G2) from its start to now, excluding outage gaps (runner deaths 2026-10-07 03:24-07:00,
backend plan outage 2026-10-07 ~14:30-23:46 UTC - find them in actions.jsonl: stale_plan ops / missing cycles). Fetch Bybit linear 1m klines
for the 5 majors over the window (public v5 market/kline). Replay the SAME plans the runner saw (plan history in the backend DB / advisor_shadow
files or the plan fields logged in actions.jsonl; say which) through the research engine rules (bot rules = engine rules per bot_parity) on
Bybit 1m, and compare per piece: fills (count, price), exits (TP / stop / time), P&L, fees, funding, and the equity curve vs the runner's
state / actions. Report every mismatch class with counts and P&L impact; total paper vs replay return; Vietnamese 3-line verdict: can the
paper log be trusted as evidence for the research numbers?
