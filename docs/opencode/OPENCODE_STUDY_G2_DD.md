# Study A: where does G2's drawdown come from? (dev years only; read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Goal of the program (user 2026-09-30): DD ~15%, 6-7 %/month, win rate ~60%. G2 (v301: CB books + learned dip size / take-profit agents, dip budget
0.26) has dev DD 17.33 (max yearly 1m-marked DD 2021-2024), 5y 6.318 %/month. We need to know WHAT produces the drawdowns before choosing a lever.
Write only under `research/diagnostics/g2_dd/` (script, json, SUMMARY.md <= 30 lines). Do not edit leader files, engine files or registries.
LOOK ONLY AT 2021-09-24 .. 2025-09-24 (the four dev years). Never compute or print a statistic for dates >= 2025-09-24; if a helper returns
the full path, slice it before any use.

How to reproduce G2 (do not re-derive): `research/parallel/rounds/parallel-20260906-r2/v301/v301_return_first_budget.py` -> `build_hooks(eu, idx, cols)`
returns (size_s1, size_s5, tp); run `eu.simulate(cb, opens, prep, trade=dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL)), win_start=5,
events=ev, attrib=att, path_out=path, sleeve_fill_size=size_s1, sleeve_tp=tp, **dict(v221.KW, sleeve_stop_mode="close5", sleeve_backstop=8.0,
m_sleeve_sl=4.0, sleeve_risk_budget=0.26))` with cb = 0.8 x (0.5 (A+B)/2 + 0.5 (Aq+Bq)/2) + 0.2 x (D+Dq)/2 exactly as in that script's main(). The
reference must give monthly_dev4 6.527 and dev DD 17.33. `attrib` gives per-bar (t, per-asset book PnL array, sleeve PnL) as fractions of bar-start
equity; `path_out` the 4h equity / 1m-marked minimum; `events` every fill / stop / take-profit / dip rung (kinds rung_fill / rung_tp / rung_sl /
rung_timeout carry `ret`, symbol, rung).

Questions (answer with numbers, per dev year and overall):
1. List every drawdown episode deeper than 7% on the 4h close path (peak date, trough date, depth, days). For each: the sum of book PnL and of dip
   sleeve PnL inside it (fractions of equity), the coins that contributed most (book and sleeve separately), the worst single day and worst 3-day
   loss, the BTC move over the episode, the number of dip rungs filled and stopped inside it, and the share of the loss that came from the 3 worst
   trades / rung clusters.
2. Cluster analysis of dip losses: group rung_sl events by 4h bar; how many bars have >= 3 stopped rungs of different coins (systemic flush)? What
   fraction of total sleeve loss do those bars carry, and what did the sleeve earn on the OTHER bars? Same for rung_tp wins (does a flush bar also
   produce the biggest wins?).
3. Book concentration: gross and net exposure and the number of coins held long / short in each episode vs outside it; does a high same-direction
   exposure (net > x of equity) precede the episodes? Give the dev-year distribution of daily PnL when net exposure is in its top decile.
4. A counterfactual table (re-run the engine, same agents) for three SIMPLE mechanical rules, each decided with data known at the decision:
   (a) book target x 0.5 whenever the 4h realised vol of BTC (std of the last 42 4h returns) is above its trailing 540-bar 80th percentile,
   (b) the dip sleeve skips rungs of a bar once >= 3 rungs of other coins in the same bar were stopped (known at the fill minute),
   (c) the dip sleeve risk budget cut to 0.13 whenever the equity is more than 6% below its trailing 90-day peak (lag the equity by 2 bars as the
   engine's governor does).
   Report dev4, worst dev year, dev DD, dev book win rate for each; (a)-(c) must be implemented with hooks that exist (risk_mult, sleeve_fill_size,
   sleeve_filter) or with an engine copy under your own folder - never edit the leader's engine file.

Output: JSON with every number above + SUMMARY.md with a plain ranking of the levers by (dev DD reduction) / (dev4 loss). Fix the definitions above
before looking at results; log any post-hoc change.
