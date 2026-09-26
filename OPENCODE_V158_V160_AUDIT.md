# v158 + v159 + v160 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v158_v160_audit/` and `tests/test_v158_v160_audit.py`.
Base: your v154 replication (members A, B, D; v150 options features definitions). Do NOT open v158/, v159/ or v160/ until
part A is saved (`replication.json`). All members: extra market-wide columns merged on t into the v114 and v103 panels
BEFORE the v142 xs step, no xs versions of them, vol models exclude them; v144 engine rows (0.15 ungoverned, 0.20/0.25
governed, 10 bps 1m execution).
A1 (v158): books (A + B' + D)/3 where B' has the five v150 BTC options features plus the same five from
data/raw/deribit_opt_20260926/ETH_options_4h.parquet prefixed eth_ (outer join on t).
A2 (v159): books (A + B + D + G)/4; G features from data/raw/fng_20260926/fng_daily.parquet: value for date D available at
D + 1h; for panel row t use the last value available at t + 4h: fng, fng7 = rolling-7 mean of daily values, fng_chg7 =
fng - fng.shift(7), fng_z = (fng - rolling90 mean(min 60))/rolling90 std(min 60) (daily series).
A3 (v160): books (A + B + D + H)/4; H from data/raw/cftc_20260926/btc_cme_tff.parquet (dedup report dates): report date D
usable from D + 4 days; lev = (Lev_Money long - short)/Open_Interest_All, am = (Asset_Mgr long - short)/OI;
cot_lev_net, cot_am_net, *_chg4 = x - x.shift(4), *_z = (x - rolling52 mean(min 26))/rolling52 std(min 26) (weekly series).
Save `replication.json`, compare with v158/v159/v160 result JSONs (explain return diff > 1pp or DD diff > 0.5pp), audit
the three scripts for look-ahead (availability rules!), write COMPARISON.md. Do not edit leader files.
