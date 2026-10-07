# oc_postflush PLAN (pre-registered BEFORE any outcome is inspected)

Idea #30: post-flush recovery book overlay. The dip ladder buys market-wide
flushes and earns when they revert. Question: after a market-wide flush that
has started to revert, is there remaining drift worth holding as a BOOK long
for the next 4h bar?

## Hypothesis (fixed here)

After a 4h bar in which >= 3 majors traded >= 2.5 sigma4 below their own bar
open but recovered to close above (open x (1 - 1.0 sigma4)), the next 4h bar
still drifts up on the recovered coins (continuation of the snap-back).
Direction pre-registered: mean next-bar net return > 0. PROMISING only under
the decision rule below.

## Data (fixed here, all in repo)

- Hourly panel: `research/tournament/ext/hourly_ext.parquet` (t = bar START
  UTC; open/high/low/close; 35 coins, 2020-08-01 .. 2026-09-23 23:00 UTC).
  Coins used: majors {BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT} only.
- 1m klines (one coin at a time, freed before the next coin):
  `data/raw/btc_intraday_20260924/klines_1m_YYYY.parquet` (BTC),
  `data/raw/majors_intraday_20260924/<SYM>_1m_YYYY.parquet` (others).
  Columns open_time (= bar START, UTC), open/high/low/close. Bars with
  open_time >= 2026-09-24 00:00 UTC are dropped; no data beyond the cutoff.
- Dip stream for correlation: `research/tournament/ext/fills_U_ext.parquet`
  via `research/tournament/ext/harness5.py::load` (y_dep at deployed TP,
  size_dep; exact net, fees + adverse funding inside).
- `research/tournament/ext/bar_open_ext.parquet` is NOT used for prices
  (4h opens are rebuilt from hourly_ext so sigma4 matches v293 exactly);
  listed here as the available bar-open source per assignment.
- Market data up to 2026-09-24 00:00 UTC may be read (assignment override;
  all five years are research data; any finding needs prospective
  validation).
- LIGHT job: one process, hourly panel in memory (< 300 MB), 1m one coin at
  a time (yearly files concatenated per coin as float64 open only, then
  freed). RAM < 1 GB. No GPU.

## Exact causal definitions (frozen)

4h grid: bars with open T on 00/04/08/12/16/20 UTC from 2020-08-01 00:00 UTC
(same grid as fills_U T and v293: T = START + 4h*j). Bar [T, T+4h) closes at
C = T+4h. Anchor years Y_k = [A_k, A_k+365d) by event close C,
A in {2021-09-24 .. 2025-09-24} UTC. Events with exit C+4h > 2026-09-24
00:00 UTC are excluded (so the last year ends 2026-09-23 20:00 <= C).

1. `O_s(T)` = hourly open of coin s at t = T (NaN if the hourly bar missing).
2. `L_s(T)` = min(hourly low over t in {T, T+1h, T+2h, T+3h}) (NaN if any of
   the 4 hourly bars missing).
3. `Cc_s(T)` = hourly close at t = T+3h (the 4h bar close; NaN if missing).
4. `sigma4_s(T)`: per-coin v293 definition on the 4h-open series o[j]:
   pc[j] = o[j]/o[j-1]-1; sigma4[j] = std(pc[j-360..j-1], ddof=1) with
   min_periods=120, i.e. `pd.Series(pc).rolling(360, min_periods=120).std()
   .shift(1)`; NaN/<=0 unusable. o[j] is the hourly open at the j-th grid
   point (built from hourly_ext, not from 1m). Causal: uses only opens
   strictly before T.
5. B1 condition (coin s, bar T): sigma4 finite > 0 AND O finite AND
   `L_s(T) < O_s(T) * (1 - 2.5 * sigma4_s(T))`.
6. Recovery condition (same s, T): `Cc_s(T) > O_s(T) * (1 - 1.0 * sigma4_s(T))`.
7. EVENT at close C = T+4h iff >= 3 majors satisfy BOTH 5 and 6 for bar T.
   Recovered set R(C) = coins satisfying both. No outcome data is used for
   event definition.
8. Signal: at C, book-long each s in R(C), equal weight, holding bar
   [C, C+4h):
   entry price `P_in,s` = 1m OPEN at C+5min (first fillable minute; the
   pipeline needs 5 min; maker 0.0002);
   exit price `P_out,s` = 1m OPEN at C+4h (= next 4h open; taker 0.00055).
   Both 1m opens must exist with exact minute timestamps, else the leg is
   missing (rule 9).
