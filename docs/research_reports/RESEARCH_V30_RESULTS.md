# v30 causal calibration of v29 — completed 2026-09-06

## Decision

Keep v30 as a development diagnostic, not a target candidate. It was a
read-only, pre-registered calibration probe over v29 predictions; no training
or data was changed. Isotonic-4 at 1x was the strongest row, reaching
`+122.798%` normal net and `+112.963%` fee-stress net, but DD was `20.086%`
and `20.473%` respectively, just beyond the 20% limit. Its monthly geometric
returns were only `2.405%` and `2.268%`, below the required 5%. The safer 0.5x
isotonic-4 row stayed below 11% DD but reached only `1.233%` monthly. No
mapping was selected for deployment and no leverage increase is authorized.

## Scope and method

V30 uses v29's immutable 33-model export and passed v29 replay audit. For each
continuous fold it fits an isotonic map only on earlier mature-label rows,
with a fixed 8-day label-end embargo. The fixed comparison is identity,
previous 1, 2, 4 or all quarters; all five mappings, both exposures and all
three cost scenarios are retained. The policy, thresholds, seed ensemble and
global equity state are unchanged. All 4,076 decisions from `2023-06-01` to
`2026-03-23` are opened development, not an independent test.

Costs are 0.02% per fill, long funding 0.01% every eight hours, zero short
funding; fee stress is 0.055% per fill; execution stress uses 5 bps
entry/target penetration, 5 bps market-exit slippage and 0.055% market-exit
fee. DD is close-sampled and execution stress is not a queue or mark-price
model.

## Complete results

Capital starts at 100. Gross, fees and funding are percentage-point amounts on
the compounded ledger; DD is shown as a positive magnitude here.

