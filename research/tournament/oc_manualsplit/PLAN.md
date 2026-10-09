# oc_manualsplit PLAN (pre-registered, frozen before any run, 2026-10-07)

Idea B8 (docs/opencode/IDEAS_20261007c.md): MANUAL split-TP bracket ladder
(human half-bank + runner). Every DIP bracket order is split into two
half-size limits at the same price with the same stop; half A TP at +a sigma,
half B at +b sigma (both maker limits, placed with the entry as Bybit TP/SL
attachments - a human places them once). Book orders unchanged.

## Reference (must reproduce exactly or STOP)

M5_human = deployed MANUAL M5 (v367) on the human schedule, exactly as
research/diagnostics/manual_human/manual_human.py runs it and as scored in
research/diagnostics/oc_manualcap (reset metric + v388.mix full-path DD):
- pipe v367 via pof.pipe_setup (book_mult 0.75, tighten on flat-signal losers,
  M3_R2_RUNG mapped agents ON with per-phase v376/tables_hidden R2 tables).
- human schedule on EVERY row: 15-min reaction (book orders from minute 15
  via win_start=15, dip limits from minute 16 via sleeve_start=16) + night bar
  skipped: on the holding bar starting at (20+s) UTC no new book order
  (flat -> wait, in position -> hold) and no new dip limit (sleeve_filter 0);
  resting orders, SL, TP stay on the exchange.
- gate costs maker 0.0002 / taker 0.00055, longs pay 0.0001 per 8h settlement,
  shorts nothing; limit fills only on 1m trade-through, no fill minutes 0..14
  (stricter than the minute-5 user rule); stop-first if SL+TP same 1m bar;
  dip exits: TP limit (maker) / touch stop 8.0sg market (taker) / timeout at
  next 4h open (taker); book SL 5.0 / TP 10.0 sigma_d per v362/v367.
- 4 phases s=0..3, live window [2021-09-24+sh, 2026-09-23+sh), anchors
  2021-09-24..2025-09-24 (+sh per phase), each year [a0, min(a0+365d, live1)).
- scoring: reset_metric.year_reset per anchor + v388.mix full-path DD
  (v421/v422 convention); per-year %/month, yearly DD, full-path DD, win
  rates (book episodes via v213.trade_stats dev+_hidden, dip rung exits via
  ret>0 on rung_tp/sl/timeout, all = book+dip), trade counts.
- reproduction gate: this study's M5_human rerun must be BIT-EXACT vs
  research/diagnostics/oc_manualcap/oc_manualcap_runs.pkl
  (max abs d(eq,eq_min) <= 1e-12 over 4 phases) AND equal
  R5 3.728 / W 0.847 / maxDD 17.94 / fullDD 17.79 / book_win .6482.
  Else STOP and report the mismatch (no H1/H2 numbers are used).

## Deployed dip TP reference (ratio rule)

M5's dip TP is NOT a fixed 1.0 sigma: with agents ON the TP multiplier comes
from the walk-forward R2 table (artifacts/.../v321_r2_table_m0.parquet,
values 0.5 / 1.0 / 1.5, median 1.0). So per the assignment the split keeps the
same RATIOS relative to the deployed per-rung TP multiplier m0:
- H1: half A TP mult = 0.75 x m0, half B = 1.5 x m0.
- H2: half A TP mult = 0.50 x m0, half B = 1.0 x m0.
TP price = limit x (1 + mult x sg). Stop unchanged (8.0sg touch, same level
for both halves, one shared stop level). Same entry price, same fill minute,
same timeout bar, same fees per half (maker entry+TP, taker stop/timeout).

## Pre-registered rows (ONLY these, no other variants)

- M5_human (reference, unpatched eu.simulate).
- H1_split75_150: M5_human with every taken dip rung split into two halves
  rn/2 + rn/2 at ratios (0.75, 1.5) x m0.
- H2_split50_100: same with ratios (0.5, 1.0) x m0.
Budget semantics (fixed): the engine risk-budget check (0.26) is applied ONCE
on the full rn before the split (a human places both halves totalling the
planned notional); both halves are then taken without a second budget cut.
No gross cap (M5_human has none). Night dip skip applies before any split
(filter 0 on night). Book path untouched.
Minimum-notional merge (fixed, Bybit): half notional = (rn/2) x prev_eq
x 10000. If EITHER half < 5.0 USDT, the rung is NOT split: single order with
the deployed TP and full rn (counted in stats split_merged, reported per row
and total). 5.0 USDT = Bybit linear-perp default minimum (bot/bybit_v5.py,
bot/tsmom.py MIN_NOTIONAL_DEFAULT); engine book minima (BTC 100 / ETH 20 /
else 5) are not used for dip halves. Merges expected ~0 (typical half ~400
USDT) but counted honestly.

## Selection (AGENTS.md robust criterion, dev years ONLY)

Compare H1 vs H2 ONLY on dev years 2021-2024 (anchors 2021-09-24..2024-09-24):
eligible = DDdev4 <= 20 and no losing dev year; prefer dev4 mean >= 5
%/month if any; among the pool pick the highest dev4 WORST-year monthly;
ties -> higher dev4 mean. Most-recent year 2025-09-24..2026-09-23 is scored
ONCE, only for the chosen variant (and M5_human), labelled POST-HOC, never
used to choose. If neither is eligible, PICK = none-eligible.
5-year R5/W/maxDD/fullDD are context only.

## Leakage audit (to be stated in REPORT.md)

- features at decision time use only data available at that time (4h bar
  values at its close; R2 size/TP tables keyed by holding-bar time T,
  pre-fit walk-forward, never minute/fill data).
- no new fits/thresholds/quantiles; split ratios fixed above before any run.
- fills need 1m trade-through from minute 15/16; stop-first on same-bar touch.
- state explicitly: feature timing, label windows, fit windows, fill timing.

## Outputs

research/tournament/oc_manualsplit/{PLAN.md,compute_manualsplit.py,
results.json,REPORT.md,tmp/} + tests/test_oc_manualsplit.py only.
results.json: per-row years_R/years_DD/book wins/rung wins/fills/merges,
R5/W/maxDD/fullDD/Rdev4/Wdev4/DDdev4/losing_dev4/Rlast, pick, costs, baseline.
REPORT.md ends with a 3-line Vietnamese verdict (adopt / reject /
needs prospective evidence) + one-line MANUAL-gap verdict with gap in pp.
