# oc_presampletilt — REPORT (2026-10-08; PLAN frozen before any outcome)

Do the vol / Chronos dip-size tilts work in the PRE-SAMPLE years 2017-2021?
Frozen rule on genuinely unseen years: V_RV6 / V_GARCH / C2 multipliers with the
EARLIEST (anchor-2021) fits, labelled "fit from later data, rule frozen".
Chronos-Bolt and RV6/GARCH never saw crypto, so 2017-2020 is unseen for all three.

STATUS: DONE. Bars 101,345 rows; vol 59,247 rows; Chronos 44,375 rows
(model amazon/chronos-bolt-small revision 772f3d25d38aec6d914c8949dab4462e2d46f5d8,
chronos-forecasting 2.3.2, transformers 5.19.0, GPU GTX1650 ~51 s); ledger 9,731 fills;
tilt + 1000 timing/block perms per variant/year complete. 2021-2026 columns are COPIES
(placebo_vol.json / placebo_c2.json), not recomputed.

## Data / coins / ledger (fixed)

- Spot store `data/raw/spot_1m_presample_20261007` (read-only): BTC/ETH from 2017-08-17,
  BNB from 2017-11-06, XRP from 2018-05-04, SOL absent. Years exactly as oc_presample2:
  Y2017 [2017-10-16,2018-01-01) BTC+ETH only (XRP absent, BNB pre-warmup),
  Y2018/Y2019 full 4-coin (XRP from 2018-07-03), Y2020p [2020-01-01,2020-09-01).
  The extra 2020-09-24..2021-09-23 window is NOT evaluated (spot store ends 2020-09-30).
- Ledger: D0+B1 replica same as oc_k2placebo (RUNGS 2.5-5, live 16..238 strict
  trade-through, w=1/(1+n) coins-present-only, outcome_mu TP 0.9/1.0/1.1 close5+backstop,
  gate costs inside, stop-first, kept iff y09/y10/y11 ALL finite; NO budget/cap).
  Fills Y2017/Y2018/Y2019/Y2020p = 909/2986/3115/2721 (total 9,731).
  Diff vs oc_presample 9,732: exactly 1 Y2019 fill dropped by the paired-leg kept rule
  (same as k2placebo); disclosed, not a mismatch.
- Features: same 4 clocks (ORIGIN 2020-01-01 + s h); sigma = rolling-360 std of
  diff(log open); RV6 = 6-return std shift-1; GARCH filter with FROZEN anchor-2021
  params; Chronos 512-close ctx, ch_q10=(q10-logC0)/sigma, risk=-ch_q10.
  Join missing -> mult 1: vol 4,254/9,731 fills (burn-in), C2 5,547/9,731 (512 ctx).
  Spot-vs-perp caveat on every number (SPOT fills/exits, perp gate costs).

## Pre-sample results (frozen 2021 rule; norm = tilt/realised_mean, gain = norm-base)

| year x variant | n | base | norm | gain | timing pct | block pct |
|---|---|---|---|---|---|---|
| Y2017 V_RV6 | 909 | 2.313362 | 2.312963 | -0.000399 | 100.00 | 100.00 |
| Y2018 V_RV6 | 2986 | 2.678870 | 2.822164 | +0.143293 | 100.00 | 100.00 |
| Y2019 V_RV6 | 3115 | 0.577643 | 0.683668 | +0.106025 | 98.20 | 98.90 |
| Y2020p V_RV6 | 2721 | 0.297538 | 0.160221 | -0.137316 | 9.89 | 12.19 |
| Y2017 V_GARCH | 909 | 2.313362 | 2.330076 | +0.016714 | 100.00 | 100.00 |
| Y2018 V_GARCH | 2986 | 2.678870 | 2.715430 | +0.036560 | 99.90 | 100.00 |
| Y2019 V_GARCH | 3115 | 0.577643 | 0.732384 | +0.154741 | 100.00 | 100.00 |
| Y2020p V_GARCH | 2721 | 0.297538 | 0.253256 | -0.044282 | 45.05 | 43.76 |
| Y2017 C2 | 909 | 2.313362 | 2.331855 | +0.018493 | 96.40 | 87.51 |
| Y2018 C2 | 2986 | 2.678870 | 2.679426 | +0.000556 | 99.80 | 100.00 |
| Y2019 C2 | 3115 | 0.577643 | 0.616509 | +0.038866 | 77.32 | 66.53 |
| Y2020p C2 | 2721 | 0.297538 | 0.138425 | -0.159113 | 2.90 | 1.50 |

