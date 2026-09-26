# Hidden-year program (vf) results — living document, started 2026-09-24

User protocol (2026-09-24): train/select on all real data before the hidden
year, hide only the most recent year (2025-09-24..2026-09-23, real Binance
USD-M BTCUSDT data), replay it bar by bar. Leader (Claude Code) owns modelling
decisions; OpenCode workers build feature studies and audits.

Code: `src/agentic_alpha_lab/research_vf.py` (selection strictly before the
anchor with a 10-day embargo; risk scale k = min(cap, 0.20 / training intrabar
DD) floored to 0.05), `src/agentic_alpha_lab/vf_families.py`,
`src/agentic_alpha_lab/backtest/portfolio.py` (fractional target engine; agrees
with ma_ribbon.backtest within 0.02 pp), `scripts/vf_lab.py` (leaderboard
`artifacts/research/vf/leaderboard.csv`), `scripts/replay_hidden_year.py`
(truncated-data replay). Secondary robustness view: the same procedure for five
real anchors 2021..2025 with expanding training windows (`--multi`).

Acceptance (hidden year): net > 0 under stress and intrabar DD <= 20%.
Multiple testing: about 45 configurations/families have now been scored on the
same hidden year (including pattern_lab r1-r4). Treat any single pass with
caution; robustness across the five real years is required before promotion.

## Leaderboard (4h, hidden year; stress = 0.06% fee + 0.05% slippage per fill)

| Family | Hidden-year normal / stress | DD | Stress-positive years (5 real years, expanding) |
|---|---|---|---|
| combo: EMA20/200 ribbon long + Donchian 55/10 L/S, 50/50, k=0.65 | +13.0% / +8.1% | 9.0% | 5/5 (CAGR 7.8%, worst-year DD 26.4%) |
| ML overlay (HGB 2-day forward return > 0 on trend book), k=1 | +21.1% / +12.9% | 9.4% | ablation: gain not robust (beats trend 2/5 years) |
| trend_long (4h ribbon, daily gate) | +11.1% / +4.9% | 10.7% | 4/5 |
| donchian long/short | +9.9% / +7.5% | 11.9% | 4/5 |
| rotation between books | +12.0% / +7.4% | 9.1% | 3/5 |
| trend_hyst (EMA band 0.5%) | +10.7% / +7.5% | 8.1% | 3/5 |
| breadth overlay (alt funding crowding) | = trend_long (no event in hidden year) | | 4/5 (event found in-sample) |
| multibook subset selection | +4.6% / +1.0% | 9.9% | 5/5 |
| trend_funding, trend_trail | = trend_long (filters never triggered) | | 3/5, 4/5 |
| vol_managed, ensemble, trend L/S, pullback, donchian long | fail | | |
| 1h and 1d versions of trend/donchian/combo | fail or < 5% | | |
| OI-surge continuation (1h, W5) | -21.4% / -36.1% | 31.9% | fail: dev edge vanished |
| Buy and hold | -32.8% | ~59% | |

Replay check: combo replayed on 2,190 truncated 4h bars matched the vectorized
target with 0 mismatches (`artifacts/research/vf/replay/`). Mean exposure 17.8%.

## Feature studies (dev-only event studies, BH-FDR q<0.1, n>=30, half-stable)

Candles 5/264 (~cost), chart 0/212, indicators 2/168 (Bollinger breakout
continues), seasonality 1/236 (flips yearly), alt breadth 4/32 (alt funding
crowding short +91 bps/12h, n=68; BTC-alt divergence works reversed),
positioning 2/48 (1h OI-surge continuation; failed hidden year).

## Prospective log

`scripts/advisor_shadow.py` logs `pattern_lab_r4_R0_scaled_0.65` and
`vf_combo_fast20_don55_10_w0.5_k0.65` per closed 4h bar with `logged_at`.

## Update 2026-09-24 (later)

- Independent blind audit (OpenCode W9, `research/vf_audit/`): reproduced combo
  from a text specification to < 0.001 pp (145/145 target changes identical)
  and found no look-ahead in `research_vf.run` selection or scaling.
