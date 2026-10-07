# OpenCode task oc_ripcont - intrabar continuation sleeve: buy the first pullback after a 4h-bar rip
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_ripcont/` and `tests/test_oc_ripcont.py`.

## Why
research/tournament/oc_rips (read REPORT.md, PLAN.md, backtest.py) sold rips (+k sigma above the 4h open) and LOST in every regime: rip-sell
win rates 51-69 % but negative means (small TP wins, large stop/timeout losses) -> rips tend to CONTINUE. v174 also found that spikes do not
revert. The mirror question was never tested: after a rip, does a limit bid on the first pullback earn (momentum continuation inside the bar)?
It would be a long sleeve that fills in up-moves, i.e. at different times than the dip ladder (diversification), with maker entries.

## Rule (fixed before running; reuse oc_rips' data loading, sigma and exit code where possible)
- Coins BTC/ETH/SOL/BNB/XRP, Binance USD-M 1m klines; 4h bars on four clock grids (shift s = 0..3 h), each clock = 1/4 of the capital
  (as the 4-phase harness). sigma = std of the last 360 4h open-to-open log returns ending at the bar open O (same as the dip ladder / oc_rips).
- Trigger: inside bar [T, T+4h), the first minute m >= 5 with 1m high >= O * exp(+k * sigma).
- Entry: from minute m+1 a resting BUY limit at L = O * exp((k - 1.0) * sigma) (one-sigma pullback), valid until minute 199 of the bar;
  fills on a 1m trade-through (low < L), maker 0.0002. One entry per coin per bar.
- Exits: TP limit at L * exp(+0.75 * sigma) (maker); SL market at L * exp(-1.0 * sigma) (taker 0.00055, filled at the stop price; stop first
  if both touched in one minute); otherwise exit at the next bar open T+4h (taker). Longs pay 0.0001 per 8h settlement crossed.
- Size: notional 0.10 x sub-account equity per fill (fixed); report per-fill net bps and per-year sums.
- Variants: C1 k = 2.0; C2 k = 3.0; C3 = C1 only when the deployed book is long that coin at the bar open (use a causal book-weight source
  available at T, e.g. the v376 / phase_agents book tables or scripts/forward_v205-style live_books used by the G2 harness; if no causal per-bar
  book weight exists for all four clocks, drop C3 and say why - do not invent one).
- Placebo (fixed): for each variant, 200 draws of the same number of entries per (coin, year) at random minutes 5..199 of random bars of the same
  year, with a limit at the minute-open price and the same exits; report the variant's percentile vs the placebo distribution.
- Reference for scale: the mirrored dip numbers in oc_rips REPORT (+11.68 5y sum).

## Evaluation
- Per year (dev4; most recent year only for the chosen variant): fills, win rate, mean net bps per fill, sum, daily-sum DD, TP / SL / timeout
  shares, daily P&L correlation with the dip sleeve (oc_rips mirrored dip or G2 hourly equity).
- PROMISING only if: mean net per fill > +5 bps in >= 3 of 4 dev years, dev sum > 0, placebo percentile >= 95, daily-sum DD < 2 x the dip DD.
- Only if PROMISING: overlay on G2 4-phase hourly equity at notional 0.05 x total equity per fill (A(t) = A(t-1)(1 + r_bot) + dSleeve), report
  4-phase reset metric, yearly and full-path DD vs G2. Labelled as a screen (book/dip engine not modified).
