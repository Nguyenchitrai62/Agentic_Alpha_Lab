# Forward scorer: realistic costs (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)

User rule (2026-09-26): evaluation must match live trading as closely as possible.

Write only: `scripts/forward_scorer.py` and `tests/test_forward_scorer.py` (both exist; extend them). Do not edit any
other file. Keep the current output as the `legacy` block of each candidate (so old numbers stay comparable) and add a
`real` block computed with the rules below. Public REST only (no keys, no orders).

Rules for the `real` block (same as the research engine
`research/parallel/rounds/parallel-20260906-r2/engine_real/engine_real.py`, read it but do not edit it):
1. Execution of each weight change of a perp symbol for a decision at bar close T (next bar opens at T + 1 ms): fetch
   Binance USD-M 1m klines for [T, T + 16 min). p0 = open of minute 0, lo/hi = min low / max high over minutes 2..14,
   p15 = open of minute 15. Buy: if lo < p0 * (1 - 0.001) fill at p0 * (1 - 0.001) with fee 0.0002 (maker), else fill at
   p15 * (1 + 0.0002) with fee 0.0005 (taker). Sell symmetric (hi > p0 * 1.001 -> p0 * 1.001, fee 0.0002; else
   p15 * (1 - 0.0002), fee 0.0005). Cost of the change relative to p0 = |dw| * fee + dw * (fill/p0 - 1) (buy dw>0).
   The position then earns returns from p0 onwards (i.e. use the 4h open series as before, fills measured vs p0).
2. Spot legs (`spot_weight`): Binance spot fee 0.001 per unit of weight change (taker), no offset.
3. Funding: actual Binance USD-M funding (`/fapi/v1/fundingRate`, public) per symbol; a settlement at time S is paid
   by the perp weight held at S (long pays a positive rate, short receives it; negative rates reverse). A weight
   decided at T is held from T + ~15 min, so a settlement exactly at T + 1 ms (bar open) is paid by the PREVIOUS weight.
   Replaces the flat long-only 0.00005 per bar.
4. Minimum order notional at a 10,000 USDT account (BTCUSDT 100, ETHUSDT 20, others 5 USDT): a change smaller than the
   minimum that does not close the position is not executed (keep the previous weight for that symbol).
5. Unpriced bars (1m data not yet available) are skipped, as today.
Also report, per candidate in `real`: gross, execution cost, funding, net, max DD, maker share of fills.
Tests (no network, synthetic klines/funding): maker vs taker branch and price, funding sign and timing at a settlement
at the bar open, min-notional skip, spot fee. Run `.venv/Scripts/python.exe -m pytest tests/test_forward_scorer.py`.
