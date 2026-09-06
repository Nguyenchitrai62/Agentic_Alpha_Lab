# BTC research v36–v39 — 2026-09-06

## Decision

No candidate meets the registered gate of calendar-geometric net at least 5%
per month, global drawdown at most 20%, and at least 30 fills in every normal,
fee-stress, and execution-stress scenario. All four rounds are research-only;
there is no live approval.

The rounds use the v4 development data and the existing continuous chronology:
4,076 decisions over 2023-06-01 through 2026-03-23, 2.809092589 years,
730-day past-only windows, and an 8-day label embargo. All opened dates remain
development data, not an independent test. Full gross PnL, fees, funding, net
PnL, rejection counts, and execution diagnostics are persisted in each JSON
summary below.

## Results

The compact entries are `net / drawdown / monthly-geometric-net / fills`.
Negative drawdown means a loss from the sampled equity peak.

### v36 — nonlinear action classifier

The causal HistGradientBoosting classifier produced 135 signals (3.312%
coverage). Its best row was 1x normal: `+14.922% / -30.303% / +0.413% / 79`;
fee stress was `+8.719% / -31.246% / +0.248% / 79`, and execution stress was
`+10.287% / -27.640% / +0.291% / 68`. At 0.5x it remained only `+0.254%`
monthly in normal conditions. ExtraTrees was negative at both exposures.

Source: `artifacts/research/v36_nonlinear_action_probe/summary.json`.

### v37 — confidence leverage

This read-only probe kept immutable v30 isotonic signals and changed only
per-signal leverage, capped at 2x. The fixed 1x reproduction was
`+122.798% / -20.086% / +2.405% / 65` normal and
`+112.963% / -20.473% / +2.268% / 65` under fee stress; execution stress was
`+92.890% / -18.318% / +1.968% / 56`.

The fixed formula `1.0 + clip((score-0.3)/1.7, 0, 1)` reached only `+2.990%`
monthly normal and exceeded the drawdown gate at `-21.659%`; fee stress was
`+2.816%` monthly with `-22.076%` drawdown. The two >1x formulas could not be
run through execution-stress because the current engine intentionally rejects
exposure above 1x without a validated liquidation model. They are therefore
not candidates.

Source: `artifacts/research/v37_confidence_leverage_probe/summary.json`.

### v38 — causal frequency policy

The v30 score was held fixed while the cooldown/cap was changed by a
pre-specified sensitivity matrix. The original 5-day/4-signal policy reproduced
v30. No variant improved the result: cooldown 3/cap 8 reached only `+1.547%`
monthly normal with `-23.532%` drawdown; cooldown 2/cap 8 reached `+1.454%`
with `-21.585%`; cooldown 1/cap 12 reached `+1.414%` with `-22.281%`.

Execution-stress monthly returns for those variants were respectively
`+0.869%`, `+0.981%`, and `+0.664%`, with 83, 80, and 84 fills.

Config: `configs/swing_v38_frequency_policy_probe.json`.
Source: `artifacts/research/v38_frequency_policy_probe/summary.json`.

### v39 — shared HGB net/fill regression

The causal context-plus-candidate HGB regression was evaluated with two fixed
leaf sizes. `leaf128` at 1x returned `+0.584%` net, `-28.611%` drawdown, and
only `+0.017%` monthly normal; fee stress was `-6.114%` net and execution
stress `-4.261%` net. `leaf32` at 1x returned `+2.746%` net with
`-35.897%` drawdown and only `+0.080%` monthly; fee and execution stress were
negative. The 0.5x rows stayed below 0.1% monthly and did not pass fee stress.

Config: `configs/swing_v39_shared_hgb_probe.json`.
Source: `artifacts/research/v39_shared_hgb_probe/summary.json`.

## Provenance and blocker

The exact summary hashes are:

- v36 summary: `2F0255A807E78B03775BFB6BCF823B30F2BB5D43068DE1B8053A4A943CDC4969`
- v37 summary: `8270D5B2E5C623FF9567EDE14F8E35C6831614E7740CF284FBFD23F47352D440`
- v38 config: `E27EAEF3E2E332302C9FA8A2AB4828D82C8B9196915CF12C822EC7529D51920E`
- v38 summary: `7E5A173F27C017F845FFA4E3FBA5D4A29420207D614244BE47AB719238051C5C`
- v39 config: `666EC2F7CD7B0437E4B0E58D4A2A540A13989AAC03B8D54D2A5FACC250D464F1`
- v39 summary: `09954CF5AA5752AE63B02F1B1D08ECF1CB6ECE78F3D0A6C0D6B055DB5BF46CDA`

V33 remains the only unrun materially different heavy hypothesis. Its package
was prepared for one private Kaggle run, but the upload was rejected by the
execution approval boundary because it would send internal BTC research source
and data to Kaggle. The inventory check found no v33 dataset or kernel, and no
package data was uploaded. The package archive SHA-256 is
`915f89e4476684646f11f44895830ec6d0eadd54b21e504b94ff27287e58766f`.

Further progress on the registered heavy hypothesis requires explicit user
authorization for that private Kaggle upload. Do not work around the boundary
through a browser or another transport. Until then, local heavy training and
execution-stress >1x validation remain out of scope under the repository rules.
