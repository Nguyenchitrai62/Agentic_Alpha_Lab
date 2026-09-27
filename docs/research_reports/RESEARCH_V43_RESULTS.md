# BTC research v43 — 2026-09-06

V43 combined the strongest v42 filter (7-day holding horizon) with fixed
expected-net score tiers over immutable, causal v30 selected signals. It did
not produce a candidate.

The best variant was `holding_7d_score_0.3`: 1x normal returned
`+137.850% / -12.644% / +2.604% / 43` (net / DD / monthly geometric net /
fills), fee stress returned `+130.910% / -12.892% / +2.514% / 43`, and
execution stress returned `+99.566% / -15.531% / +2.071% / 39`. Raising the
score threshold to 0.5% reduced execution stress to `+1.784%` monthly with
30 fills. Thresholds 0.75% and 1.0% had only 18 and 10 fills respectively.
The 0.5x rows were lower and also missed 5% monthly. Gross PnL, fees, funding,
coverage, rejection counts, and all scenario diagnostics are in the JSON.

Data/protocol: 4,076 continuous decisions, 2023-06-01 through 2026-03-23,
2.809092589 years, 730-day past-only windows, 8-day label embargo, and no
independent test claim. No live approval.

Config: `configs/swing_v43_horizon_score_probe.json`.
Summary: `artifacts/research/v43_horizon_score_probe/summary.json`.
Config SHA-256: `5B8515488561184882574A96868726F78D1E92A4729F1060E67B419DD4A6AF9B`.
Summary SHA-256: `6E8936742C5FD638726AE25FB2D1C76E3C521FC87DB7AB049416AFE75DE9200D`.

The next unrun heavy hypothesis remains the packaged v33 action-margin GRU.
Its private Kaggle upload is still pending explicit authorization because the
package contains internal BTC research source/data; no upload occurred.
