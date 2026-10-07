# OpenCode task oc_presampleflow - do the deployed book's member FAMILIES (whale flow, Coinbase premium) have skill before 2021?
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_presampleflow/` and `tests/test_oc_presampleflow.py`.
Print progress at least every 10 minutes. Heavy steps via heavy_slot.

## Why
oc_bookattrib: G2's book return is TIMING (placebo pct >= 96.8 every year 2021-2025). oc_presamplebook: a TV-only member has ~0 OOS IC, so
the timing comes from the other members: whale flow (A/Aq, v236/v240 order-level flow) and the Coinbase premium (D/Dq, v285). oc_memberdrop:
either family alone keeps G2. Their skill was only ever measured on 2021-2026. Data for a never-used test exist: Binance SPOT order-level
1m flow store data/raw/aggflow_spot_20260929_orders_1m (BTC/ETH/BNB from 2017-08/11, XRP 2018-05; read its docs / producing script) and
Coinbase BTC-USD / ETH-USD 1h from 2017-08 (data/raw/coinbase_20260925, manifest.json). Spot 1m prices: data/raw/spot_1m_presample_20261007.

## Members (copy the feature code UNCHANGED; never edit the originals)
- FLOW: the order-level whale-flow features of the deployed A member (find them: research/parallel/rounds/parallel-20260906-r2/v236/
  flow_features.py, v240 (order-level variant), and how research_books_d2 / pipe_setup build members A/Aq). Compute them from the SPOT store
  for the pre-sample (the research years used PERP flow - disclose the venue difference; also compute spot-flow features on 2021-2025 so the
  reference uses the SAME spot construction).
- PREMIUM: the Coinbase-premium features of the D member (v285 / scripts/v285_cb_advisor.py): Coinbase BTC-USD / ETH-USD vs Binance spot
  BTCUSDT / ETHUSDT (SOL/BNB/XRP use BTC's premium as the deployed code does - check).
- Model and label exactly as those members (copy hyper-parameters and the label definition; pooled HGB as deployed).

## Test (descriptive generality; NOT a deployment change)
Walk-forward anchors: 2019-03-01 (train 2017-10..2019-02), 2019-09-24, 2020-03-01 (truncated at 2020-09-23) on spot; reference anchors
2021-09-24 .. 2024-09-24 with the same spot-built features. For each member (FLOW, PREMIUM, and the 0.8/0.2-style blend the deployed book uses
- confirm weights from the code): pooled + per-coin Spearman IC vs the realised label per year with block-42 bootstrap CI, sign hit rate,
in-sample IC (positive control), and the vectorised diagnostic P&L of oc_presamplebook (labelled, not the engine). Key question in bold:
do the deployed member families show positive OOS IC in the pre-sample years like (or unlike) the research years? Vietnamese 3-line verdict.
