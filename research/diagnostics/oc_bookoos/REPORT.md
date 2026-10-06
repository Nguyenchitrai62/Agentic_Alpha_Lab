# oc_bookoos — REPORT (clean OOS, tiny sample)

Window 2026-09-30 00:00 .. 2026-10-06 00:00 UTC (6 days, genuinely new; research ends 2026-09-23).
Mode: **full G2 book+dip, rule-based** (prospective 0.8×O1+0.2×CB books; no agents, no bear, no refit).
Why honest: frozen members end 2026-09-23; the deployed book is rebuilt ONLY from
logged prospective member rows (v240_O1 + v285_CB, mode=prospective, lag<=6h, valid
weights; 34 common t, 6 backfill-only gaps forward-filled = hold last target).
First-bar check: O1-t from 09-28 16:00, CB-t from 09-29 16:00, first common
2026-09-29 16:00; the first traded holding bar 2026-09-30 00:00 needs t=09-29 20:00,
which exists for both (prospective, lag<=6h) — scoring starts at that midnight
for clean daily equity. No backfill rows used as evidence (asof+prospective within
6h included as forward evidence per advisor_shadow.py; mode=backfill excluded).
Engine: `engine_user.simulate`, 4 clock shifts, v321 dip rules + G2 overlays
(inv corr kd=1.7, budget 0.26×1.7, gross cap 2.0), gate costs (maker 0.0002 /
taker 0.00055 / long funding 0.0001 per settlement / shorts 0), `win_start=5`,
stop-first. Agents OFF (R2/G2 tables end 2026-09-23, no OOS rows; size 1.0,
default TP); bear halving OFF (live-paper form, as forward_trade v285/v321_R2).
1m from Binance vision daily zips (CHECKSUM-verified, `data/raw/majors_1m_oos_20261006/`,
reused/extended oc_oos12d fetcher; 8640 bars/symbol over the 6d window, gap-free).

## Result (4-phase mix, per reset-metric convention)
- Daily equity (7 closes 09-30..10-06): 1.004602 → 1.019945; total **+1.995%**.
- Max DD: close 0.128%, 1m-marked 0.766%, gate **0.766%**.
- Trades (pooled over 4 phase sub-accounts): **10 rung exits, 9 wins, win 90.0%**;
  book fills 12 events (3/phase) but **0 completed book episodes** (positions still
  open at the window end, so book/all-trade win = rung win; all 10 wins 90.0%).
- Expectation band (10000 random 6-day windows, v421 G2 mixed daily):
  p5 −3.309%, p50 +0.466%, p95 +7.477%; OOS **percentile 72.7** (above median,
  inside the band). Median 6-day DD band p50 0.832% / p95 5.32% vs OOS 0.766%.
- verdict: inside the historical band on a tiny sample; **no gate claim**
  (6 days cannot pass/fail 5%/month). First clean full-book OOS leg (dip-only
  oc_oos12d was +0.187% over 12d with books=0).

## Reproduce (weekly, one command)
`.venv/Scripts/python.exe research/diagnostics/oc_bookoos/score_oos.py --fetch --run`
(no-fetch: `--run` fails loudly if the manifest is stale); `.venv/Scripts/python.exe -m pytest tests/test_oc_bookoos.py -q`.
