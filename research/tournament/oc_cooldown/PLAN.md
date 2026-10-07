# oc_cooldown PLAN (pre-registered BEFORE any outcome is computed, 2026-10-05)

Implements idea #11 ("per-coin dip COOLDOWN after a stop-out") EXACTLY as
described in docs/opencode/OPENCODE_W_oc_cooldown.md. This PLAN is written
before any cooldown outcome is computed.

## Hypothesis

oc_ddanat17 (research/tournament/oc_ddanat17/REPORT.md) shows the big D17BF
drawdowns are dip stop cascades and stop-vs-TP churn concentrated in ONE coin
per episode (FTX SOL 2022-11: dip sleeve -8.89 with rung_sl -19.75 vs rung_tp
+16.18; 2023-04/06: rung_sl -12.72; 2024-06/09 XRP dip -11.81; 17 of the 20
worst rungs are XRP stop-outs, fastest cluster 2024-06-07 fills 18:00/18:01
-> stop 18:05). After a coin's dip rung stops out, the same coin keeps
refilling into the same flush and stopping again within hours. Suppressing new
dip bids of that coin for 24h after each stop-out should cut the cascade tail
(maxDD of the dip daily-sum path) while giving up little yearly sum, because
kept rungs (TPs/timeouts) dominate the rung population (2868 TP vs 176 stops).

## Universe, data, years (fixed)

- Ledger (checked, no outcome computed): `research/tournament/oc_ddanat17/
  rungs_s0.parquet` (5466 dip rungs, s=0 engine replica of R2B1D17BF) HAS
  per-rung stop exit times: columns (fill_t, exit_t, symbol, depth, exit,
  weight, ret, loss, fill_price, exit_price, n, fill_min, bar_start) with
  exit in {rung_sl (176), rung_tp (2868), rung_timeout (2422)}; all rung_sl
  rets are negative (mean -7.6%). `events_s0.parquet` confirms rung_sl events
  carry minute exit times. This satisfies the assignment's "check and
  document" for the rung_s0+events source option.
- Source choice: use rungs_s0+events (actually-traded BOT rung stream under
  R2B1D17BF s=0, exact engine weights/sizing, no 1m read). REJECTED:
  (a) re-running the oc_dipexit stop replica (needs 1m reads; heavier than
  the LIGHT budget when rungs_s0 already carries exact stop times);
  (b) fills_U_ext.parquet (no exit-kind column, 7-depth grid r0..r6, cannot
  identify stops without 1m).
- Universe: majors (BTCUSDT/ETHUSDT/SOLUSDT/BNBUSDT/XRPUSDT) x R2 depths
  {2.5, 3.0, 3.5, 4.0} (v293 RUNGS = R2 rung grid; see
  v293_pooled_exit_agent.py line 50). The 304 depth-5.0 rungs in rungs_s0
  (oc_dipexit extra rung / engine fills) are EXCLUDED from triggers and from
  scoring; the excluded count is reported.
- Rung P&L: loss = weight*ret (fraction of bar-start equity, engine-sized,
  fees/funding included by the engine). Win = ret > 0 strictly.
- Years: 5 anchor years Y0..Y4 = bars with bar_start in [anchor, anchor+365d)
  for anchors 2021-09-24..2025-09-24 (same anchors as the assignment; keyed by
  bar_start, the trading decision time). Engine-live coverage starts
  2021-10-15 (documented warmup truncation of Y0).
- Market data up to 2026-09-24 00:00 UTC per assignment (all 5 years are
  research data; a PROMISING cooldown still needs prospective validation
  before real money). Disclosed vs RULES.md hidden-year convention.

## Exact causal rule (frozen, single value 24h, no grid)

- Per coin c, stop set S_c = {exit_t of universe rungs with symbol == c AND
  exit == 'rung_sl'} (close-stop and 8-sigma backstop are merged into rung_sl
  by the engine; both count as stops per the assignment).
- A universe rung of coin c with holding-bar open B is COOLED (removed) iff
  there EXISTS s in S_c with B in (s, s + 24h] (strictly after the stop,
  up to and including +24h). Bar opens exactly at s are NOT removed.
- Causality: the decision for bar B uses only stop exits completed strictly
  before B. No lookahead: stops at/after B never suppress B.
- "Rungs already resting keep their order": removal is keyed on BAR OPEN, so
  fills later in the same bar as a stop (bar open B <= s) are kept, and
  in-flight rungs filled before a stop keep their outcomes. Kept rungs keep
  their engine weights (no budget redeployment; disclosed approximation).
- Counterfactual paths per year: baseline = all universe rungs; cooldown =
  kept rungs only. Daily sums group loss by EXIT date (UTC); cumulative curve
  starts at 0 within each anchor-year exit window [anchor, anchor+365d);
  worst_day = min daily sum; maxDD = min(cumsum - running_max) (<= 0).
  Full-period row for context only.

## Statistics (fixed, no fitting)

Per anchor year report: n_total, n_removed, n_kept; sum_base, sum_cool,
sum_removed (= sum_base - sum_cool); win rate kept vs removed (ret > 0);
worst_day and maxDD of the daily-sum path with/without cooldown.
Full-period aggregates for context (not scored).

## Decision rule (fixed, assignment-specific)

- PROMISING only if BOTH hold:
  (a) cooldown maxDD improves (DD_cool > DD_base strictly, tolerance 0) in
      >= 4 of 5 anchor years, AND
  (b) the yearly sum falls by < 10% in >= 4 of 5 years, where "falls by <10%"
      means: if S_base > 0 then S_cool >= 0.90 * S_base; if S_base <= 0 then
      S_cool >= S_base (must not lose more).
- This replaces the default same-sign/LOO rule (the assignment pre-specifies
  this maxDD + sum-retention rule for idea #11). One-line verdict in REPORT.md
  (PROMISING / NOT PROMISING).

## Protocol / resources (fixed)

- PLAN.md written before any outcome computation. One process, parquet-only
  (rungs_s0 + events check), no 1m read, RAM < 1 GB.
- No commits; write ONLY under `research/tournament/oc_cooldown/`
  (+ `tests/test_oc_cooldown.py`).
- Scripts: `run_cooldown.py` (filter + per-year stats -> results.json);
  outputs `results.json`, `REPORT.md` (tables + one-line verdict).