Note Y2017 V_RV6: timing 100 but gain -0.0004 — the actual assignment beats every
random tilt (perms p95 2.213 < actual 2.313) yet lands a hair below doing nothing
(base 2.313362); random tilts hurt a lot that year, the frozen tilt avoids the damage.

## Side by side with 2021-2026 (COPIED, not recomputed)

| year x variant | gain (norm-base) | timing pct |
|---|---|---|
| 2021 V_RV6 / V_GARCH / C2 | -0.2318 / -0.1755 / -0.0178 | 2.40 / 12.39 / 90.11 |
| 2022 V_RV6 / V_GARCH / C2 | -0.1606 / -0.1762 / +0.0229 | 14.49 / 7.29 / 88.31 |
| 2023 V_RV6 / V_GARCH / C2 | -0.0930 / +0.0363 / +0.1308 | 97.10 / 99.90 / 100.00 |
| 2024 V_RV6 / V_GARCH / C2 | +0.0622 / +0.0197 / +0.0420 | 100.0 / 100.0 / 100.00 |
| 2025 V_RV6 / V_GARCH / C2 | +0.1233 / +0.1614 / +0.0437 | 100.0 / 100.0 / 99.20 |

## Counts over ALL 9 available years (pre 4 + 2021-2026 5)

- Helps (gain>0): V_RV6 4/9 (pre 2/4: 2018,2019; recent 2/5: 2024,2025),
  V_GARCH 6/9 (pre 3/4: 2017,2018,2019; recent 3/5: 2023,2024,2025),
  C2 7/9 (pre 3/4: 2017,2018,2019; recent 4/5: 2022,2023,2024,2025).
- Timing significant (>=95): V_RV6 6/9 (pre 2017,2018,2019 + 2023,2024,2025),
  V_GARCH 6/9 (same split), C2 5/9 (pre 2017,2018 + 2023,2024,2025).
- Common failure: Y2020p (COVID leg) hurts under ALL three tilts (gains negative,
  timing 2.9-45, block 1.5-43.8). Vol tilts also fail 2021-2022 (gains + timing);
  C2 timing is insignificant in 2021-2022 as well (90.1/88.3 < 95).

## Leakage statement

Feature timing (RV6: 6 closes <= T; GARCH filter: r[E-1] and earlier with frozen
params; Chronos: 512 closes <= T; sigma: opens <= T; truncation-tested in tests);
label windows (none fit here); fit windows (frozen anchor-2021 fits from harness rows
t_exit < 2021-09-17 + 7d embargo inherited, shift-0 only; GARCH params from bars closing
before 2021-09-17, prices only — applied to EARLIER years, hence the "fit from later
data, rule frozen" label; pre-sample years never used for any fit); fill timing
(strict 1m trade-through live 16..238 + stop-first, replica core). No statistic from
any test year feeds any choice. Gate costs inside replica outcomes. No selection is
made on any year here (diagnostic only).

## What failed

Y2020p fails for every tilt (the COVID crash leg: bigger-dip rungs when vol is high
catch the crash, not the rebound). V_RV6 also fails Y2017 on gain (timing without gain).
C2 fails timing in Y2019 pre-sample (77.3) and in 2021-2022. The 2020-09-24..2021-09-23
spot year could not be built (store ends 2020-09-30); cited tiltgate perp leg instead.

## Vietnamese verdict

2023-2026 là quy luật của giai đoạn gần đây (cả 3 tilt đều giúp và timing có ý nghĩa
2023, 2024, 2025), nhưng KHÔNG phải quy luật phổ quát: chân COVID Y2020p làm cả 3 tilt
đều lỗ và mất timing, còn 2021-2022 cũng làm 2 tilt vol lỗ (C2 timing không có ý nghĩa).
Tính cả pre-sample: C2 giúp 7/9 năm, V_GARCH 6/9, V_RV6 4/9 — tilt chỉ đáng tin khi
không phải chân crash. Kết luận: REJECT as a standalone rule; giữ bằng chứng prospective.
