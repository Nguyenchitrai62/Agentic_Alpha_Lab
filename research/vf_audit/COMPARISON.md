# W9 blind-audit comparison (Part B)

Blind first: `research/vf_audit/replication.json` was saved before opening
`research_vf.py`, `vf_families.py`, `backtest/portfolio.py`, `vf_lab.py`,
`replay_hidden_year.py`, `artifacts/research/vf/`.
This file is written after reading those files plus
`artifacts/research/vf/replay/combo_733498_*` (combo fast=20/entry=55/exit=10/gate=none/w=0.5/scale=0.65).

## 1. Headline numbers (pp = percentage points)

Leader = `combo_733498_summary.json` results; Mine = `replication.json`.
DD magnitudes compared (|mine| vs leader positive).

| side | metric | leader | mine | diff (mine-leader) |
|---|---|---|---|---|
| normal | net % | 12.9822 | 12.9822108 | +0.00001 pp |
| normal | fees % | 1.0146 | 1.0145536 | -0.00005 pp |
| normal | funding % | 1.4322 | 1.4320714 | -0.00013 pp |
| normal | max DD close % | 8.819 | 8.8190087 | +0.00001 pp |
| normal | max DD intrabar % | 9.013 | 9.0130059 | +0.00001 pp |
| normal | target/position changes | 145 | 145 | 0 |
| stress | net % | 8.0979 | 8.0978839 | -0.00002 pp |
| stress | fees % | 2.9774 | 2.9773530 | -0.00005 pp |
| stress | funding % | 1.3985 | 1.3983990 | -0.00010 pp |
| stress | max DD close % | 10.2419 | 10.2419663 | +0.00007 pp |
| stress | max DD intrabar % | 10.433 | 10.4329924 | -0.00001 pp |
| stress | changes | 145 | 145 | 0 |

No difference exceeds the 0.3 pp threshold. Gross/turnover/sharpe/exposure not in
the audit spec; not compared (leader gross 15.4289/12.4737 is net+fees+funding by
construction in `portfolio.summarize_curve`).

## 2. Target-change list

- Mine: 145 decision changes; leader `combo_733498_trades.csv`: 145 rows.
- Decision-close times match exactly (145/145, `pd.to_datetime` UTC equality).
- `to_pos` matches `new_target` exactly (max abs diff 0.0).
- Only representational difference: my final change
  `2026-09-23T20:00 -> 0.0` has `trade_open_time=None` (open[2190]=2026-09-24T00:00
  lies outside the spec window, liquidated at final close 84355.1);
  leader executes it at `2026-09-24 00:00` (84355.2) and liquidates one bar later
  at `2026-09-24 03:59` close. Both end flat; price gap 0.1 on |Q|~0.3*equity/price
  is <0.001 pp. No mismatch by the spec's ">0.3pp or any target-change mismatch" rule.

## 3. Root causes of the sub-0.001 pp residuals (minimal examples)

All three are accounting proxies, not signal differences. Signals are identical
(§2), so Books T/D/target logic matches.

R1. Funding notional price: mine `Q*open[i]`, leader
`portfolio.py:52` `max(q,0)*c[i]` (close).
Minimal: Q=0.65, open=100, close=110, 1 event -> mine 0.0065, leader 0.00715.
Over the hidden year open/close avg gap is ~0.3, so total funding diff ~1e-4 pp.

R2. Fee/slippage accounting: mine deducts `fee*notional + slip*notional` from equity;
leader shifts execution price `px=o*(1+slip*sign(dq))`, charges `fee*|dq|*px`
(`portfolio.py:42-43,61-62`). Difference is fee-on-slippage.
Minimal: dq=1, o=100, fee=0.0006, slip=0.0005 -> mine cost 0.11, leader 0.05+0.06003=0.11003.

R3. Final-bar window edge (§2): mine holds `open[2189]->close[2189]` then liquidates;
leader `position_backtest(bars,tgt,s,e)` with `last=min(e+1,len-1)` holds through
`open[2190]->close[2190]`. Since final target=0 both end flat; only the 0.1 price
gap between `close[2189]=84355.1` and `open[2190]=84355.2` remains.

R4. Drawdown peak definition (no numeric effect here): leader
`portfolio.summarize_curve` peaks from closes (`[100]+eq`), intrabar DD =
`max(1-worst/peaks)`; mine interleaves `[worst,close]` with running peak.
Proof of equivalence for this strategy: for q>0 worst uses low<=close so
worst_eq<=close_eq; for q<0 worst uses high>=close with q<0 so worst_eq<=close_eq;
flat worst==close. Hence running peak over interleaved == peak over closes.

## 4. Code-path equivalence found after unblinding

- Daily ribbon: mine SMA50/200 + `(c>s50>s200)` matches
  `pattern_pipeline.daily_context` + `join_daily` (merge_asof backward on close_time).
- Book T: mine edge-triggered `hold` matches `vf_families.hold(cond, allow)` with
  `ribbon_cond(fast=20,slow=200,side=+1)` + `gate_mask(not_against)` (rib!=-1).
- Book D: mine state machine matches `vf_families.donchian(entry=55,exit=10)`:
  `hi/low` via `.rolling().max/min().shift(1)` (= previous N bars exclusive),
  long `c>hi & allow`, exit `c<=lo_exit`, short `c<lo & rib==-1` (`gate with,-1`)
  and `out[t]==0` guard (= never overlaps long), same-bar flip after exit.
- Target `0.65*(0.5*T+0.5*D)` = `combo(w=0.5)*0.65`.
- Costs: `ma_ribbon.NORMAL/STRESS` (0.0002 / 0.0006+0.0005, flat funding 0.0001 long).

## 5. Audit of `research_vf.run` for look-ahead in parameter/scale selection

No look-ahead found:

- `windows()`: `sel_end` = last bar with `open < anchor-10d`; `fwd_start` = first
  `open >= anchor`. 10-day embargo respected.
- Parameter search: `target_fn(ctx,params,fit_end=sel[1])`, scored by
  `position_backtest(bars,tgt,sel_start,sel_end,NORMAL)` (uses `target[i-1]` traded
  at `open[i]`; last holding ends `close[sel_end+1]`, still ~10d before anchor).
  Combo/trend/Donchian ignore `fit_end` and are fully causal (rolling/ewm/shift(1),
  as-of daily join). ML path `_ml_pred` trains only on labels with
  `realized+horizon < r` for refits `r<=fit_end` (`vf_families.py:224,237`); features
  from `pattern_pipeline` are causal (`diff/rolling`, `merge_asof backward`,
  `searchsorted(close_time,right)`).
- Scale: `k=floor(min(cap,0.20/sel_dd_intra)*20)/20` uses selection DD only
  (`research_vf.py:88`); forward uses `target_fn(...,fit_end=fwd_start)*k`.
- Funding precompute `funding_per_bar` assigns events to `[open_i,open_{i+1})`;
  normal mode charges `count*0.0001` (schedule is deterministic; rate not used for
  decisions). No decision consumes future bars.

Caveat (not a finding): `run()` default `anchors=HIDDEN_YEAR=("2025-09-24",)` with
`select_years=None` means selection uses all data from `bars[0]+60d` to anchor-10d;
that is allowed (all before embargo), not look-ahead.
