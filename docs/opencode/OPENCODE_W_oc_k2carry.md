# OpenCode task oc_k2carry - account-realistic profile of the two live candidates: G2 + carry vs G2-K2 + carry (on Binance and Bybit prices)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_k2carry/` and `tests/test_oc_k2carry.py`.
Print progress every 10 minutes. Descriptive (decision support), no selection.

## Inputs
- G2 and K2 4-phase hourly equity paths: research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl (G2) and the K2 runs of
  research/tournament/oc_kronoshidden (find the pickle) and research/tournament/oc_k2bybit (S5 Bybit-price runs for REF and K2, if stored;
  else rerun only those two rows via heavy_slot).
- Carry overlay: research/tournament/oc_carrycompound/analyze_carrycompound.py (f = 0.25, compounding on total equity; reproduce its
  5.634 / 16.75 / 16.66 first).
## Table (per year + 5y + full-path DD + worst year + most-recent year, all labelled):
G2, G2 + carry, K2, K2 + carry - each on Binance prices and on Bybit prices (S5). Also the bootstrap expectation of each (stationary block
bootstrap of daily returns, 10-day blocks, 4000 draws: median %/month, P(month >= 5 %), P(DD > 20 % in a year), P(losing year)) like
research/tournament/oc_mcdd. Vietnamese summary (<= 15 lines) of what the owner should expect on Bybit with and without K2.
