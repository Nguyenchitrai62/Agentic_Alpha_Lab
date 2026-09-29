# O1 B18 robustness report (deployed pipeline) - bounded task for OpenCode

Leader: Claude Code owns all decisions; you produce ONE diagnostic report of the frozen deployed pipeline (nothing is selected on it).
Read AGENTS.md. Write ONLY `research/diagnostics/o1_robustness/o1_robustness.py`, its `o1_robustness.json`, a `SUMMARY.md` (<= 25 lines)
and `tests/test_o1_robustness.py`. Do not edit any other file, config, registry, ledger, ../Kronos or git state.

Template: copy the structure of `research/diagnostics/w2_robustness/w2_robustness.py` (same rows, same bootstrap) but on the DEPLOYED O1
pipeline: books = 0.5 (A + B)/2 + 0.5 (Aq + Bq)/2 with the cached members `member_A_O1_orders.parquet`, `member_Aq_O1_orders.parquet`,
`member_B_tv.parquet`, `member_Bq_tv.parquet` (engine_real CACHE, see
`research/parallel/rounds/parallel-20260906-r2/v247/v247_o1_sleeve_budget.py`), engine_user trade mode with
`trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))`, `win_start=5`, `**dict(v221.KW, sleeve_risk_budget=0.18)`.
The base row MUST reproduce dev4 5.777, gate DD 19.65, 5y 5.436, most recent year 4.082 (assert).
Rows: base; cost_stress (maker 0.04%, taker 0.07% + 5 bps on taker fills, as in the template); latency_15 / latency_30 / latency_60 (as in
the template); band_lo / band_hi; cool_3 / cool_12; sleeve_0.16 / sleeve_0.20 (budget instead of 0.18); offset_0.15 / offset_0.40.
For every row report dev4, every walk-forward year (net %, 1m DD), 5y monthly, most recent year monthly, gate DD, losing years, trade win
rate (v213.trade_stats). Bootstrap exactly as the template (daily returns of base over the first four years, 30-day blocks, 2000 draws,
seed 0): median / 5% / 95% of the 1-year return and max DD, P(loss year), P(DD > 20%), P(>= 5%/month).
Also, for a USDT account of 2000: using the Bybit lot rules (min qty BTC 0.001, ETH 0.01, SOL 0.1, BNB 0.01, XRP 0.1; min notional 5 USDT;
see research/parallel/rounds/parallel-20260906-r2/v245 for the existing small-account code if present) report the share of book orders and
dip-rung orders that are placeable at equity 2000 USDT over the most recent year.
Test: the base row reproduction assert and one cost_stress sanity check (net lower than base). Run
`.venv/Scripts/python.exe -m pytest tests/test_o1_robustness.py -q`. SUMMARY.md: table of rows + bootstrap + placeable shares + a plain
verdict on how fragile the pipeline is (which knobs / latencies break the DD <= 20% or the no-losing-year rule). Stop when done.
