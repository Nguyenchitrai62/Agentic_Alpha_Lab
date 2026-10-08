# OpenCode task oc_ideascan5 - 10 NEW pre-registerable ideas the program has not tested (2024-2026 literature + this program's evidence)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `docs/opencode/IDEAS5_20261008.md`. No code, no engine. Print progress every 10 minutes.

## Inputs (read them; do not repeat anything closed)
docs/CLOSED_DIRECTIONS.md (all sections), docs/FRONTIER_MAP_VI.md, docs/opencode/IDEAS4_20261007.md and IDEAS_20261007c.md, memory of the program in
docs/NEXT_AGENT.md / docs/CONTINUOUS_RESEARCH.md. Key facts: the return comes from a 4h dip-limit ladder (maker bids on 1m trade-through, TP limit,
stop market, time exit) plus a 4h book; majors only (BTC ETH SOL BNB XRP); gate costs maker 0.0002 / taker 0.00055, longs pay 0.0001 per 8h,
shorts earn nothing; the vol / foundation-model dip-size tilts help outside crash regimes (oc_presampletilt, oc_voltilt); MANUAL lacks entry edge.
You may use web search for 2024-2026 papers / practitioner notes on crypto liquidity provision, limit-order mean reversion, liquidation cascades,
order-flow toxicity, volatility forecasting for market making.

## Output (<= 120 lines)
10 ideas, each: mechanism (why it should earn), exact causal rule with at most 2 pre-registered variants, data needed (must exist locally or be
public and free), which existing harness would test it (engine / dip replica / MANUAL harness), expected effect size and a prior probability,
and the leakage traps. Rank by expected value / cost. Mark clearly any idea that is a near-duplicate of a closed direction and drop it.
