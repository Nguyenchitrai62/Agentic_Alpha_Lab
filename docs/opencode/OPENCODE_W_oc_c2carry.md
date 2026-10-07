# OpenCode task oc_c2carry - account-realistic profile of G2 + carry vs G2-C2 (Chronos tilt) + carry, on Binance and Bybit prices
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_c2carry/` and `tests/test_oc_c2carry.py`.
Print progress every 10 minutes. Descriptive (decision support), no selection. Light job (reuse stored runs; no engine re-run unless a path is missing).

## Inputs
research/tournament/oc_k2carry (copy its analyze_k2carry.py and method exactly; reproduce its G2 / G2 + carry / K2 / K2 + carry numbers first),
the C2 runs of research/tournament/oc_chronos (Binance) and research/tournament/oc_c2bybit (S5 Bybit prices; REF_S5 and C2_S5 runs - find the
stored per-phase equity paths; only if one is missing, rerun that single row via heavy_slot).
## Table
G2, G2 + carry, K2, K2 + carry, C2, C2 + carry - on Binance prices and on Bybit prices (S5): per year, 5y, worst year, most recent year (labelled),
full-path DD, plus the block-bootstrap expectation like oc_k2carry (median %/month, P(month >= 5 %), P(DD > 20 % in a year), P(losing year)).
Vietnamese summary (<= 15 lines): what the owner should expect on Bybit with G2, with K2 and with C2 (all + carry).
