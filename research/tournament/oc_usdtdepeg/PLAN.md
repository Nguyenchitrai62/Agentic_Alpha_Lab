# oc_usdtdepeg PLAN (pre-registered BEFORE any outcome statistic)

Assignment: docs/opencode/OPENCODE_W_oc_usdtdepeg.md (+ OPENCODE_W_COMMON_20261007.md,
AGENTS.md, OPENCODE_VF_COMMON.md). Idea B9 of docs/opencode/IDEAS_20261007c.md.
Read first: CLOSED_DIRECTIONS.md USDT-premium items — oc_usdtprem (book tilt,
engine NO), oc_usdtdip (dip-size tilt, dSum +0.047 < +0.273 gate, NO),
oc_usdtshort (short-leg tilt, P&L 5/5 p99.6 but DD 3/5, NO). This sleeve is
different: it trades the stablecoin itself (long USDT-USD snap-back), not a
tilt of the majors. No parameter is fitted; every number below is fixed before
any P&L/placebo/overlay statistic is computed.

## Data (read-only)

- `data/raw/coinbase_usdt_20261006/USDT-USD_1h.parquet` (Coinbase USDT-USD 1h
  candles: open_time/open/high/low/close/volume). Manifest: requested
  2021-01-01..2026-09-24, actual first bar 2021-05-04 01:00 UTC, last
  2026-09-23 23:00 UTC, 47240 rows, 3 gaps (2023-03-04 4 missing h,
  2025-10-25 6 missing h, 2026-05-08 5 missing h). Granularity = 1h.
- Checked: NO 1m/5m USDT data exist anywhere under data/raw (only this 1h
  file). Per the assignment, signals use 1h closes; fills/exits use the next
  1h bars' low/high with STRICT trade-through (no 1m refinement).
- Bars used: open_time < 2026-09-24 00:00 UTC only. Windows below are counted
  in BARS (robust to the 15 missing hours; labelled).

## Rule (fixed; ONLY these two variants)

State machine, one position at a time. States: FLAT -> (signal) PENDING ->
(filled) IN_POSITION -> FLAT. Signals are ignored while PENDING or
IN_POSITION. Each signal is consumed (no queue).

- Signal: 1h bar t with close_t < TRIGGER (known at bar t's close; uses only
  close_t).
- Entry: resting limit BUY at L = close_t - 0.0001, valid bars t+1..t+4 (4 h
  window). Fill at the FIRST bar i in the window with low_i < L STRICTLY
  (trade-through; low_i == L exactly is NO fill). Fill price = L, maker fee.
  No fill in window -> back to FLAT, no position.
- Exits (monitored from the FILL bar itself, inclusive — conservative: a
  crash bar that fills can stop the same bar; labelled):
  - STOP: if low_j <= STOP_PX (touch) -> exit at STOP_PX, taker (market).
  - TP: else if high_j > TP_PX STRICTLY (trade-through) -> exit at TP_PX, maker.
  - Same-bar priority: STOP FIRST (stop checked before TP every bar).
  - CAP: else exit at the close of bar (fill_idx + 72) (72 h holding cap),
    taker. If the panel ends first, the position is dropped as INCOMPLETE
    (excluded from sums, listed; not silently closed).
- Variants (assignment-fixed):
  - E1: TRIGGER 0.9975, TP 0.9995, STOP 0.9900.
  - E2: TRIGGER 0.995, TP 0.999, STOP 0.985.
- Net per FILLED event (fraction of USDT notional):
  net = (exit_px - L) / L - fee_entry - fee_exit,
  fee_entry = maker always; fee_exit = maker (TP) or taker (stop/cap).
  Win = net > 0 strictly.
- Costs: gate row maker 0.0002 / taker 0.00055; second RETAIL stress row maker
  0.004 / taker 0.006 (same fills/exits, fees only).
- Note vs idea B9 sketch (limit mid-10bps, exit next 4h open): the ASSIGNMENT
  rule governs (entry close-0.0001, 72 h cap, explicit stop); difference logged.

