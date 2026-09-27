# MA Ribbon r1 results (2026-09-24)

Protocol: `configs/ma_ribbon_r1_protocol.json`, SHA-256
`f5642fdbc5843966fcf71162805d7c29d2565b9aa23bdfb86150fe25f119ce7c`, hashed
before any holdout metric was computed. Code: `src/agentic_alpha_lab/backtest/ma_ribbon.py`,
`src/agentic_alpha_lab/models/ma_ribbon_ml.py`, `scripts/ma_ribbon_study.py`,
tests `tests/test_ma_ribbon.py`. Full output (ignored):
`artifacts/research/ma_ribbon_r1/report.json`, `grid.csv`.

Data: Binance USD-M BTCUSDT 1d/4h + funding, 2019-09-08..2026-09-23
(`data/raw/ma_ribbon_20260924/manifest.json`). Development decisions
2019-09-08..2025-09-13; 10-day embargo; holdout decisions 2025-09-24..2026-09-22,
computed once. Fill at next open, 1x, compounded, index 100.

Holdout exposure disclosure: this year is not pristine in the human sense.
Earlier OpenCode/Codex rounds loaded 2022-2026 5m data for other strategies and
the leader saw the user's chart. Protection is the pre-registration only. The
holdout is now opened; the only clean test left is prospective.

## Holdout year (buy and hold: -33.3%, intrabar DD 59.1%)

| Row | Net normal | Net stress | Net actual funding | Intrabar DD | Trades (L/S) | Monthly geo | Dev Sharpe (B&H 0.85) | Dev intrabar DD |
|---|---|---|---|---|---|---|---|---|
| H1 SMA50>200 long | -12.6% | -13.0% | -11.5% | 29.1% | 2 (2/0) | -1.12% | 0.83 | 62.7% |
| H2 cross long/short | +2.0% | +1.5% | +5.0% | 28.5% | 3 (2/1) | +0.16% | 0.32 | 78.1% |
| H3 ribbon long | +2.9% | +2.1% | +3.3% | 18.7% | 4 (4/0) | +0.24% | 1.16 | 33.7% |
| H4 ribbon long/short | +31.3% | +28.1% | +33.2% | 18.7% | 14 (4/10) | +2.30% | 0.90 | 44.5% |
| Grid pick on dev: 4h EMA20/200 ribbon long | +22.4% | +11.3% | n/a | 14.7% | 53 | ~1.7% | 1.29 | 32.1% |
| ML HGB gated, frozen | +16.9% | +11.8% | +18.1% | 14.2% | 25 (9/16) | +1.32% | 0.28 | 56.1% |
| ML HGB ungated, frozen | +36.4% | +25.2% | +45.3% | 29.3% | 48 | +2.63% | 0.09 | 77.8% |
| ML LR gated / ungated | -31% / -42% | worse | worse | 40-50% | | | <0.1 | |

Ribbon = long when close > SMA50 > SMA200; short (H4) when close < SMA50 < SMA200; else flat.

## Verdicts against the pre-registered acceptance rule

Rule: holdout net > 0 under normal and stress, holdout intrabar DD <= 20%,
development Sharpe above buy-and-hold.

- PASS (research candidate only): H4 ribbon long/short, H3 ribbon long
  (economically negligible), grid pick 4h EMA20/200 ribbon long.
- FAIL: H1 and H2 (plain golden/death cross is too slow; it lost money in the
  holdout), all ML rows. HGB development AUC was 0.496 and LR 0.471 (no skill);
  the HGB holdout AUC 0.636 in one bear year is not evidence of skill because
  the same model had none over 4.7 development years.
- 3%/month aspiration with DD <= 20%: not met by any row in development or holdout.

## Caveats that limit the claim

- H4 holdout profit came mainly from three trades (short Jan-Mar 2026 +17.7,
  short May-Jul 2026 +16.0, long from 2026-09-09 +9.3 still open). Nine of 14
  trades lost. The 20-day block bootstrap 90% CI of annualized mean is
  [-14%, +81%]; the excess over buy-and-hold CI is [-49%, +186%]. Not significant.
- The holdout was a falling year; flat/short filters naturally beat buy-and-hold
  there. In development, H4 lost 23% in 2025 (to Sept) and had 44.5% DD.
- Grid: dev ranking did not predict holdout ranking (Spearman -0.10). The
  second-ranked dev config lost 0.6% in holdout. 70% of the 120 configs were
  positive in holdout (median +6.5%), which reflects the regime, not selection.
- Long-held 1x perp positions are not rebalanced, so funding erodes margin while
  notional stays; this raises B&H and H1 drawdowns vs spot holding.
- Drawdown uses daily bars (4h for the grid), not mark price.

## Independent replication (OpenCode R82, muse-spark-1.3-contributor)

A new OpenCode session (the old session ID fails with HTTP 400 on resume)
reimplemented H1-H4 and buy-and-hold from the protocol text alone and saved
`research/opencode_r82_ma_replication/replication.json` before opening the
leader's files (verified from the event log order). All holdout trade lists
(side, dates, prices) and all trade counts match exactly. Net differences come
only from sizing: the replication rebalanced to 1x of equity every day instead
of fixing quantity at entry. The worker judged the leader engine correct
against the protocol text, but the sensitivity matters:

| H4 holdout | Fixed quantity at entry (protocol) | Daily rebalanced 1x |
|---|---|---|
| Net normal / stress | +31.3% / +28.1% | +23.6% / +20.5% |
| Intrabar DD | 18.7% | 22.6% (fails the 20% limit) |

H2 flips from +2.0% to -10.9%. Any future H4 variant must declare its sizing
convention and report both.

## Current state (last closed daily bar 2026-09-23)

Close 84,355; SMA50 74,526; SMA200 70,761; golden cross on 2026-09-08. H3/H4
target is LONG since the 2026-09-09 open. Close is 13% above SMA50. This is a
rule state, not advice.

## Recommendation

1. Use the MA ribbon (close vs SMA50 vs SMA200, daily) as a regime/direction
   filter for any BTC signal: trade only in the ribbon direction, flat when
   mixed. Keep the plain cross only as a slow context label.
2. Stop spending cloud GPU on 5m deep models: v19-v44 and R75-R81 produced no
   accepted candidate, and a small daily ML model had no development skill here.
3. Next pre-registered development question (post-holdout, train/dev only):
   volatility-targeted H4 sizing to bring development DD under 20% while at 1x cap,
   and ribbon-gated entries for the existing intraday execution engine.
4. Forward test: prospective append-only shadow log started 2026-09-24
   (`research/opencode_r82_ma_replication/shadow_log.py` ->
   `artifacts/research/ma_ribbon_shadow/shadow.jsonl`). Each row carries
   `logged_at`; only rows logged within 36h of the bar close are
   `mode=prospective`. The first 998 rows are `backfill` and are not evidence.
   Run it daily. Re-evaluate after at least 6 months or 10 closed trades,
   whichever is later.