- Parameter neighbourhood (288 combo configs around the selection, fixed k=0.65):
  hidden-year stress net positive for 74%, median +3.2% (p10 -2.6%, p90 +9.6%),
  median DD 11.9%. The selected +8.1% includes favourable luck; expect roughly
  +3-5% under stress costs for this family in a year like the hidden one.
- Risk dial (combo, k from training DD): DD target 15/20/25/30/40% gives hidden
  year +10.0/+13.0/+15.9/+19.8/+25.5% normal and 5-year CAGR 10.9/14.1/17.3/20.5/25.7%;
  3% monthly is not reached even at 40% DD.
- Deep sequence model (TCN+GRU, BTC+10 alts+funding, local GPU, expanding
  anchors): hidden-year IC 0.001 (2-day) and -0.009 (7-day). Rejected.
- ML overlay with all new sources (positioning, breadth, macro, DVOL,
  seasonality; up to 327 features): mean effect vs trend book -0.7 to -6.8 pp per
  year. Rejected.
- Macro module fix: calendar misalignment blanked 200-day windows in 2025-2026;
  now forward-filled per asset (causal). DVOL (W8): 0/48 stable events.
- Execution realism (hidden year, 527,101 real 1m bars, 145 combo target changes):
  a limit order at the 4h open price was traded through (conservative fill, no
  queue assumption) within 15 minutes for 97.9% of changes, median 0 minutes;
  the rest filled at market after 15 minutes (+20 bps each). Net extra cost vs
  the "normal" scenario: ~0.2% per year (immediate market orders: ~2.6%).
  Realistic combo hidden-year net is about +12.8%; the stress scenario
  (0.06% fee + 0.05% slippage per fill) is pessimistic for this execution.
- 5-coin basket (BTC/ETH/BNB/SOL/XRP) and BTC+ETH versions: lower DD but lower
  and less consistent returns than BTC alone. Not adopted.
- CME gap belief: gaps >1% "filled" within 5 days 69% (dev) / 77% (hidden), but
  fading the gap for 24h lost 54 bps per trade in dev (hit 48%). No edge.
- Honest family selection without the hidden year: ranking 15 families by mean
  Sharpe over the four earlier real out-of-sample years (2021-2025, expanding
  windows) selects `breadth` (trend_long + alt funding-crowding overlay):
  hidden year +11.1% normal / +4.9% stress, DD 10.7%. Rank correlation between
  pre-period Sharpe and hidden-year return across families is 0.12: the trend
  variants have similar expected value and the winner is not identifiable in
  advance. Realistic expectation for the family: about +5% to +13% per year at
  k~0.65 with DD ~10% in a year like the hidden one.

## Extended history (2017-08 spot prefix) — current lead

`research_vf.load_context_extended` prefixes Binance spot BTCUSDT 4h/1d bars from
2017-08-17 (synthetic flat long funding 0.0001/8h in the spot period). Longer
training raises training DD (2018 crash), so k falls to 0.4-0.65.

Honest selection over 15 families using only the four real years before the
hidden year (both "best mean Sharpe" and "no losing stress year, DD<=20%, then
Sharpe") picks `breadth` = combo base (4h EMA20/200 ribbon long + Donchian 55/10
L/S) with the alt-breadth overlay (BTC-alt divergence followed long for 3 bars;
alt funding-crowding short never fired in the hidden year), k=0.5:

| | Hidden year | Prior 4 real years |
|---|---|---|
| Normal / stress | +12.0% / +7.8% | mean Sharpe 1.32, worst stress year +1.5% |
| Intrabar DD | 6.1% (stress 7.4%) | max 12.8% |
| Realistic execution (1m limit simulation) | ~+11.6% (97.4% limit trade-through) | |

Full truncated replay: 2,190/2,190 bars, 0 mismatches, 154 position changes.
Caveats: the overlay events were discovered by W6 on 2019-2025 data, so the
prior-year numbers are partly in-sample; the hidden year is clean. The overlay
adds only +1-2% over the combo base at the same scale (+10.0% / +6.3%).
Rank correlation of prior-year Sharpe vs hidden-year return across families
with extended history: 0.17. Added to the forward tournament as `breadth_ext`.
