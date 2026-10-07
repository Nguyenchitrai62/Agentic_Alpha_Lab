# OpenCode task oc_usdtdepeg - USDT-USD dislocation snap-back sleeve (idea B9 of docs/opencode/IDEAS_20261007c.md)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_usdtdepeg/` and `tests/test_oc_usdtdepeg.py`.
Read idea B9 in docs/opencode/IDEAS_20261007c.md and the closed USDT-premium items in docs/CLOSED_DIRECTIONS.md (oc_usdtprem, oc_usdtdip,
oc_usdtshort) first - this sleeve trades the stablecoin itself, not a tilt of the majors.

## Data
`data/raw/coinbase_usdt_20261006/` (Coinbase USDT-USD candles; check granularity, coverage 2021-09-24 .. 2026-09-23, gaps). Use 1h closes for
signals; if 1m or 5m data exist use them for fills, else fills on the next 1h bar's low/high (trade-through, strict).

## Rule (fixed; only these variants)
- E1: when a 1h close of USDT-USD < 0.9975, place a limit BUY of USDT at (close - 0.0001), valid 4 h; exit with a limit SELL at 0.9995 (TP),
  stop (market) at 0.9900, else exit at the end of the 72 h holding cap at the bar close (taker). One position at a time.
- E2: same with trigger 0.995, TP 0.999, stop 0.985.
- Costs: Coinbase-like maker 0.0002 per side for limits (labelled; Coinbase Advanced retail fees are higher - add a second row with 0.004 / 0.006
  maker / taker as the retail stress row), taker 0.00055 on stops / cap exits.
- Size: 5 % of total equity per position (sleeve), P&L added to the G2 account path (A(t) = A(t-1)(1 + r_bot) + dSleeve, see
  research/tournament/oc_carrycompound) - report standalone event table first.
- Placebo: same number of entries at random hours with the same exits (200 draws).

## Report
Events per year, win rate, mean net bps per event, worst event, standalone sum; overlay effect on G2 (expected tiny: say how tiny in pp/month);
placebo percentile. Vietnamese 3-line verdict. Honest: if events < 10 in five years, say the sleeve is untestable.