9. Leg net return: `r_s = P_out,s / P_in,s - 1 - 0.0002 - 0.00055
   - (0.0001 if hour(C+4h UTC) in {0,8,16} else 0)`. The funding term is the
   gate adverse rule (longs pay 0.0001 per 8h settlement held; at most one
   settlement per 4h hold, due exactly when the exit bar open is a funding
   timestamp). Event return `R(C) = mean_s(r_s)` over recovered coins.
   Event VALID only if EVERY recovered coin has both 1m prices; otherwise the
   whole event is dropped (strict; drops logged per year). No partial events.
10. Overlay daily P&L: `D_ov(d) = sum(R(C) for valid events with
    floor(C)=d)` (UTC calendar day of the event close; 0 on days with no
    event). Dip daily: `D_dip(d) = sum(size_dep * y_dep)` over majors-R2
    fills with floor(T)=d via harness5.load (0 on empty days). Pearson
    correlation over the 365/366 calendar days of each anchor year
    (zeros included; NaN if a leg has zero variance).

Timestamps: features/prices at/before C+5min entry use only bars with
END <= entry except the exit price (known only at exit, as traded).

## Evaluation (fixed here — parameter-free, one variant)

- Per anchor year (by C): n events (valid), mean / median / win rate
  (fraction R>0) of R(C) net, plain t-stat = mean/(sd/sqrt(n)) with ddof=1
  (NaN if n<3 or sd==0), worst event (min R with its C), total overlay
  return sum(R), funding paid, dropped-event count, mean recovered-set size,
  Pearson(D_ov, D_dip) with n days. Returns in bps x1e4 for reference;
  round-trip cost context ~7.5 bps + funding when due.
- LOYO: the overlay has NO fitted parameters/thresholds, so the held-out
  year statistic is the held-out year's own mean net. PASS_loyo(h):
  mean(R | C in year h) > 0 — numerically identical to the sequential pass
  by construction (disclosed here, not data-dredged).
- DECISION RULE (assignment + event-count floor): PROMISING iff
  (a) mean net > 0 in >= 4 of 5 anchor years, AND (b) PASS_loyo in >= 4 of 5
  held-out years, AND (c) valid events >= 10 in EVERY anchor year.
  Otherwise NOT PROMISING. NaN = FAIL, never imputed.
- Descriptive only (NOT part of the rule): per-coin leg means, median,
  t-stat, worst event, dip correlation, cost split.

## Causality / alignment tests (tests/test_oc_postflush.py)

- test_sigma_causal_truncate: per-coin sigma4 at sampled T recomputed from
  hourly panels truncated to t < T equals the stored value.
- test_event_windows_only_prior_bars: shifting all hourly bars at/after C
  leaves the event flag at C unchanged (recompute on truncation); intrabar
  low uses only the 4 hourly bars of [T, T+4h).
- test_entry_exit_timing: synthetic 1m frames map entry to C+5min open and
  exit to C+4h open exactly; moving the C+5min bar changes the return,
  moving earlier bars does not change other events.
- test_funding_rule: synthetic legs exiting at 08:00 pay 0.0001, at 04:00
  pay 0; exit at C+4h uses taker 0.00055 and entry maker 0.0002.
- test_year_counts_and_bounds: results.json per-year n sums to total valid
  events; no C outside 2021-09-24 .. 2026-09-23 20:00+4h; no 1m/hourly bar
  with START >= 2026-09-24 used; decision strings recomputed from yearly
  means equal stored values.

## Deliverables

research/tournament/oc_postflush/: PLAN.md (this file),
compute_postflush.py, events_postflush.parquet, results.json, REPORT.md
(tables + one-line verdict). tests/test_oc_postflush.py. No commits, no
edits outside these two paths. One process, RAM < 1 GB.

Note on docs/opencode/OPENCODE_VF_COMMON.md: its compute()/events() contract
targets BTC-bar pattern features; this assignment is a tournament
post-flush study with its own fixed deliverables, so the common-pattern
contract does not apply; the shared rules honoured are causality (value at
C uses only bars ending <= C, entry from C+5min), no peeking at outcomes
before freezing definitions, and the default 4/5 + LOYO 4/5 rule (plus the
assignment's >= 10 events/year floor).
