# oc_capacity REPORT — G2 per-order notional vs Binance order-book depth (2026-10-07)

RESEARCH ONLY, no selection, no orders. Prior-work grep (`capacity|size impact|bookdepth`
over `research/`): no previous per-order notional-vs-depth capacity study exists.
`v385_bot_depth_sizing.py` sizes dip rungs by depth (signal, not capacity),
`oc_depthtilt` is a depth tilt, `oc_spreadcost` measures quoted spread only,
`research/diagnostics/newdata_bookdepth` screens depth as a fill-outcome signal.

## Rule (stated up front in `capacity.py` docstring before running)

G2 = v421 `R2B1D17BFG2` from `research/tournament/oc_kpi_g2/events_s{0..3}.parquet`
(4h-close equity matches `v421_runs.pkl` to 1e-9) + `barsum` phase-equity index.
Every liquidity-consuming order (entries `rung_fill/book_fill/book_add`, all exits)
with `2023-01-01 <= t < 2026-09-24` is joined to the last bookDepth snapshot with
`ts` strictly before `t` (lag <= 5 min). Depth `D` = relevant-side notional within
1% of mid (`ask_n1` buys, `bid_n1` sells). The archive has ONLY 1%/2%/5% bands, so
"within 0.2%" is proxied as `D02 = D/5` (uniform density = conservative lower bound;
true touch-concentrated depth is deeper, hence D02 shares are upper bounds).
`notional(E) = |weight| * eq_idx(t) * E/4` (weight = fraction of phase equity,
`eq_idx` = indexed phase equity, /4 = four sub-accounts). Conservative haircut,
ONLY for orders with `r = notional/D > 5%`: maker entries get fill prob
`p = 0.05/r`, missed P&L `(1-p)*max(profit,0)` (rung `ret*w*eq`, book episode profit
pro-rata; TP/timeout exits untouched to avoid double counting); stop exits pay
`0.5*Bybit_p90_spread*notional` (oc_spreadcost halves: BTC 0.0059 / ETH 0.019 /
SOL 0.42 / BNB 0.64 / XRP 0.33 bps). Drag pp/month = H/months over the 44.75-month
depth window; adjusted ~= 5.41 - drag; "material" = drag >= 0.5 pp.
POST-HOC FIX (logged in script): side prints below that side's 0.5th percentile
(stale near-zero prints, min $8-$71) are treated as missing (1618 orders), not floored.

## Coverage

44,122 G2 orders in window; 41,981 matched (95.1%), 2141 lag-unmatched, 1618 bad-print.
Median 1% depth (total / one side, USDT): BTC 271M/136M, ETH 117M/59M, SOL 29M/15M,
BNB 11.4M/5.7M, XRP 14.4M/7.2M. Median order is 0.0005% of D at 10k, 0.24% at 500k.

## Per-order size vs depth: share of orders above 1% / 5% / 20% of D (exact 1% band)

| equity | >1% | >5% | >20% | makers>5% | stops>5% | drag pp/mo | adj. %/mo |
|---|---|---|---|---|---|---|---|
| 1k | 0.06% | 0.03% | 0.00% | 13 | 0 | 0.08 | 5.33 |
| 5k | 0.14% | 0.06% | 0.03% | 24 | 0 | 0.20 | 5.21 |
| 10k | 0.26% | 0.07% | 0.04% | 26 | 0 | 0.22 | 5.19 |
| 50k | 2.41% | 0.26% | 0.08% | 50 | 4 | 0.34 | 5.07 |
| 100k | 5.81% | 0.67% | 0.14% | 135 | 14 | 1.07 | 4.34 |
| 500k | 25.5% | 5.81% | 0.99% | 1278 | 58 | 15.1 | neg |

D02 proxy (upper bound): >5% share = 0.06% / 0.14% / 0.26% / 2.41% / 5.81% / 25.5%
at 1k..500k. Binding venue first: BNB (thinnest book; max r at 50k = 7.8x),
then XRP; BTC never binds below 500k (max r at 100k = 0.4%). Stop-cost leg is
negligible everywhere (sub-bps half-spreads); the haircut is all missed maker fills.

## Verdict

Up to **50k USDT** the G2 result (~5.4%/mo) is NOT materially reduced by size
(drag 0.34 pp, adj 5.07; <= 10k drag <= 0.22). At 100k the haircut turns material
(1.07 pp, adj 4.34); at 500k the replay breaks down (25% of orders above 1% of
depth, 1278 makers impaired). All five years are research data; needs prospective
validation. Repro: `research/tournament/oc_capacity/capacity.py -> results.json`;
test `tests/test_oc_capacity.py`. LIGHT (one depth symbol at a time, no heavy slot).

## Caveats

Single-print depth overstates impact for resting limits (they see average depth);
profit attribution mixes time bases (book legs converted by own-time eq index);
drag is subtracted from the 5y mean as an approximation (depth covers 2023+ only;
pre-2023 orders are small notionals anyway); D02 is a uniform-density proxy.
