# oc_manualveto PLAN (pre-registered, frozen before any run, 2026-10-08)

IDEAS5 #8 (20261008): MANUAL volatility veto of new bracket placement.
Assignment docs/opencode/OPENCODE_W_oc_manualveto.md + common header
docs/opencode/OPENCODE_W_COMMON_20261007.md + AGENTS.md. CLOSED rows read:
oc_manualcap / oc_manualshallow / oc_manualsplit / oc_manualrest /
oc_k2manual (K2 +0.112 of 1.272 gap, timing +0.249 too small),
oc_ladderfill (8% stops erase ~50 TPs each, stops cluster in expansion
bars). None vetoed PLACEMENT on volatility; this study is the distinct
placement-veto cell. TP/stop distances frozen (H1 0.75/1.5 family NOT
revisited). No new signal, no re-peg, no churn.

## Reference (must reproduce exactly or STOP)

M5_human = deployed MANUAL M5 (v367) on the human schedule, exactly as
research/diagnostics/manual_human/manual_human.py runs it and as scored
in research/diagnostics/oc_manualcap (reset metric + v388.mix full-path
DD), copied as oc_manualsplit / oc_k2manual did (same harness lines):
- pipe v367 via pof.pipe_setup (book_mult 0.75, tighten on flat-signal
  losers, M3_R2_RUNG mapped agents ON with per-phase v376/tables_hidden
  R2 tables; sleeve_risk_budget 0.26, m_sleeve_sl 8.0, size_mult 4.375,
  rungs (3.0, 4.0); no gross cap; book SL 5.0 / TP 10.0 sigma_d).
- human schedule on EVERY row: 15-min reaction (book orders from minute
  15 via win_start=15, dip limits from minute 16 via sleeve_start=16) +
  night bar skipped: on the holding bar starting at (20+s) UTC no new
  book order (flat -> wait, in position -> hold) and no new dip limit
  (sleeve_filter 0); resting orders, SL, TP stay on the exchange.
- gate costs maker 0.0002 / taker 0.00055, longs pay 0.0001 per 8h
  settlement, shorts nothing; limit fills only on 1m trade-through, no
  fill minutes 0..15 (stricter than the minute-5 user rule); stop-first
  if SL+TP touch the same 1m bar; dip exits: TP limit (maker) / touch
  stop 8.0sg market (taker) / timeout at next 4h open (taker).
- 4 phases s=0..3, live window [2021-09-24+sh, 2026-09-23+sh), anchors
  2021-09-24..2025-09-24 (+sh per phase), each year [a0, min(a0+365d,
  live1)).
- scoring: reset_metric.year_reset per anchor + v388.mix full-path DD
  (v421/v422 convention); per-year %/month, yearly DD, full-path DD, win
  rates (book episodes via v213.trade_stats dev+_hidden, dip rung exits
  via ret>0 on rung_tp/sl/timeout, all = book+dip), trade counts, veto
  rates per year (diagnostic only).
- reproduction gate: this study's M5_human rerun must be BIT-EXACT vs
  research/diagnostics/oc_manualcap/oc_manualcap_runs.pkl
  (max abs d(eq,eq_min) <= 1e-12 over 4 phases) AND equal
  R5 3.728 / W 0.847 / maxDD 17.94 / fullDD 17.79 / book_win .6482.
  Else STOP and report the mismatch (no V1/V2 numbers are used).
- NOTE on the common header G2 line: this assignment is the MANUAL
  product, so the reference is M5_human (3.728 / 17.94 / 17.79), NOT the
  BOT G2 baseline. Everything else in the common header applies.

## Veto signals (frozen, causal, no fitting)

Price source: existing 1m klines only (no new data):
BTC data/raw/btc_intraday_20260924/klines_1m_20*.parquet,
others data/raw/majors_intraday_20260924/{SYM}_1m_20*.parquet,
from 2020-08-01 (warmup) to live end. Built per phase shift s on the
phase 4h grid; 4h bar i closes at idx[i] (minutes [idx[i]-4h, idx[i])):
open = first 1m open, high = max 1m high, low = min 1m low,
close = last 1m close. One coin in RAM at a time, float32 1m arrays.
If a coin/year lacks 1m coverage, that anchor-year is disclosed-skipped
for that variant (never imputed); expected: full coverage, no skips.

- sigma360[i,a]: program definition (oc_adaptsig / prep sig4 family):
  pct_change of 4h OPENS, rolling 360 std ddof=1, min_periods 120,
  shift 1 (value at i uses returns ending at bar i-1 only; strictly
  past, known at close idx[i]).
- V1 threshold: trailing-90d p80[i,a] = 80th percentile of sigma360
  over the 540 bars before i (sigma360[i-540:i], all < i). V1 veto
  per (coin, bar): sigma360[i,a] > p80[i,a]. Warmup rule (frozen):
  fewer than 120 finite sigma values in the 540-bar window -> NO veto
  (False), never imputed.
