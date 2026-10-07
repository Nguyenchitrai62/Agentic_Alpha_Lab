# OpenCode task oc_tailhedge - protective BTC puts so the dip sleeve can run larger at the same DD
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_tailhedge/` and `tests/test_oc_tailhedge.py`.

## Why
G2's drawdown is set by a few crash events (2024-01-03 one-bar multi-coin dip-stop cascade, 2022 LUNA/FTX, 2024-08-05). Every DD overlay so
far (breakers, caps, budgets) moved along the same return-DD frontier because it removed exposure. A long put is different: it pays exactly in
those events. If the premium cost is smaller than the extra return of a larger dip sleeve (G2K20 = dips x2.0: 5.87 %/month at yearly DD 17.79
vs G2 5.41 / 16.91), the frontier moves. Options have never been traded here.

## Data
- IV: `data/raw/deribit_opt_20260926/BTC_options_4h.parquet` (`bar` = 4h bar start UTC, `iv_otm_put` in vol points; a bar's value is known at
  bar start + 4h); fallback Deribit DVOL hourly (`data/raw/deribit_dvol_20261005`).
- BTC Binance USD-M 1m klines (find the files; see other folders' code, e.g. research/tournament/oc_carrycompound).
- G2 4-phase hourly equity: `research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl` (`R2B1D17BFG2`); G2K20: the v422 runs in
  `research/parallel/rounds/parallel-20260906-r2/v422/` (find the strategy key with dips x2.0 + G = 2.0; reproduce its published 5.87 / 17.79
  first). Load exactly as research/tournament/oc_carrycompound/analyze_carrycompound.py does.

## Rule (fixed before running)
- Instrument: BTC European put, monthly expiry = last Friday of the month 08:00 UTC. Buy at 08:05 UTC on the previous monthly expiry day (roll),
  choosing the expiry that is >= 21 days away. Strike K = S * (1 - m) rounded DOWN to 1000. S = 1m close at 08:04.
- Buy price = BS put (r = q = 0) with sigma_buy = 1.05 * iv_otm_put / 100 (last bar whose close <= entry) + skew add-on (fixed): +0.05 for
  m = 0.15, +0.10 for m = 0.25. Fee per side min(0.0003 * S, 0.125 * option price) per unit.
- Size: units = h * E / S at entry (protects h x equity of BTC exposure), E = current total equity. Premium paid from equity.
- Mark: hourly, BS with sigma_mark = 0.95 * latest KNOWN iv_otm_put / 100 + the same skew add-on, remaining T. Two DD views:
  conservative = hedge marked at the hourly CLOSE; optimistic = hedge marked at the hourly LOW of BTC (labelled: assumes the G2 equity minimum
  and the BTC low coincide).
- TP (monetise a crash): if mark >= 5 x entry premium, sell at the mark minus fee and immediately buy a new put with the same m (expiry >= 21 d).
  Otherwise hold to expiry: payoff max(K - S_settle, 0), S_settle = mean of BTC 1m closes 07:30..07:59 on expiry day; settlement fee
  min(0.00015 * S, 0.125 * intrinsic). (A long put's maximum loss is its premium = its stop.)
- Rows (choose on dev4): for m in {0.15, 0.25} and h in {1.0, 2.0}: G2+H(m,h) and G2K20+H(m,h); plus G2 and G2K20 alone.
- Overlay on total equity: A(t) = A(t-1) (1 + r_bot(t)) + dHedge(t) (the BOT sizes on total equity, hedge value included).

## Evaluation
Per dev year: 4-phase reset metric (%/month), yearly DD (conservative and optimistic), full-path DD, hedge cost per year (premium + fees -
payoffs), hedge payoff in the top-5 G2 DD episodes (dates). Key question in bold in REPORT.md: does any G2K20+H row beat G2 on dev4 mean AND
have yearly / full DD <= G2's (conservative view)? Choose with the robust criterion; score the most recent year once for the chosen row and G2.
Caveat paragraph: aggregated OTM IV + fixed skew add-on is not a strike-level quote; deep-OTM puts trade wider; Bybit lists BTC options
(USDC-settled) - say whether monthly 15-25 % OTM strikes are typically listed there (public instruments endpoint, read-only GET allowed:
https://api.bybit.com/v5/market/instruments-info?category=option&baseCoin=BTC).
