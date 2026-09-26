# v171 blind audit - HIGH PRIORITY, be adversarial (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v171_audit/` and `tests/test_v171_audit.py`.
Do NOT open v171/ until part A is saved (`replication.json`). The leader result looks unusually good (sleeve alone
+8..+65%/year, DD 7-9%), so the main job is to find any bug, look-ahead or unrealistic fill. Implement independently
(do not import v169/v171 code; you may import engine_real for `v154_books`, `context`, `funding_at_bar_open`, constants,
and your own audited engine replication).
A (sleeve): symbols BNB/BTC/ETH/SOL/XRP USDT perps. Decision grid t = 4h bars from 2020-02-01 00:00 UTC to the last
books bar; holding bar T = t + 4h. 4h opens from `data/raw/xs_universe_20260924/<SYM>_4h.parquet`. sigma(t) = std of
4h open-to-open pct changes over the 360 bars ending at t (min 120). 1m klines: BTCUSDT `data/raw/btc_intraday_20260924/
klines_1m_20*.parquet`, others `data/raw/majors_intraday_20260924/<SYM>_1m_20*.parquet` (drop duplicate open_time;
forward-fill missing minutes within the 4h bar). Event for (t, sym): first minute offset m in 16..238 of T whose 1m
close / open(T) - 1 <= -k sigma(t). Entry = open of minute m+1 * 1.0002; exit = open of the next 4h bar (T + 4h)
* 0.9998; r = exit/entry - 1 - 0.001 - funding rate settled at T + 4h (sum of fundingRate floored to 4h). k per anchor
from (2, 2.5, 3, 3.5, 4) maximising mean/std of the per-bar sleeve return 0.25 * sum_sym r (0 without event) over
[2020-02-01 + 30 d, anchor - 1 d]; applied to [anchor, anchor + 365 d). Report per anchor: k, net %, DD %, events.
A (combined): engine_real loop (target 0.25, 20% governor with the 2-bar lag, all realism, 15-minute execution) with
net[i] += g[i] * sleeve[i] on live bars; must give baseline 3.708 / 18.87 without the sleeve. Report monthly, yearly,
full-path DD. Save `replication.json`.
B: compare with `v171/v171_result.json` and `v171/v171_robustness.json`. Then adversarial checks, each with numbers:
(1) any use of data after the entry minute in the trigger or sigma; (2) alignment of the 1m minute offsets with the 4h
open (is minute-0 open == 4h open?); (3) duplicated/bad 1m bars or price spikes (report the 20 largest event returns
with timestamps and check them against the raw 1m rows: are they real market moves (e.g. known crash dates) or data
errors?); (4) whether the entry price is actually tradable (volume in minute m+1 > 0; entry within that minute's
high/low); (5) sensitivity: exit at T + 4h + 15 minutes instead of the 4h open. Write COMPARISON.md with a verdict.
Do not edit leader files.
