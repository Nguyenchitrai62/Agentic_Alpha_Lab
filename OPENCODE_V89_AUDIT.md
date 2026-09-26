# v89 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Reproduce from this spec BEFORE opening `research/parallel/rounds/parallel-20260906-r2/v89/*`.
Write only under `research/parallel/rounds/parallel-20260906-r2/v89_audit/` (create it) and `tests/test_v89_audit.py`.
Spec: 4h USD-M bars for BTC (`data/raw/ma_ribbon_20260924/klines_4h.parquet`, `klines_1d`, `funding.parquet`) and
ETH/SOL/BNB/XRP (`data/raw/xs_universe_20260924/{SYM}_{4h,1d,funding}.parquet`). Per asset-bar features at close:
log return over k bars and k-bar return / (std of last 42 1-bar log returns * sqrt(k)) for k in 6,42,90,180,540;
std of 1-bar log returns over 42 and 180 and their ratio; log(close/EMA20), log(close/EMA200) (pandas ewm span,
adjust=False, min_periods=span); from the last CLOSED daily bar: log(close/SMA50), log(close/SMA200), ribbon
(+1 close>SMA50>SMA200, -1 close<SMA50<SMA200, else 0); funding mean of last 21 prints and 90 prints (x1e4) known
at bar close; log quote volume z-score over 180 bars; asset id 0..4; BTC's ret42, ret180, ribbon, snr42 at the same
open_time. Target y = clip(log(open[t+43]/open[t+1]) / (std42_t * sqrt(42)), -4, 4).
Model: sklearn HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300,
l2_regularization=1.0, random_state=0). For anchor A=2025-09-24: cutoff = A - 4h*(42+60); train rows with
open_time < cutoff and open_time + 4h*43 < cutoff and y not NaN (all assets pooled); predict rows with
open_time in [A, A+365d).
A. Save `replication.json`: number of training rows and Spearman correlation between prediction and y on the
   predicted rows (drop NaN y). Leader value to compare after saving: listed in the v89 folder.
B. Then open the v89 folder, compare (difference in IC > 0.01 or train rows mismatch = explain root cause) and audit
   v89_pooled_hgb.py for look-ahead (features, label realization/embargo, portfolio K rule, execution timing).
   Write `COMPARISON.md`. Do not edit leader files.
