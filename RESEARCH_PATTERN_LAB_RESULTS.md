# pattern_lab r1-r4 results (2026-09-24)

User request: test candlestick patterns, classical chart patterns and indicators,
mainly as model features, inside a trade-suggestion pipeline. Leader (Claude
Code) owned all modelling/evaluation decisions; three OpenCode workers
(muse-spark-1.3-contributor, new sessions) wrote the feature libraries.

Protocols (hashed before running, `artifacts/research/pattern_lab/protocol.sha256`):
`configs/pattern_lab_r1_protocol.json` (24cf1590...), `_r2_` (f5f8b8ec...),
`_r3_` (cf9e5207...), `_r4_` (52369b2f...). Development decisions
2019-09-08..2025-09-13, walk-forward from 2021-01-01, selection validation
2024-01-01..2025-09-13. Opened-year check 2025-09-24..2026-09-22, run once per
protocol (marker files block reruns). The opened year was already exposed by
ma_ribbon_r1; see disclosures in each protocol.

## Feature libraries (workers, leader-verified)

`src/agentic_alpha_lab/patterns/{candles,chart,indicators}.py`; contract and
event study `patterns/common.py`. Leader re-ran `assert_causal` on real 1h/4h/1d
bars (chart: 40 random cuts). Leader fix: indicators now read full funding
history (as-of joined) so opened-year features are not starved.

| Library | Event tests (dev, BH-FDR q<0.1, n>=30, half-stable) | Finding |
|---|---|---|
| Candles (27 patterns) | 5/264, all 1h, 4-13 bps | ~ cost; pin bar works against tradition |
| Chart (18 patterns, causal pivots) | 0/212 | double top/bottom, H&S: no edge; Donchian20 4h +29 bps (q=0.23) |
| Indicators (14 events) | 2/168, 4h Bollinger | breakout continues (+31 bps); band re-entry fade fails |

## r1: triple-barrier classifier (4h/1d, TP 2 ATR, SL 1 ATR)

Walk-forward AUC 0.47-0.52 for every feature set. Dev acceptance passed only
4h base+chart gated and all gated (daily-ribbon gate). Opened year: base+chart
gated +2.3% normal / -0.6% stress, 18 trades; all gated -7.8% / -12.4%. FAIL.
Bracket stops are assumed to fill at the stop price, which is optimistic in
flash crashes (2025-10-10 20:00 bar: wick to 101,516, -13%).

## r2: meta-labeling trend trades by P(win)

Trend trades win 27% with a fat right tail; filtering by P(win) removed the big
winners (Sharpe 0.99 -> 0.32). FAIL; model framing was wrong.

## r3: sizing/gating variants of 4h EMA20/200 ribbon long

Best: B = enter only if the daily ribbon is not bearish. Walk-forward +348%
normal / +147% stress, Sharpe 1.14, but DD 28.8% > 25% limit, so no selection.
DD came from the 2023 chop (14-loss streak); top 10 trades = 104% of gross.

## r4: chop filters + ML forward-efficiency filter + DD-targeted size

No filter beat B on validation; ML forward-ER Spearman 0.069 (dev), 0.173
(opened year), and the filter hurt. Selected B at size 0.65
(= 0.20 / 2021-2023 DD). Dev walk-forward +181% / +91% stress, DD 19.6%.

**Opened-year check: PASS.** Buy-and-hold -30.3%, DD 59.4%.

| Opened year | Normal | Stress | Intrabar DD | Trades | Sharpe | Monthly |
|---|---|---|---|---|---|---|
| B x0.65 (selected) | +13.6% | +7.4% | 10.7% | 48 | 1.02 | 1.07% |
| B x1 | +20.4% | +10.5% | 16.1% | 48 | 1.02 | 1.57% |
| R2 ADX>20 (not selected) | +24.2% | +17.2% | 14.5% | 32 | 1.26 | 1.83% |

3% monthly aspiration: not met.

## Cross-asset check of the frozen rule (no tuning, 10 USD-M perps)

Last year: buy-and-hold lost on 10/10 (median -47%); B x0.65 positive on 6/10
(5/10 under stress), median DD 16.5%. 2021-2025: positive on 8/10 but median
Sharpe 0.75 vs buy-and-hold 0.90, median DD 51%. The rule's value is mainly
bear-market avoidance, not bull-market alpha. `research/pattern_lab_xasset.py`.

## Frozen candidate and prospective log

`src/agentic_alpha_lab/signals/trend_advisor.py` (`pattern_lab_r4_R0_scaled_0.65`),
proven identical to the backtest painting and prefix-causal
(`tests/test_trend_advisor.py`). `scripts/advisor_shadow.py` appends one row per
closed 4h bar to `artifacts/research/advisor_shadow/shadow.jsonl` with
`logged_at`; rows logged more than 6h after the bar are `backfill`. First
prospective row: bar closing 2026-09-24 11:59 UTC, action EXIT_TO_FLAT.

## What the evidence says

- Pattern and indicator features do not give a BTC model directional skill
  (AUC ~0.5). They are not worth more compute in this framing.
- The only repeatable effect is trend persistence with a daily regime gate.
- Next clean evidence can only come from prospective data. Re-evaluate after
  at least 6 months or 20 closed prospective trades, whichever is later.
