# v161 + v162 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v161_v162_audit/` and `tests/test_v161_v162_audit.py`.
Base: your v154 replication (members A, B, D). Do NOT open v161/ or v162/ until part A is saved (`replication.json`).
A1 (v161): kp_a = 1e4*log(Upbit KRW-a close of the 1h candle with open_time <= t+3h (asof backward, tolerance 2h; files
data/raw/upbit_20260926/KRW-{a}_1h.parquet) / Binance spot aUSDT 4h close at t (2017 prefix + spot file, dedup)) for a in
BTC ETH XRP SOL; smooth(s): p6 = roll6 mean(min 4), p42 = roll42 mean(min 30), m/sd = roll540 mean/std(min 270); dev = p6-m,
z = dev/sd, chg = p6-p42 (on each coin's spot-bar series). Market (per t): kp_btc_dev/z/chg of kp_btc. Asset (t, sym):
rp = kp_a - kp_btc aligned on t (0 for BTC; BNB absent -> NaN): rp_dev/z/chg = smooth(rp). Member K = v144 builder with market
merged on t and asset merged on (t, sym) before the v142 xs step (no xs of them; vol models exclude them). Books =
(A+B+D+K)/4, v144 engine rows.
A2 (v162): all three members rebuilt with the v92 and v94 HGBs given monotonic_cst = +1 (dict by feature name) for the
features present among: ret6 ret42 ret90 ret180 ret540 snr6 snr42 snr90 snr180 snr540 ema20 ema200 d50 d200 rib btc_ret42
btc_ret180 btc_rib btc_snr42 (v103 models unconstrained). Books = (A+B+D)/3, v144 engine rows.
Save `replication.json`, compare with v161/v162 result JSONs (explain return diff > 1pp or DD diff > 0.5pp), audit both
scripts for look-ahead, write COMPARISON.md. Do not edit leader files.
