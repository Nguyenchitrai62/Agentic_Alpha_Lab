# OpenCode task oc_amihudbybit - venue-consistent Amihud tilt: illiquidity from BYBIT volumes, scored on BYBIT prices (POST-HOC LABELLED)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md and docs/opencode/OPENCODE_W_TEMPLATE_BOOKGATE_20261007.md first. Write ONLY
`research/tournament/oc_amihudbybit/` and `tests/test_oc_amihudbybit.py`. Print progress every 10 minutes. Engine via heavy_slot.

## Why (label everything POST-HOC: motivated by seeing A1 fail the Bybit-price stress)
research/tournament/oc_lit_xs A1 (book x (1 + 0.25 z), z = cross-sectional z of trailing-30d Amihud from BINANCE daily |return| / quote
volume) passed dev4, the most recent year and a blind audit, but research/tournament/oc_amihudrobust S5 (Bybit 1m prices) erased the gain
(-0.005) with full-path DD 21.3: it overweights BNB / XRP, which are much less liquid on Bybit (where the owner trades). A venue-consistent
version measures illiquidity where the orders execute.

## Rule (fixed)
AB1: identical to A1 except Amihud is computed from BYBIT daily data built from data/raw/bybit_linear_1m_20261004 (1m linear perps
2021-06-01 .. 2026-10-03; daily |close-to-close return| / daily turnover in USDT - use the turnover column if present, else close x volume;
state which), same 30-day window, same day-availability rule (day D usable from D+1 00:00 UTC), same K, clip and side rules as A1.
Score with the S5 friction (Bybit 1m prices, from 2021-11-15 as in oc_amihudrobust / robust_v421.py) AND with the base engine; reproduce
G2_S5 4.994 dev4 / 4.883 5y and A1_S5 first (oc_amihudrobust numbers) to prove the harness.
Rows: G2, A1 (Binance Amihud), AB1 (Bybit Amihud), CTRL_AB1 (exposure-matched constant). Report dev4 + the most recent year (labelled) +
5y + full-path DD for both price sources. Verdict (Vietnamese 3 lines): does the venue-consistent tilt keep a gain on Bybit prices with
full-path DD <= 20? (Even if yes: post-hoc -> paper evidence only.)
