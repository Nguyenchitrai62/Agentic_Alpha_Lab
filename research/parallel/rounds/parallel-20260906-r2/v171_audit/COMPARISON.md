# v171 audit — Part B comparison

Part A `replication.json` was saved before `v171/` was opened.
Independent implementation from `OPENCODE_V171_AUDIT.md` only
(`v171_audit/replicate_v171.py`); engine_real imported solely for
`v154_books`, `context`, constants. Numbers below from
`v171_audit/checks_v171.py` (raw parquet, no v169/v171 imports).

## Reproduction vs `v171/v171_result.json` — EXACT on everything

| Anchor | k audit/v171 | Sleeve net% | Sleeve DD% | Events |
|---|---|---|---|---|
| 2021-09-24 | 3 / 3.0 | 31.78 / 31.78 | 8.05 / 8.05 | 208 / 208 |
| 2022-09-24 | 4 / 4.0 | 7.79 / 7.79 | 8.93 / 8.93 | 95 / 95 |
| 2023-09-24 | 3 / 3.0 | 64.80 / 64.80 | 9.12 / 9.12 | 257 / 257 |
| 2024-09-24 | 3 / 3.0 | 29.65 / 29.65 | 7.18 / 7.18 | 224 / 224 |
| 2025-09-24 | 3 / 3.0 | 33.96 / 33.96 | 7.32 / 7.32 | 255 / 255 |

Combined (v154 engine_real + sleeve): monthly 5.959 / 5.959, full-path DD
21.85 / 21.85; yearly net 52.27 / 49.44 / 216.32 / 105.86 / 117.51, DD
19.08 / 13.85 / 16.03 / 14.33 / 13.83, fills 2048 / 2181 / 2190 / 2190 /
2184, mean_g identical — all exact. Baseline without sleeve reproduces
engine_real 3.708 / 18.87 in both. Robustness cross-check: per-anchor
mean/median bps and event counts match `v171_robustness.json` exactly
(55.8/17.2, 34.0/37.8, 81.0/80.5, 47.3/29.9, 47.7/6.8).

Non-material definitional diff: train Sharpe per bar matches to 3dp
(0.062/0.0538/0.0473/0.0482/0.0471) but audit's 4th decimal is
.0625/.0540/.0476/.0484/.0473. Cause confirmed: v171 seeds the sigma
rolling window at the grid start (2020-02-01), the audit uses full
pre-history. Sigmas differ for the first 240 grid bars only (max abs diff
0.27pp on 2020-03-14, last diff 2020-03-31), inside the selection window
but never in an applied window — k choices and every reported number are
unaffected. Both conventions are causal.

## Adversarial checks

(1) Look-ahead: none found. Sigma(t) uses 4h opens <= t in both
implementations. Trigger/reference/entry minutes (16..238, m+1) are all
strictly inside holding bar T = t+4h, i.e. after the decision; the only
use of T+4h data is the exit fill itself. No signal, weight, or return
uses post-decision data beyond the executed prices. `minute_cube`
offsets are `(open_time - floor4h) // 60` (correct alignment); its
within-bar ffill never carries across bars. One staleness note: a
ffilled minute repeats the last print, so a trigger can fire on a stale
price — direction is conservative (fires at first observed dip), and all
1039/1039 applied-k trigger minutes are present in raw pre-ffill 1m data,
so no phantom triggers exist.

(2) 1m/4h alignment: minute-0 1m open == 4h open(T) (median rel diff 0
bps all symbols; only 1–2 bars/symbol differ >1bp, max 12–60bps single
bars, none event-bearing). Zero duplicated 1m timestamps in all 5 files
(17.4M rows). Fully-missing bars: 56 BNB (pre-2020-02-10 history),
1357 SOL (pre-2020-09-14 history), 1 each elsewhere — all correctly yield
no event.

(3) Top-20 events are real market moves, not data errors. Every one sits
on a known stress date: 2022-05-11 SOL/XRP (Luna/UST), 2022-11-09/10 SOL
(FTX), 2022-06-13/15 ETH/SOL (Celsius/3AC), 2024-08-05 BTC/ETH/BNB (yen
carry unwind), 2024-04-13 SOL/BNB (Iran–Israel weekend),
2023-12-11 SOL (-13% minute, 1.06M volume), 2024-01-03 SOL (ETF flush),
2026-02-05/2026-08-22 XRP/ETH. Raw 1m rows show genuine panic minutes
with 10–50x normal volume (e.g. XRP 2021-10-17: 55M volume on a −5.6%
wick). Dips −348 to −1319bps rebound to +691…+1404bps net per event.
Concentration warning (from v171's own robustness table, verified):
without the top 5% of events the sleeve keeps only 5.33 / −3.57 / 28.12
/ 12.76 / 9.59 %/yr — 2022 goes negative. This is a crash-rebound
strategy whose year rests on a handful of panic bars.

(4) Entry tradability: entry-minute (m+1) volume > 0 for 1039/1039
events (median minute volume: BTC 2003, BNB 8217, ETH 28841, SOL 144615,
XRP 9.36M base units); entry price inside that minute's [low, high] for
1039/1039. Entry is the next-minute open with 0.0002 slip + 0.0005 taker
fee per side — no same-minute fill, no maker/queue assumption. OHLC
alone cannot prove depth, but nothing in the data contradicts
fillability at these sizes (0.25 equity units).

(5) Exit sensitivity (exit at T+4h+15min instead of the 4h open, same k):
2021 +14.06pp (31.78→45.84), 2022 +3.06pp, 2023 +4.16pp, 2024 +0.56pp,
2025 −10.51pp (33.96→23.45). No systematic collapse — the rebound is
not just the 4h-open print — but exit timing moves results by ~±10pp
and 2025 loses a third with 15min delay.

## Caveats (disclosed, not bugs)

- Sleeve notional (up to 5 × 0.25) sits outside the engine's 5%-buffer
  capital budget and has no liquidation modeling; the author discloses
  this in the module docstring. Combined full-path DD is 21.85,
  above the 20% governor reference — the governor only reacts ex post.
- Origin is ex post (idea from v169 error analysis, also disclosed);
  treat as hypothesis, not validated edge. 2022 sleeve net is 7.79%
  with DD 8.93% and relies entirely on outliers.

## Verdict

PASS — independent blind replication matches `v171_result.json` and the
`v171_robustness.json` event statistics exactly; no look-ahead, data
error, or unrealistic fill found. The unusually good sleeve (+8…+65%/yr,
DD 7–9%) is arithmetically real under the stated (taker, next-minute,
full-funding) execution, but concentrated in a few crash-rebound bars
per year and sensitive to exit timing — hypothesis-grade, not validated.