- BTC 24h range: range24[i] = (max 4h-high over bars i-5..i
  minus min 4h-low over bars i-5..i) / close[i], BTCUSDT only, bars
  closing <= idx[i] (current bar included, known at its close).
  median30d[i] = median of range24 over bars i-180..i-1 (180 bars,
  all < i). Expansion veto (global): range24[i] > 2.0 * median30d[i].
  Warmup: fewer than 60 finite ranges in the 180-bar window, or
  non-finite median/range, or median <= 0 -> NO veto.
- V1 (pre-registered): veto[a,i] = per-coin sigma veto only.
- V2 (pre-registered): veto[a,i] = per-coin sigma veto OR global BTC
  expansion veto (when BTC expansion fires, ALL 5 coins vetoed).
Thresholds frozen ex-ante from the idea (p80, 90d/540b, 2.0x,
30d/180b, 24h/6b, sigma360 360/min120); nothing fitted, no embargo
needed beyond strict causality (rolling windows use only past bars).

## Veto action (frozen, human-followable)

When veto[a,i] is true (in addition to the night-bar skip, on EVERY
variant row including the reference definition):
- book: trade policy returns wait (flat) / hold (in position): no new
  book order that bar; resting orders, SL, TP stay on the exchange.
- dip: sleeve_filter returns 0.0: no new dip limit that coin+bar.
Holds/exits unchanged on all rows. Book sizes, dip sizes/TP/stops,
budget 0.26, agents, and all harness settings unchanged; veto is
skip-only (never re-peg, never resize). TP/stop distances frozen.

## Pre-registered rows (ONLY these, no other variants)

Majors = BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT.
- M5_human (reference, veto never fires, unpatched eu.simulate;
  identity filter line identical to oc_manualsplit / oc_k2manual).
- VETO_V1: sigma360 > trailing-90d p80 per-coin veto.
- VETO_V2: V1 OR BTC 24h range > 2x trailing-30d median (global).
No exposure-matched control: IDEAS5 asks it for book ideas; #8 is a
MANUAL idea whose harness is vs M5_human with the win-book row deciding
with R (no control pre-registered).

## Selection (AGENTS.md robust criterion, dev years ONLY)

VETO_V1 vs VETO_V2 judged ONLY on dev years 2021-2024
(anchors 2021-09-24..2024-09-24). Eligible = DDdev4 <= 20 and no losing
dev year; robust preference: dev4 mean >= 5 %/month if any, then highest
dev4 WORST-year monthly, ties -> higher mean. Win-book row decides with
R (per IDEAS5 harness line). The most recent year 2025-09-24..2026-09-23
is scored ONCE, for the dev4 robust pick and the reference only,
labelled POST-HOC, never used to choose or to change anything. All rows
run in the same single 4-phase pass (oc_k2manual / oc_manualcap
precedent); the choice uses dev4 numbers only. 5-year R5/W/maxDD/fullDD
are context only. If anything changes after seeing an outcome, the
original row stays and the change is added as a disclosed extra row
(not planned). MANUAL gate context: R5 >= 5, fullDD < 20, book win >=
55%. Verdict question: how much of the MANUAL gap to 5 %/month
(M5_human R5 3.728, gap 1.272pp) does the veto close?

## Leakage audit (to be stated in REPORT.md)

- feature timing: sigma360/range from 1m bars closing <= decision-bar
  close idx[i] only (sigma shifted one extra bar; thresholds from bars
  < i); veto[i,a] joined by (idx[i], coin) bar-open only, never minute
  or fill data; R2 size/TP tables keyed by holding-bar time T
  (bar-open lookup only); no 1m data enters any decision beyond the
  veto's past-bar aggregates (causality test bans fill-minute markers).
- label windows: no new labels; no outcome enters any veto or sizing
  decision.
- fit windows: nothing fitted; all thresholds frozen round numbers
  from the idea (p80, 2.0x, 90d/30d/24h/360); rolling windows use only
  past bars; no test-year statistic feeds any choice.
- fill timing: no fill minutes 0..15 (win_start=15 books,
  sleeve_start=16 dips, stricter than the minute-5 user rule); limits
  fill only on 1m trade-through; stop-first on same-bar SL+TP touch;
  dip timeout at next 4h open.

## Outputs

research/tournament/oc_manualveto/{PLAN.md,compute_manualveto.py,
results.json,REPORT.md,tmp/} + tests/test_oc_manualveto.py only.
results.json: per-row years_R/years_DD/book wins/rung wins/fills/veto
rates; R5/W/maxDD/fullDD/Rdev4/Wdev4/DDdev4/losing_dev4/Rlast, costs,
baseline, data-span disclosure. REPORT.md ends with a 3-line Vietnamese
verdict (adopt / reject / needs prospective evidence) + one-line
MANUAL-gap verdict with gap in pp. Heavy run in ONE heavy_slot process
(tag oc_manualveto), heartbeat progress at least every 10 minutes, one
coin at a time float32, nohup + log under tmp/.
