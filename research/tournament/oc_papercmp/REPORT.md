# oc_papercmp — paper evidence comparison (REPORT)

Snapshot: single tool run at 2026-10-05T13:11:27Z (live bot files keep updating;
plan window starts 2026-10-04 08:00 UTC, bots start 2026-10-05 04:00 / 12:00 UTC).
Tool: `scripts/paper_compare.py` -> `artifacts/research/paper_compare.json`
(identical copy: `results.json`); driver: `compare.py`; test:
`tests/test_oc_papercmp.py` (3 synthetic tests pass). No market/1m data loaded.

## Per-source equity (hourly curve since start)

| source | window (UTC) | pts | return % | max DD % |
|---|---|---:|---:|---:|
| paper (R2-4P bot) | 10-05 04:00 -> 10-05 13:00 | 10 | +0.0158 | 0.0301 |
| paper_d18 | 10-05 12:00 -> 10-05 13:00 | 2 | +0.0000 | 0.0000 |
| plan_v376 | 10-04 08:00 -> 10-05 16:00 | 33 | +0.0971 | 0.1454 |

## Fills by kind + pieces

| source | book_entry | dip | tp | stop | market_exit | execs | pieces (total/closed) | win rate |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| paper | 2 | 0 | 0 | 0 | 0 | 2 | 2 / 0 | n/a (no closes) |
| paper_d18 | 0 | 0 | 0 | 0 | 0 | 0 | 0 / 0 | n/a (no closes) |
| plan_v376 events | 8 (`book_fill`) | 0 | 0 | 0 | 0 | — | — | — |

Runner actions: paper `place=306 fill=2 cancel=225 cycle_error=15`;
paper_d18 `place=100 amend=3 cancel=25 cycle_error=1` (incl. one Bybit 10006 rate-limit).
Costs: paper `fees=0.0685 funding_paid=0.0345`; d18 zero; plan is pre-cost (indexed 1.0).

## Divergence: R2-4P bot (paper) vs plan_v376

Return gap: **-0.0813pp** (bot +0.0158% minus plan +0.0971%).

| symbol | bot entries | plan fills | matched | only in bot | only in plan |
|---|---:|---:|---:|---:|---:|
| BNBUSDT | 0 | 4 | 0 | 0 | 4 |
| BTCUSDT | 2 | 4 | 2 | 0 | 2 |

Bot filled the 2 BTC book entries also present in the plan (04:22 UTC pair);
all 4 BNB plan fills and 2 earlier BTC plan fills (10-04) predate / are absent
from the bot window — no bot-only fills. Link-id spaces are disjoint by
construction, so reconciliation is per-symbol min-matched counts.

## Caveats
Windows differ (plan covers 10-04, bots start 10-05); win rate is undefined with
zero closed pieces (entries only, exits pending); live logs moved during the run.

## Verdict
VERDICT: R2-4P bot trails the plan by 0.08pp with 2/2 BTC entries filled, zero exits closed (win rate n/a), and 6 unmatched plan fills — entries track, closes pending.
