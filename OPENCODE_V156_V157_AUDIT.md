# v156 + v157 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v156_v157_audit/` and `tests/test_v156_v157_audit.py`.
Base: your v154 replication (members A, B, D). Do NOT open v156/ or v157/ until part A is saved (`replication.json`).
A1 (v156): member E = v144 builder with DVOL features merged on t before the v142 xs step (no xs versions; vol models exclude
them): data/raw/dvol_20260924/dvol_hourly.parquet, candle available at avail_utc; for panel row t take the last candle with
avail_utc <= t + 4h (merge_asof backward on the BTC rows); c = dvol_close (>0); dvol_lvl = c; dvol_chg24 = log(c/c.shift(24));
dvol_chg168 = log(c/c.shift(168)); dvol_z = (c - rolling2160 mean(min 720))/rolling2160 std(min 720) (shifts/rollings on the
hourly series); dvol_rvspread = dvol_lvl - 100*vol180*sqrt(2190) with vol180 of the BTC row at t. Books = (A+B+D+E)/4.
A2 (v157): member F = v144 builder with agentic_alpha_lab.patterns.macro.compute(bars) features for bars (t, close_time =
t + 4h - 1ms) over the unique panel times, merged on t before the xs step (vol models exclude them). Books = (A+B+D+F)/4.
Both: v144 engine rows (0.15 ungoverned, 0.20/0.25 governed, 10 bps 1m execution); report monthly, yearly, full-path DD.
Save `replication.json`, compare with v156/v157 result JSONs (explain return diff > 1pp or DD diff > 0.5pp), audit both
scripts for look-ahead (DVOL availability and macro 22:00 UTC rule), write COMPARISON.md. Do not edit leader files.