| Mapping / exposure | Scenario | Final equity | Gross | Fees | Funding | Net return | DD | Fills | Monthly geometric |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| identity / 1x | normal | 97.844 | 5.085 | 2.950 | 4.291 | -2.156% | 28.233% | 77 | -0.065% |
| identity / 1x | fee stress | 92.699 | 4.750 | 7.895 | 4.157 | -7.301% | 29.289% | 77 | -0.225% |
| identity / 1x | execution stress | 114.933 | 23.577 | 4.478 | 4.165 | +14.933% | 24.478% | 66 | +0.414% |
| identity / 0.5x | normal | 100.702 | 4.426 | 1.519 | 2.205 | +0.702% | 15.034% | 77 | +0.021% |
| identity / 0.5x | fee stress | 98.021 | 4.314 | 4.123 | 2.170 | -1.979% | 15.657% | 77 | -0.059% |
| identity / 0.5x | execution stress | 108.980 | 13.246 | 2.218 | 2.048 | +8.980% | 12.836% | 66 | +0.255% |
| isotonic-1 / 1x | normal | 101.748 | 7.950 | 2.844 | 3.358 | +1.748% | 36.715% | 54 | +0.051% |
| isotonic-1 / 1x | fee stress | 97.988 | 8.953 | 7.677 | 3.288 | -2.012% | 37.575% | 54 | -0.060% |
| isotonic-1 / 1x | execution stress | 93.818 | 0.611 | 3.829 | 2.964 | -6.182% | 34.218% | 49 | -0.189% |
| isotonic-1 / 0.5x | normal | 102.052 | 4.781 | 1.242 | 1.487 | +2.052% | 20.103% | 54 | +0.060% |
| isotonic-1 / 0.5x | fee stress | 100.150 | 5.004 | 3.383 | 1.471 | +0.150% | 20.642% | 54 | +0.004% |
| isotonic-1 / 0.5x | execution stress | 97.939 | 1.057 | 1.749 | 1.369 | -2.061% | 18.551% | 49 | -0.062% |
| isotonic-2 / 1x | normal | 82.913 | -11.839 | 2.284 | 2.963 | -17.087% | 36.469% | 54 | -0.554% |
| isotonic-2 / 1x | fee stress | 79.832 | -11.099 | 6.170 | 2.899 | -20.168% | 38.433% | 54 | -0.666% |
| isotonic-2 / 1x | execution stress | 71.330 | -23.095 | 3.017 | 2.558 | -28.670% | 42.179% | 48 | -0.997% |
| isotonic-2 / 0.5x | normal | 92.211 | -5.214 | 1.115 | 1.460 | -7.789% | 19.480% | 54 | -0.240% |
| isotonic-2 / 0.5x | fee stress | 90.486 | -5.032 | 3.038 | 1.444 | -9.514% | 20.728% | 54 | -0.296% |
| isotonic-2 / 0.5x | execution stress | 85.415 | -11.693 | 1.556 | 1.336 | -14.585% | 23.259% | 48 | -0.467% |
| isotonic-4 / 1x | normal | 222.798 | 134.957 | 4.322 | 7.837 | +122.798% | 20.086% | 65 | +2.405% |
| isotonic-4 / 1x | fee stress | 212.963 | 132.178 | 11.592 | 7.623 | +112.963% | 20.473% | 65 | +2.268% |
| isotonic-4 / 1x | execution stress | 192.890 | 105.072 | 5.381 | 6.801 | +92.890% | 18.318% | 56 | +1.968% |
| isotonic-4 / 0.5x | normal | 151.128 | 55.795 | 1.681 | 2.986 | +51.128% | 10.582% | 65 | +1.233% |
| isotonic-4 / 0.5x | fee stress | 147.736 | 55.250 | 4.567 | 2.946 | +47.736% | 10.796% | 65 | +1.164% |
| isotonic-4 / 0.5x | execution stress | 140.405 | 45.282 | 2.164 | 2.712 | +40.405% | 9.604% | 56 | +1.012% |
| isotonic-all / 1x | normal | 189.793 | 99.829 | 3.968 | 6.068 | +89.793% | 24.213% | 67 | +1.919% |
| isotonic-all / 1x | fee stress | 181.155 | 97.704 | 10.641 | 5.908 | +81.155% | 24.688% | 67 | +1.778% |
| isotonic-all / 1x | execution stress | 157.488 | 67.545 | 5.046 | 5.011 | +57.488% | 24.769% | 62 | +1.356% |
| isotonic-all / 0.5x | normal | 139.887 | 44.021 | 1.639 | 2.496 | +39.887% | 12.883% | 67 | +1.001% |
| isotonic-all / 0.5x | fee stress | 136.654 | 43.570 | 4.452 | 2.464 | +36.654% | 13.153% | 67 | +0.931% |
| isotonic-all / 0.5x | execution stress | 127.280 | 31.684 | 2.203 | 2.200 | +27.280% | 13.200% | 62 | +0.718% |

The strongest fixed mapping remains materially below 5% monthly. Since the
isotonic-4 row was pre-registered and all mappings are retained, this result is
not a license to tune a tighter threshold or to claim forward performance.

## Reproduction identity

- Plan: `configs/swing_v30_v29_calibration.json`
- Calibration report: `artifacts/research/v30_v29_calibration/summary.json`
- Calibration plan copy: `artifacts/research/v30_v29_calibration/plan.json`
- Source cloud export: `artifacts/kaggle/v29_download/tcn-training`
- Source replay audit: `artifacts/research/v29_local_audit/audit.json`
- V30 plan SHA-256: `c4aec73134322223328aed5e46acd042f05a4e60c0a8189ccbc13249d26b8cf3`
- V30 summary SHA-256: `efa497c1bbb3f892a8ef7aad327bf96c1fd202d8ddd8667ec32fd913cb161560`
- V30 plan-copy SHA-256: `418dc8f3a9df6c64e95608e7ff7eb9e89098e5f39acfe00e4dae618c9c98da4f`
- V29 cloud summary SHA-256: `31b0f10c661aa42b364561999fbf9f25001bb101d893cd6a18f183b9f1683a69`
- V29 audit SHA-256: `8a32411f9de8fce1e183174b694cf4cfe5862a5de6e5c745aa0cae2419a36b94`
- Dataset manifest SHA-256: `a1ab4c5f7564bd58ac3daa7479685d16eff4b85fd027a8d5f56e82093056c381`

The result records `independent_test: false` and `live_approved: false`; the
v29 source export and its audit remain immutable research inputs.
