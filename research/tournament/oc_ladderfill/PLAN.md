# oc_ladderfill PLAN (pre-registered BEFORE any outcome is computed)

DIAGNOSTIC task (no PROMISING rule, no verdict). Question: how often and how
fast are dip rungs filled, and how much of the dip edge comes from the first
minutes after a fill?

## Data (fixed here)

- Source: `research/tournament/oc_kpi/events_s{0..3}.parquet` (R2B1D17BF
  replicas, shifts s=0..3, majors BTC/ETH/SOL/BNB/XRP, live 2021-09-24..
  2026-09-23). Only `rung_fill` rows (depth in `rung` = 2.5/3.0/3.5/4.0/5.0,
  `weight`) and rung exits (`rung_tp` / `rung_sl` / `rung_timeout`, net `ret`).
  Pooled over the 4 shifts (each shift = 1/4-capital sub-account; counts are
  summed, rates are pooled).
- Market data up to 2026-09-24 00:00 UTC may be read (assignment overrides the
  old RULES.md hidden-year cut; all five years are research data; any finding
  needs prospective validation). No refit, no selection, no tuning.
- Resources: ONE process, pandas only, no 1m data, RAM < 1 GB.

## Exact causal definitions (fixed)

1. Pairing: FIFO per (shift, symbol) in time order — exact copy of
   `oc_kpi/compute_kpi.py::pair_rungs`. Depth/weight/fill_t come from the
   `rung_fill` row; `ret`/exit-kind/exit_t from the matched exit row. Unpaired
   fills/exits are counted and reported (expected ~0 + live-open at the end).
2. Fill minute `f` = minutes from the rung's own holding-bar open: the
   shift-s replica runs on the 4h grid offset by s hours (bars open at hours
   = s mod 4); `f = ((minutes since midnight) - 60*s) mod 240` (integer; 1m
   resolution). Expected range 16..238 (win_start=5 + engine limits); any value
   outside is reported, not dropped.
   CORRECTION LOG (before REPORT, after first script run): v1 of this line
   said bars open at 00/04/08/12/16/20 UTC for all shifts; the first run then
   showed f in 0..239 with 1564/21389 outside 16..238 on s=1..3 only. Cause:
   missing per-shift grid offset. Fixed to the formula above; re-run gives
   exactly 16..238 on every shift (0 outsiders). Pooled win rate / mean ret
   (grid-independent) unchanged.
3. Time to exit `dt` = `exit_t - fill_t` in minutes (float; integer-valued).
4. P&L per rung = engine `ret` (already net of rung maker/taker fees; timeout
   funding included). Per group report: n, win rate (`ret > 0`), mean ret in
   bps (1 bps = 1e-4), sum(ret) (equal-weight edge), sum(weight*ret)
   (capital-weighted contribution). "Share of the dip edge" = group
   sum(weight*ret) / total sum(weight*ret) (main) with the sum(ret) share as
   secondary.
5. Fill-minute buckets (fixed, cover 16..238): 16-60, 61-120, 121-180,
   181-238.
6. Fast-TP sets (nested, cumulative): rung exits with `exit == rung_tp` AND
   `dt <= 5` / `dt <= 15` / `dt <= 60` minutes.

## Tables (fixed)

- A. Fill-minute distribution: per depth and per coin: n, share, median/p25/p75
  of f; overall histogram over the four buckets.
- B. Time to exit by exit kind: per depth and per coin: median/p25/p75/mean of
  dt for tp / sl / timeout separately (+ overall).
- C. P&L by fill-minute bucket: per bucket (pooled + per depth): n, win rate,
  mean bps, sum(ret), sum(weight*ret), edge share.
- D. Fast-TP P&L: per horizon (5/15/60): n, share of all rungs, share of TP
  rungs, win (=100% by construction for TP — reported as check), mean bps,
  sums, share of total dip edge and of total TP edge.
- E. Paper bots: read `artifacts/bot/paper_d17bf/actions.jsonl`,
  `exchange.json` (plus `state.json` for order context; paper since
  2026-10-05, prospective data, reported separately): list every dip/book fill
  so far with the research engine's expectation where comparable (just counts
  if too few).

## Outputs (fixed)

- Script `analyze_ladderfill.py` (this plan's definitions, no 1m reads).
- `results.json` (all tables above + pairing checks + paper-bot counts).
- `REPORT.md` (tables + one-line descriptive summary; NO rule verdict).
- Test `tests/test_oc_ladderfill.py` (causal pairing/f-minute checks +
  results.json schema/expectation cross-checks).
