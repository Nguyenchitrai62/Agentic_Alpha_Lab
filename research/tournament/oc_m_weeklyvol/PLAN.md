# oc_m_weeklyvol PLAN (pre-registered, frozen before any outcome, 2026-10-08)

IDEAS9 #5 (docs/opencode/IDEAS9_20261008.md): Weekly-frozen vol distance
table (slow-adaptive brackets) on the MANUAL product. Assignment
docs/opencode/OPENCODE_W_oc_m_weeklyvol.md + common header
docs/opencode/OPENCODE_W_COMMON_20261007.md + AGENTS.md + OPENCODE_VF_COMMON.md.

MANUAL = book + bracket dip limits with native TP/SL + book, 15-min reaction,
night bar skipped (M5_human 5y 3.728 %/mo, DD 17.94, ~1.272 pp short of the
5 % floor). Mech: fixed-sigma brackets misprice when vol regimes shift, but
per-bar rescaling = re-pegging a human cannot do. A Sunday printed table is
followable. Prior 8 %. Effect pre-registered by the idea: +0.0-0.08 %/mo via
fewer stop-cluster fills, DD flat.

## Reference (must reproduce exactly or STOP)

M5_human = deployed MANUAL M5 (v367) on the human schedule, exactly as
research/diagnostics/manual_human/manual_human.py runs it and as scored in
research/diagnostics/oc_manualcap (reset metric + v388.mix full-path DD),
copied as oc_manualsplit / oc_k2manual / oc_c2manual / oc_m_btceth /
oc_m_conflict / oc_m_top2 did (same harness lines, this study copies
oc_m_conflict's harness exactly and changes ONLY the sigma input below):
- pipe v367 via pof.pipe_setup (book_mult 0.75, tighten on flat-signal
  losers, M3_R2_RUNG mapped agents ON with per-phase v376/tables_hidden R2
  tables; sleeve_risk_budget 0.26, m_sleeve_sl 8.0, size_mult 4.375,
  rungs (3.0, 4.0); no gross cap; book SL 5.0 / TP 10.0 sigma_d).
- human schedule on EVERY row: 15-min reaction (book orders from minute 15
  via win_start=15, dip limits from minute 16 via sleeve_start=16) + night
  bar skipped: on the holding bar starting at (20+s) UTC no new book order
  (flat -> wait, in position -> hold) and no new dip limit
  (sleeve_filter 0); resting orders, SL, TP stay on the exchange.
- gate costs maker 0.0002 / taker 0.00055, longs pay 0.0001 per 8h
  settlement, shorts nothing; limit fills only on 1m trade-through, no fill
  minutes 0..15 (stricter than the minute-5 user rule); stop-first if
  SL+TP touch the same 1m bar; dip exits: TP limit (maker) / touch stop
  8.0sg market (taker) / timeout at next 4h open (taker).
- Bybit order types (idea #5): GTC limit price from the printed table +
  attached TP/SL (OCO-like pair), reduce-only SL; a human places them once
  per bar from the Sunday table, no re-pegging; checklist a few times/day.
- 4 phases s=0..3, live window [2021-09-24+sh, 2026-09-23+sh), anchors
  2021-09-24..2025-09-24 (+sh per phase), each year [a0, min(a0+365d,
  live1)).
- scoring: reset_metric.year_reset per anchor + v388.mix full-path DD
  (v421/v422 convention); per-year %/month, yearly DD, full-path DD, win
  rates (book episodes via v213.trade_stats dev+_hidden, dip rung exits
  via ret>0 on rung_tp/sl/timeout, all = book+dip), trade counts.
- reproduction gate: this study's M5_human rerun must be BIT-EXACT vs
  research/diagnostics/oc_manualcap/oc_manualcap_runs.pkl
  (max abs d(eq,eq_min) <= 1e-12 over 4 phases) AND equal
  R5 3.728 / W 0.847 / maxDD 17.94 / fullDD 17.79 / book_win .6482.
  Else STOP and report the mismatch (no V1/V2 numbers are used).
- NOTE on the common header G2 line: this assignment is the MANUAL
  product, so the reference is M5_human (3.728 / 17.94 / 17.79), NOT the
  BOT G2 baseline. Everything else in the common header applies.

## Weekly-frozen sigma (frozen ex-ante, no refit)

sigma360 = the engine's own sigma_4h estimator: std of 4h open-to-open
pct returns over the trailing 360 bars (min_periods 120), exactly the
sig4 array pof.prep_idx builds (phase_offset_full.py line 71). For a
holding bar opening at T = idx[i]+4h on phase shift s, let SUN(T) be the
most recent Sunday 00:00 UTC <= T. The frozen sigma is sig4[jw, a] where
jw = max j with idx[j]+4h <= SUN(T) (the last bar whose holding-bar open
is at/before the Sunday print; its sig4 uses opens with index <= jw, i.e.
closes <= Sunday close minus 4h, strictly causal). One printed table per
week (same Sundays on all phases; per-phase jw differs only by the shift
grid, disclosed). Fallback (frozen): no jw yet, or sig4[jw,a] NaN
(warmup), or sig4[i,a] NaN -> use the per-bar sig4[i,a] (identical to
M5_human on those bars; counted in the fallback-rate diagnostic).
Table versioned per week: the week_start (Sunday 00:00 UTC date) + the 5
frozen sigmas are logged per phase in results.json (n_weeks, per-year
freeze rate, mean |frozen/per-bar - 1|, fallback rate).

k / distances frozen (manualshallow depths, never refit, idea leak note):
dip rungs (3.0, 4.0), dip SL 8.0, dip TP mults from the deployed R2 tables
(bar-open lookup, unchanged), dip risk budget 0.26 with gap 0.02
(unchanged, budget counts the frozen stop distance), book SL 5.0 / TP 10.0
sigma_d with sigma_d_week = sigma_week*sqrt(6), book entry pullback 0.75
sigma_4h_week (min_off 0.001 unchanged), tighten/add offsets use the same
weekly sigma (they are SL/limit distances from the same table).
Implementation: V1/V2 replace the whole prep sig4 array with the weekly
array (sig_sl defaults to sig4, so dip lv/TP/SL + budget, book
entry/SL/TP/tighten/scales all use weekly; vol target s[i], governor,
R2 size/TP mults, books, schedule untouched). No intraday recompute: the
frozen value is fixed for all T in [Sunday 00 UTC, next Sunday 00 UTC).

## Pre-registered rows (ONLY these, no other variants)

- M5_human (reference, per-bar sig4, unpatched eu.simulate; identity filter
  line identical to oc_k2manual / oc_m_conflict).
- V1_WEEKLY: weekly-frozen sigma as above, no rounding.
- V2_WEEKLY5T: weekly-frozen sigma as above + every sigma-derived price
  rounded to the nearest 5-tick grid (frozen Bybit-style ticks: BTCUSDT
  0.10, ETHUSDT 0.01, SOLUSDT 0.01, BNBUSDT 0.10, XRPUSDT 0.0001; i.e.
  steps 0.50 / 0.05 / 0.05 / 0.50 / 0.0005). Rounded: dip lv/tp/sl at
  ladder placement; book entry limit px, SL/TP at placement/fill; tighten
  SL moves; scale-order (add/reduce) limits. Patched simulate via the
  audited inspect.getsource pattern (cf. oc_m_breakeven make_be_simulate):
  each anchor asserted exactly-once, rounding helper _r5 uses only the
  computed price + frozen tick (no minute/fill/future data).

Closest CLOSED (disclosed, not this idea): oc_manualshallow (FIXED shallow
rungs, best 3.73) never adapts sigma; oc_bookoffset (per-BAR vol offset;
trade-mode already sigma-scaled) re-pegs every bar, which a human cannot
do; this is SLOW (weekly) vol-adaptive distance, neither fixed nor per-bar.

## Selection (AGENTS.md robust criterion, dev years ONLY)

Compare V1 vs V2 ONLY on dev years 2021-2024 (anchors 2021-09-24..2024-09-24):
eligible = DDdev4 <= 20 and no losing dev year; prefer dev4 mean >= 5
%/month if any; among the pool pick the highest dev4 WORST-year monthly;
ties -> higher dev4 mean. If neither is eligible, PICK = none-eligible.
The most recent year 2025-09-24..2026-09-23 is scored ONCE, only for the
chosen variant (and M5_human), labelled POST-RELEASE, never used to choose.
Single frozen 4-phase pass over the full 5-year window (oc_k2manual /
oc_m_btceth precedent): the non-pick's last-year row is shown for
completeness from the same pass only, never used for any decision and not
re-scored. If anything changes after seeing an outcome, the original row
stays and the change is added as a disclosed extra row (not planned).
5-year R5/W/maxDD/fullDD are context only. Verdict question: how much of
the MANUAL gap to 5 %/month (M5_human R5 3.728, gap 1.272 pp) does the pick
close?

## Leakage audit (to be stated in REPORT.md)

- feature timing: weekly sigma for week [Sun, Sun+7d) uses only sig4 at
  jw with T_jw <= Sunday 00 UTC (opens with index <= jw, i.e. closes <=
  Sunday close; causality test bans 1m/minute/fill markers and future
  opens in the builder; synthetic tests check Sunday-boundary freezing and
  the fallback rule); R2 size/TP tables keyed by holding-bar time T
  (bar-open lookup only); V2 rounding uses only the computed price + frozen
  tick; no 1m data enters any placement decision.
- label windows: no new labels; no outcome enters any distance/table rule.
- fit windows: no fits/thresholds/quantiles of any kind; k frozen ex-ante
  (3.0/4.0, 8.0, 5.0/10.0, 0.75), ticks frozen ex-ante, Sundays are the
  public calendar; no statistic from any test year feeds any choice.
- fill timing: no fill minutes 0..15 (win_start=15 books, sleeve_start=16
  dips, stricter than the minute-5 user rule); limits fill only on 1m
  trade-through; stop-first on same-bar SL+TP touch; dip timeout at next
  4h open; weekly table never recomputed intraday.

## Outputs

research/tournament/oc_m_weeklyvol/{PLAN.md,compute_m_weeklyvol.py,
results.json,REPORT.md,tmp/} + tests/test_oc_m_weeklyvol.py only.
results.json: per-row years_R/years_DD/book wins/rung wins/fills,
R5/W/maxDD/fullDD/Rdev4/Wdev4/DDdev4/losing_dev4/Rlast, pick + eligibility,
costs, baseline, weekly-freeze diagnostics (n_weeks, freeze/fallback
rates), tick table. REPORT.md ends with a 3-line Vietnamese verdict
(adopt / reject / needs prospective evidence) + one-line MANUAL-gap verdict
with gap in pp. MANUAL gate: R5 >= 5 %/month AND fullDD < 20 AND pooled
book win >= 55 %. Heavy run in ONE heavy_slot process (tag oc_m_weeklyvol),
heartbeat progress at least every 10 minutes, nohup + log under tmp/.
