# Majors-only multi-direction round (mj), 2026-09-25

User: trade only BTC, ETH, SOL and large caps (BNB, XRP); research many directions.
Protocol: select on data before 2025-09-14, trade the hidden year 2025-09-24..2026-09-23.

| Direction | Hidden year | Verdict |
|---|---|---|
| BTC breadth/combo 4h (current lead) | +12% to +13%, DD 6-9% | still best |
| Majors combo portfolio, portfolio-level DD targeting (3 / 5 coins) | +13.0% / +11.5%, DD 10.7 / 14.6% | no gain vs BTC |
| Dual momentum across majors (1d) | +0.4% | fail |
| Volatility squeeze breakout (1d) | -2.5% | fail |
| Per-coin daily trend | -3.7% | fail |
| Opening-range breakout BTC (1m, Asia range -> EU/US) | -6% to -49%; 0/72 dev t>2 | fail |
| Pairs spread (5 pairs, residual MR / ratio breakout) | -10.2% selected; SOL/ETH breakout -12..-20% post hoc | fail |
| Volume-confirmed impulse continuation (W16) | BTC -0.7%, ETH -11.3%, SOL +5.5% | dev t=4.4 but did not persist |
| BTC -> ETH/SOL lead-lag (1-15m) | edge -1.2..+0.03 bps vs ~4 bps cost | none |
| Capitulation-wick reversal (W16) | wrong sign in dev | fail |

Workers: W14 majors 1m/15m/1h data (`data/raw/majors_intraday_20260924`), W15 pairs
(`patterns/pairs.py`), W16 capitulation (`patterns/capitulation.py`, 20-cut causality verified).
Recurring pattern: several statistically strong development edges (OI surge, stablecoin
liquidity, impulse continuation, SOL/ETH ratio momentum) failed in the bearish hidden
year; only trend following with the daily SMA50/200 regime gate survived every test.

## Push toward 5%/month (2026-09-25, later)

All rows: parameters chosen only on data before each anchor (expanding), then the next
real year traded; the last year is the hidden year. Geometric mean over the 5 years.

| System | 5-year geometric | Hidden year | Worst-year DD |
|---|---|---|---|
| Pyramiding trend BTC 4h (Turtle adds, regime gate) | 10.3%/yr | +6.0%, DD 7.3% | 12.4% (5/5 years positive) |
| TSMOM BTC 4h, vol target, daily ribbon gate | 20.9%/yr (1.6%/mo) | +15.8% / +9.4% stress, DD 15.1% | 15.9% |
| Regime-scaled breadth BTC 4h | stress 12.7%/yr | +11.0% / +7.5%, DD 5.8% | 16.4% |
| TSMOM 3 majors, portfolio DD-scaled | ~40%/yr (2.8%/mo) | +17.2%, DD 27.7% | 27.7% |
| TSMOM 5 majors, portfolio DD-scaled | ~42%/yr (3.0%/mo) | +11.4%, DD 27.9% | 33.7% |
| TSMOM 5 majors, portfolio vol target | 50.8%/yr (3.5%/mo) | -5.4%, DD 45.1% | 45.8% |
| TSMOM 5 majors, DD circuit breaker, Calmar selection | 59.1%/yr (3.95%/mo); stress 27.8%/yr | +6.3%, DD 47.2% | 47.2% |

Reading: return comes from the 2023-2024 bull years (+113% to +285% per year at 2-3x gross);
the bearish hidden year gives +6% to +17%. High-average variants carry 30-47% drawdowns.
Choosing the majors list (SOL, XRP) has hindsight. Many design choices were made after seeing
earlier results, so the 5-year averages are optimistic.

## DD-constrained large grid (810 configs, max training return s.t. training DD <= 20%) — rejected

| Universe | 5-year geometric | Worst forward-year DD |
|---|---|---|
| BTC | 12.8%/yr | 47.5% |
| BTC/ETH/SOL | 4.4%/yr | 47.7% |
| 5 majors | 43.4%/yr (3.05%/mo), stress 16.1%/yr | 38.2% |

A training-DD constraint does not bound forward DD when the return-maximizing config is picked
from a large grid (e.g. 2021: training DD 16% -> forward DD 47.5%). The small Sharpe-selected
`tsmom` family inside the 3-book portfolio (2.61%/mo, DD 19.0%, hidden +11.9%) remains the best
result that respects the user's DD <= 20%.

## Independent blind audit (OpenCode W17, `research/mj_audit/`)

Reproduced the 5-major TSMOM 2023-09-24 year from a text spec before reading code:
+188.6% vs leader +192.2%. Gap fully explained by the window end (leader stops at
anchor+364d, spec at 20:00 that day; 5 extra bars); on the same window the numbers match
to 1e-14 per bar. No look-ahead found in signal, volatility, portfolio scale, daily
ribbon join, funding or execution. Note: in that year no grid config met the 20%
training-DD constraint, so the least-penalised one was chosen.

## Portfolio round (2026-09-25, user: continue until 5%/month, DD <= 20%)

- Fast TSMOM (1-7 day horizons, 1h) per major, OOS 2021-2026: Sharpe 0.38-0.97; BTC hidden +18.7%.
- 11 trend books (BTC regime + slow/fast TSMOM x5) + carry, OOS daily streams
  (`src/agentic_alpha_lab/oos_streams.py`, `research/portfolio_v2.py`): mean pairwise
  correlation 0.3; trend group Sharpe 1.22. Inverse-vol weighting across all books is
  dominated by carry (tiny vol) and must not be used. Two-sleeve results with DD <= ~20%:
  70/30 trend/carry L=1: 1.70%/mo, DD 15.0%; 50/50 L=2: 2.44%/mo, DD 20.7%, hidden +13.9%.
- Continuous drawdown control overlay: lowers returns more than risk (hidden ~2%). Rejected.
- Best so far under DD <= 20% remains the 3-book portfolio (regime BTC + majors TSMOM 1.5x,
  carry 3x): ~2.6%/mo OOS, DD 19.0%, hidden +11.9%. Frozen on all data to 2026-09-14
  (`scripts/portfolio_freeze.py` -> `artifacts/research/advisor_shadow/portfolio_v1.json`)
  and logged prospectively as `portfolio_v1_3book` (`src/agentic_alpha_lab/signals/portfolio_advisor.py`).
- Reaching 5%/mo needs ~55% DD with the available books; the binding limit is the Sharpe
  (~1.2-1.6) of trend-type returns. Next: market-neutral sources (cross-exchange funding, W18).
