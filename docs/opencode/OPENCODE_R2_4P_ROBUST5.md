# OpenCode task: robustness of the deployed BOT R2-4P over five years with the per-year reset metric (read AGENTS.md, OPENCODE_VF_COMMON.md)

Write ONLY under `research/diagnostics/r2_4p_robust5/` and `tests/test_r2_4p_robust5.py`; ONE heavy process at a time (run scenarios
sequentially), RAM < 2.5 GB; no commits; do not edit leader files. Market data up to 2026-09-24 00:00 UTC may be read (all years are research
data now).

Baseline = research/diagnostics/r2_decompose5/r2_decompose5.py run 'R2' (honest 4-phase harness: phase_offset_full prep_idx on the full
standard index shifted by s = 0..3 h, standard books forward-filled, pipe_setup("v321") with v376/tables_hidden r2_table_s{s}.parquet,
win_start 5, live 2021-09-24 + s h .. 2026-09-23 + s h). Metric = research/diagnostics/r2_decompose5/reset_metric.py year_reset (sub-accounts
reset to 1/4 at each anchor) for the five years 2021-09-24 .. 2025-09-24 anchors; report per year %/month and DD, the 5-year geometric mean,
the max year DD, and the full-path conservative DD of an equal 1/4 mix started 2021-09-24 (v388.mix).
Scenarios (each = one full 4-phase run; reuse r2_decompose5/runs.pkl for the baseline - verify you reproduce its phase-0 final equity first):
 S1 cost stress: engine_user module constants MAKER 0.0004 / TAKER 0.0007 (patch simulate.__globals__ as research/diagnostics/r2_robustness
    did - read it) + 5 bps on taker fills if the engine supports it (check engine_user.simulate kwargs; otherwise document);
 S2 latency 15 min: win_start 15 and sleeve_start 16 (book orders from minute 15);
 S3 latency 30 min: win_start 30, sleeve_start 31;
 S4 stop slip 50 %: engine kwarg stop_slip = 0.5 if available (read engine_user.simulate signature);
 S5 Bybit prices: the 1m cube / opens built from data/raw/bybit_linear_1m_20261004/<SYM>_1m.parquet instead of Binance (as research/diagnostics/
    bybit_execution/bybit_engine.py does; Bybit data ends 2026-10-03; SOL starts 2021-10-15 - start all phases at 2021-11-15 for S5 and compare
    with the baseline restricted to the same window).
Deliverables: results.json, REPORT.md (scenario x year table, 5-year geometric mean, DD), the reproduction check, and a one-paragraph verdict:
which frictions break the >= 0 per-year floor or push DD above 25.
