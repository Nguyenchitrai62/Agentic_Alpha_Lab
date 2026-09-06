# BTC research v40–v42 — 2026-09-06

## Decision

No v40–v42 variant meets the registered gate of calendar-geometric net at
least 5% per month, global drawdown at most 20%, and at least 30 fills in every
normal, fee-stress, and execution-stress scenario. These are research-only
diagnostics over the already causal and audited v30 output; no live approval is
implied.

The common evaluation contains 4,076 continuous decisions from 2023-06-01 to
2026-03-23 (2.809092589 years), using 730-day past-only training windows and an
8-day label embargo. All opened dates remain development data. Each JSON
summary persists gross PnL, fees, funding, net PnL, drawdown, fills, coverage,
and execution diagnostics.

The compact entries below are `net / drawdown / monthly-geometric-net / fills`.

## v40 — score tiers

Immutable v30 calibrated predictions were rerun with fixed expected-net gates,
while keeping the 5-day cooldown, 4-signal monthly cap, and candidate geometry.
The baseline threshold 0.3% reproduced v30. The best higher tier with at least
30 execution-stress fills was threshold 0.75%: at 1x it reached
`+18.612% / -13.381% / +0.508% / 32` in execution stress; normal was
`+32.085% / -13.166% / +0.829% / 34`, and fee stress was
`+28.999% / -13.350% / +0.758% / 34`. Higher thresholds lost the 30-fill
requirement or produced lower returns.

Config: `configs/swing_v40_score_tier_probe.json`.
Source: `artifacts/research/v40_score_tier_probe/summary.json`.

## v41 — cross-timeframe HGB

The 40 causal context features were expanded only with cross-timeframe
mean/std/min/max, absolute mean, and adjacent-frame differences. Shared HGB
net/fill regressors were fit in every chronological fold. The better `leaf32`
variant at 1x reached only `+29.619% / -23.353% / +0.773% / 96` normal,
`+21.200% / -24.482% / +0.572% / 96` fee stress, and
`+14.583% / -24.509% / +0.405% / 86` execution stress. `leaf64` was worse.

Config: `configs/swing_v41_crossframe_hgb_probe.json`.
Source: `artifacts/research/v41_crossframe_hgb_probe/summary.json`.

## v42 — direction and holding horizon

Fixed filters over immutable v30 selected signals tested direction and the
3-day/7-day candidate horizon. The best was `holding_7d`: 1x normal
`+137.850% / -12.644% / +2.604% / 43`, fee stress
`+130.910% / -12.892% / +2.514% / 43`, and execution stress
`+99.566% / -15.531% / +2.071% / 39`. The safer long-only variant reached only
1.563% monthly in execution stress. The 3-day variant was negative and the
short-only variant had only 18 execution-stress fills.

Config: `configs/swing_v42_direction_horizon_probe.json`.
Source: `artifacts/research/v42_direction_horizon_probe/summary.json`.

## Provenance and next action

Exact hashes:

- v40 config: `3B53BCF7109FF5A5A99EE965A831D38185CED5ED3BEC74FE08B2AB58B1F91EC5`
- v40 summary: `CF38FF6AA71B2366026DD48C68D6DD268708642B294998AB601DFED9B6EDC94E`
- v41 config: `08C7AA40D840F11AFFB60BC57F1701A55CACDC1B5DA8638042A3014CF365CDF8`
- v41 summary: `B377ADB9BC669EA8BC0EF1B2E8210D165C2932094B89E5C82FCCDBA76452D9B4`
- v42 config: `2F16DEC6C8DCA08DFCC0102A3E3FE73CB11275D644D4087B14B42C3A26DD6120`
- v42 summary: `C95D89A6A9A5B63FD15617C403AA8AF6CC7E315082FD9F8A421A3850DAE6967A`

The next materially different heavy hypothesis remains the packaged v33
action-margin GRU. Its private Kaggle upload is still blocked by the approval
boundary because the package contains internal BTC research source/data; no
upload occurred. Explicit user authorization is required before submitting it.
