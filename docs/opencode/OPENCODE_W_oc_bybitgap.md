# OpenCode task oc_bybitgap - where exactly does G2 lose ~0.5-0.6 %/month when run on BYBIT prices (the owner's venue)?
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_bybitgap/` and `tests/test_oc_bybitgap.py`.
Print progress every 10 minutes. Engine runs via heavy_slot.

## Facts
research/tournament/oc_amihudrobust / oc_amihudbybit: G2 dev4 5.601 (Binance 1m prices) vs G2_S5 4.994 (Bybit 1m prices from 2021-11-15,
the robust_v421.py S5 friction), 5y 5.410 vs 4.883, full-path DD 16.82 vs 18.09. Earlier diagnostics (research/tournament/oc_venuegap,
oc_bnbvenue, oc_bookvenue - read their REPORTs): dip-leg drag ~4 % of rung P&L, BNB spread ~10x, "drag NOT in book execution". The owner
trades on Bybit, so this gap is the most direct live cost.

## Tasks (descriptive decomposition; no rule change)
1. Re-run G2 and G2_S5 (reproduce the numbers first) and decompose the difference per year into: book vs dip leg (book-only and dip-only runs
   on both price sources), per coin (leave-one-coin-on: run each coin alone, or attribute fills / exits by coin from the engine records), and
   per component (entry fills missed / extra, exit prices of SL / TP / time exits, funding, vol-scale differences from Bybit-computed
   volatility, governor differences).
2. Price-series diagnostics per coin: Bybit vs Binance 1m close basis (median, p95 |diff| in bps), wick depth differences (minute lows),
   and how often a Binance trade-through is NOT a Bybit trade-through at the rung / limit price (and vice versa).
3. If the gap concentrates in one coin or one component (e.g. BNB on Bybit), say so with numbers and describe - do not run - the obvious
   pre-registrable venue fixes (e.g. exclude that coin on Bybit, wider rung offset there); the leader decides what to pre-register.
Vietnamese 3-line verdict.
