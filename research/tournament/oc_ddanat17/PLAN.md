# oc_ddanat17 PLAN (pre-registered BEFORE any outcome is computed, 2026-10-05)

## Hypothesis
The five largest drawdown episodes of the deployment pick R2B1D17BF (registry v411:
dips x1.7 inv-rule, budget 0.26x1.7, bear-book filter longs x0.5) on phase s=0 are
dominated by the dip sleeve (correlated stop-outs / timeouts in cascades), not by the
book. Per-episode anatomy (book-long vs book-short vs dip, per coin) plus the 20 worst
dip rungs identify the mechanism.

## Exact causal replica (R2B1D17BF, phase s=0 only)
- Grid: standard 4h decision index from eu.er.v154_books() shifted by 0h; holding bar
  i covers [idx+4h, idx+8h); prep via phase_offset_full.prep_idx on pod.minutes()
  (float32 cube, sig4 = pct_change().rolling(360,min120).std, settle flags).
- Books: fw.research_books_d2(eu) (BOT book) ffill on idx; bear filter: rows where
  BTCUSDT standard open < rolling-1200 mean (min 600) have positive entries x0.5.
- Dips: pipe_setup("v321", ...) WITH R2 agents (r2_table_s0.parquet size/TP lookup);
  corr_size inv-rule kd=1.7: at fill minute f of asset a, n = #{b != a:
  C[i,m,b] <= O[i,0,b]*(1-2.5*sg[i][b])}, mult = 1/(1+n); size = mult*1.7*base_size;
  risk_mult k=1.0; sleeve_risk_budget = 0.26*1.7; trade = v216 grid policy
  (no M-series overrides). eu.simulate(..., win_start=5, events=[], attrib=[],
  path_out={}, bars=[]) — one process only.
- Window: live [2021-09-24, 2026-09-23+12h) (v411 Y1+12h mix end); 1m read to
  2026-09-24 00:00 UTC. All five years are research data (assignment override of
  RULES.md hidden-year rule); findings need prospective validation. No refit, no
  selection, no tuning.
- Costs: book entries/TP maker 0.0002, stops taker 0.00055; rung fills/TP maker,
  stops/timeouts taker; adverse long funding 0.0001 per settling bar (gate rule).

## Drawdown + attribution definitions (fixed before running)
- Equity: 4h-close eq from path_out restricted to live; peak-to-trough episodes:
  running peak; each new max-DD (trough below all prior in live) is an episode
  (peak time, trough time); take the FIVE deepest non-overlapping episodes by
  1 - trough/peak (report also 1m-marked depth from eq_min for reference).
- Per-episode P&L: attrib rows with t in (peak, trough]: book[a] = sum of per-asset
  book fractions (bar-start equity units, converted to episode-equity-fraction via
  compounding check vs eq); sleeve = sum of sleeve fractions. Book long/short split:
  sign of the episode-start book target weight for (bar, asset) — books_bear value
  >0 -> long bucket, <0 -> short bucket, ==0 -> excluded (cash). Per-coin table =
  book coin sums + dip coin sums (dip per coin from rung exit events in window).
- Dip rungs: paired rung_fill -> rung_sl|rung_tp|rung_timeout events; loss =
  weight*ret (fraction of bar-start equity); n = B1-rule count recomputed at the
  fill bar (same inv formula, m = f-1, NaN-guarded); depth = rung k in
  {2.5,3.0,3.5,4.0} (rungs[r]); exit kind = exit event kind. Rank by loss ascending;
  top 20 reported (exit t, coin, n, depth, exit kind, loss, fill t).
- Cross-checks: attrib sums vs eq move per episode (tolerance 2%); event count vs
  stats (rungs); s=0 equity end vs v411_runs.pkl s=0 R2B1D17BF end (tolerance 1%).

## Decision / verdict rule
- Descriptive verdict per episode: the component (book-long | book-short | dip)
  with the largest loss share (>50% = "dominates", else "mixed") and the mechanism
  (dip stop cascade / dip timeout bleed / book long drawdown / book short squeeze /
  mixed), plus which coins drive it.
- Default tournament rule (for any PROMISING claim): PROMISING only if the named
  effect has the same sign in >= 4 of 5 anchor years (2021-09-24..2025-09-24, +365d)
  AND holds leave-one-year-out in >= 4 of 5. This anatomy makes no PROMISING claim;
  the one-line verdict names the dominant component/mechanism per episode.

## Outputs
- scripts: run_ddanat17.py (single heavy process); results.json (episodes, per-coin,
  worst-20 rungs, checks); REPORT.md (tables + one-line verdict). Test:
  tests/test_oc_ddanat17.py.
