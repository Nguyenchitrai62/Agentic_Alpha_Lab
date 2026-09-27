# v188 + engine_user blind audit - adversarial (read AGENTS.md (updated 2026-09-27), .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v188_audit/` and `tests/test_v188_audit.py`. Use
relative paths without quoting. Do NOT open engine_user/ or v188/ until part A is saved (`replication.json`).
engine_user becomes the gate engine, so implement it independently from AGENTS.md "User goal and validation protocol"
and "Current execution assumptions" plus this spec:
Inputs: books = artifacts/research/engine_real/books_v154.parquet, opens = artifacts/research/engine_real/opens_v154.parquet,
1m klines of the majors (btc_intraday / majors_intraday). For decision bar t (index of books), holding bar T = t + 4h.
Vol target: realized = 0.8 * sum_j books[t-2, j] * (open[t,j]/open[t-1,j] - 1); vol = rolling std 360 (min 120) *
sqrt(2190); s = min(0.25/vol, 2) (1 if NaN); governor g = clip((0.20 - (1 - eq[t-2]/max eq over the 540 bars ending
t-2))/0.10, 0, 1). Live span 2021-09-24 .. +1825 d. Target weight = 0.8 * s * books[t] * g.
Positions are quantities: q = w / open(T) at bar start (w = weight drifted from the previous bar end, q * open(T+4h) /
end equity). Order dw = target - w (skip if |dw| * equity * 10000 < min notional: BTC 100, ETH 20, others 5, unless the
target is 0 and the position is not). Limit at open_1m(T, minute 0) * (1 -/+ 0.001), filled at the limit if a 1m low
(buy) / high (sell) in minutes 2..59 trades through it (strict), maker 0.0002; otherwise it expires. Average entry
price: new position -> fill; adding same side -> weighted; reducing -> unchanged; flip -> fill.
Stops/TP per asset with m = 2, 3, 4: sigma_d = std of 360 4h open-to-open returns ending at t * sqrt(6); long SL =
entry (1 - m sigma_d), TP = entry (1 + 2 m sigma_d) (short mirrored); levels reset at each decision; checked from minute
0 on the position held (before the fill) and from the fill minute on the new position; SL if low <= SL (long), filled at
min(SL, minute open), taker 0.00055; TP on high > TP, maker 0.0002; both in one minute -> SL first; after SL/TP the
asset is flat for the rest of the bar and the pending order is cancelled if not yet filled.
Funding: a long held at the end of the bar pays 0.0001 of its notional if T + 4h is 00/08/16 UTC; shorts 0. No carry.
Sleeve: rungs k = 2.5/3/3.5/4 with sigma_4h (not daily), bid L = open(T) (1 - k sigma_4h) live minutes 16..238, maker
fill on low < L; exits after the fill minute: SL at L (1 - 2 sigma_4h) (low <= SL, fill min(SL, open), taker), TP at
L (1 + sigma_4h) (high > TP, maker), else at open(T + 4h) taker paying 0.0001 if that is a settlement; rung notional
rn = s g 0.25/4/1.657; fills taken in (minute, rung, asset) order iff (open rungs at that minute + 1) rn <= 1/6.
1m-marked equity per minute = start equity * (1 + sum of position MTM + sleeve MTM); gate DD = max(4h-close DD,
1m-marked DD); per anchor year net/monthly; monthly_dev4 = geometric mean of the first four anchor years.
Rows: m = 2, 3, 4 (with sleeve), selection = best monthly_dev4 among variants with DD <= 20 and no losing year in the first
four years; that variant without the sleeve. Save `replication.json`.
B: compare with `v188/v188_result.json`; audit engine_user.py and v188 for leakage (every decision uses data <= t;
sigma windows; the selection uses only the first four years), fill/stop timing, fee and funding arithmetic; review
tests/test_engine_user.py. Write COMPARISON.md with a verdict. Do not edit leader files.