## Years, selection, testability (fixed)

- Anchors A in {2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24} = dev4, plus
  2025-09-24 = most-recent year. Year y = [A_y, A_y + 365 d). Events attributed
  by SIGNAL bar time. Dev4 computed first for E1+E2; the most-recent year is
  scored ONCE, only for the chosen variant, after the choice is frozen, and
  labelled. It is never used to pick.
- TESTABILITY FLOOR (assignment): < 10 filled events in the five years ->
  UNTESTABLE, reject, no overlay adoption (overlay still quantified once for
  the chosen variant as a "how tiny" number, labelled descriptive).
- Choice rule (dev4 ONLY; robust criterion analogue for a standalone sleeve):
  if testable, pick the variant with the higher dev4 total net sum; tie ->
  higher dev4 mean bps/event; tie -> more dev4 events. If UNTESTABLE, the
  "chosen" variant for the single last-year scoring is the one with more dev4
  filled events (tie -> E1), labelled non-selection, descriptive only.
- Overlay adoption (only if testable): standalone dev4 sum > 0 AND placebo
  percentile >= 95 AND daily-PnL correlation vs G2 < 0.3 AND G2+overlay keeps
  yearly DD <= 20 with no losing dev year. Otherwise NO adoption.

## Placebo (fixed)

- Per variant on dev4: per anchor year y, N_y = actual filled entries. Each of
  200 draws (seed 7) picks N_y random 1h bars uniformly in [A_y, A_y+365d)
  (bars with valid OHLC), places the same entry (L = bar close - 0.0001,
  forced fill at L immediately, maker — isolates trigger-timing/exit edge;
  limitation: placebo fills do not require a trade-through, same convention
  as oc_ripcont), then identical TP/stop/cap exits from that bar (stop-first,
  same fees). Statistic: dev4 total net sum per draw. Report actual sum,
  placebo mean-of-means, p95, and percentile = 100 * fraction(draws <= actual).

## Overlay on G2 (fixed; "how tiny" quantification)

- Deployed reference G2 = R2B1D17BFG2 in v421 (v421_result.json: R 5.41 %/mo,
  W 2.588, max yearly DD 16.91, full-path DD 16.82). Hourly equity from
  v421_runs.pkl via v388_bot_stop_distance.hourly + 4-phase mean. f=0 (no
  sleeve) must reproduce the yearly (R, DD) rows TO THE DIGIT before any
  overlay; if not, stop.
- Account (oc_carrycompound convention):
  A(t) = A(t-1)*(1 + r_bot(t)) + dSleeve(t), r_bot from the stored G2 4-phase
  hourly mix. dSleeve realised at EXIT hour only: dSleeve = N * net with
  N = 0.05 * A at the entry hour (5 % sleeve, compounds across events; no
  intra-hold MtM — labelled; a ~1.0-pegged asset held <= 72 h, max adverse
  excursion to stop ~= -0.75 % * 0.05 ~= -4 bps account-level, negligible).
- Per-year reset to 1.0 at each anchor (reset_metric.year_reset arithmetic);
  R = 100 * (A_end^(1/12) - 1) geometric %/mo; yearly DD on the marked path
  (= close path here — sleeve exits are realised cash, labelled); full-path DD
  continuous from 2021-09-24 (close path; marked ~= close for this sleeve,
  labelled lower-bound convention as in oc_carrycompound).
- Report overlay lift in pp/month vs G2 (expected tiny) + daily-PnL
  correlation (sleeve daily exit-PnL vs G2 daily returns, dev4) for the
  corr < 0.3 check.

## Deliverables

research/tournament/oc_usdtdepeg/: PLAN.md (this file), backtest.py, run.py,
results.json, REPORT.md. tests/test_oc_usdtdepeg.py. Small job (47k 1h rows,
~44k hourly grid rows, 200 placebo draws): NO heavy_slot needed (< 0.4 GB, no
engine run, no GPU). No edits outside the two allowed paths. Data < 2026-09-24
only. Any post-outcome change is a disclosed extra row (original kept).
