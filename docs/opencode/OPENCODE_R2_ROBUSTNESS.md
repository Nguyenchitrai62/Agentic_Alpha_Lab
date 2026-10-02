# R2 robustness report (diagnostic; read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Candidate: the BOT pipeline R2 (v321) vs the deployed G2 (v301), both in the deployed BAR-OPEN form. Template: copy
research/diagnostics/s1_robustness/s1_robustness.py (rows, bootstrap, small-account check) and adapt the two legs:
  G2_*: books CB = (2A + 2B + D)/5 from the v306 member groups (= 0.8 C4 + 0.2 (D + Dq)/2), lookup hooks from
        artifacts/research/engine_real/v301_g2_table_m0.parquet (keys: holding bar T = decision bar + 4h, symbol, rung index), rungs (2.5, 3, 3.5, 4),
        sleeve_risk_budget 0.26, size_mult 1.75, align (1.5, 0.5), close5 stop 4 sigma + 8-sigma backstop, grid_policy(0.03, 0.40), win_start 5.
        Base must reproduce dev4 6.504 / gate DD 17.09 / 5y 6.272 / most recent year 5.349.
  R2_*: same books and rules, hooks from artifacts/research/engine_real/v321_r2_table_m0.parquet, rungs (2.5, 3, 3.5, 4, 5). Base must reproduce
        dev4 7.079 / gate DD 18.39 / 5y 6.793 / most recent year 5.655.
Rows for both legs: base, cost_stress (maker 0.0004, taker 0.0007 + 0.0005), latency_15 / 30 / 60 (book win_start), band_lo / band_hi, cool3 / cool12,
sleeve budget 0.22 / 0.30, offset 0.15 / 0.40, outage_backstop_only (stop touch at 8 sigma, no close stop), close_1m; sleeve_start 21 / 31
(the bot places the ladder 5 / 15 minutes late); the stationary block bootstrap (first four years, 30-day blocks, 2000 draws, seed 0) and the
small-account check at 1000 and 2000 USDT (Bybit lots). Diagnostic only - nothing is selected on it; report the most recent year as a row field as
the template does.
Write only under `research/diagnostics/r2_robustness/` (script r2_robustness.py, r2_robustness.json, SUMMARY.md) and `tests/test_r2_robustness.py`;
relative paths without quoting; do not edit any engine or leader file. SUMMARY.md: the per-row table G2 vs R2 and a verdict line "R2 at least as
robust as G2: YES/NO" with the reasons (rows where DD <= 20 holds, bootstrap odds, losing years).
