# oc_crashgate — REPORT (2026-10-08; PLAN frozen before any outcome)

Crash-conditioned dip tilt (IDEAS5 #1, rank 1): frozen C2 tilt multipliers applied ONLY
when trailing-30d BTC max-DD-depth < X, else base G2 sizes. V1 X = 15 %; V2 X = 10 %
(round numbers frozen ex-ante, never fit). Dip sleeve otherwise untouched; existing 4h
closes only (no new data).

STATUS: DONE — gate FAIL for both variants, NO engine run (negative result, valid per
IDEAS5: "several will fail at the screen/gate").

## Crash depth (frozen, causal)

- BTCUSDT 4h closes (`oc_kronoshidden/bars_4h_4shift.parquet`), per shift: at holding-bar
  open T, window = closes with close_time in (T-30d, T] (nominal 180 bars);
  depth = max intra-window peak-to-trough, floored at 0 (`crash_depth_4shift.parquet`,
  53,877 rows). Median depth ~13 % (p90 ~26 %, max ~46 %); share of bars with
  depth >= 15 % ~40 %, >= 10 % ~65 % — both gates bind hard (V2 disables the tilt on
  ~60 % of fills overall, ~97 % of 2021 fills).

## Replica + placebo gate (reused D0+B1 ledger, n = 22312, base sum5y = 7.718304 exact)

| year x variant | n | base | gated | norm | timing pct | block pct | fills allow% |
|---|---|---|---|---|---|---|---|
| 2021 V1 / V2 | 4171 | 0.911273 | 0.911825 / 0.941090 | 0.9217 / 0.9436 | 77.4 / 97.7 | 80.1 / 97.5 | 16.8 / 2.7 |
| 2022 V1 / V2 | 4059 | 0.832599 | 0.746980 / 0.851981 | 0.8121 / 0.8944 | 55.8 / 93.6 | 67.5 / 90.6 | 77.2 / 49.9 |
| 2023 V1 / V2 | 5352 | 2.099814 | 2.203956 / 2.143320 | 2.2649 / 2.1818 | 100.0 / 99.6 | 100.0 / 99.9 | 72.9 / 57.0 |
| 2024 V1 / V2 | 3958 | 3.197390 | 3.239462 / 3.266991 | 3.2399 / 3.2487 | 100.0 / 100.0 | 100.0 / 100.0 | 90.0 / 64.2 |
| 2025 clean V1 / V2 | 4772 | 0.677229 | 0.677613 / 0.665159 | 0.6806 / 0.6685 | 86.5 / 73.2 | 89.6 / 76.7 | 42.1 / 26.9 |

- dSum5y (4-phase-mean w*y): V1 +0.062, V2 +0.150 — BOTH < +0.273 (pooled placebo p95).
  Sum-half: 4/5 each (V1 fails 2022; V2 fails clean 2025). Gate needs BOTH legs:
  V1 FAIL, V2 FAIL.
- Timing keeps the family signature (100.0 in 2023-2024) but NEITHER variant has
  significant clean-year timing (V1 86.5, V2 73.2). V2's tighter gate recovers 2021
  timing (97.7/97.5) yet still loses clean-year money (-0.012) — the crash it dodges is
  not where the tilt's edge lives.
- Bars allow-share (decision bars, 4 shifts): V1 [23.8, 79.8, 59.9, 85.2, 67.5] %;
  V2 [2.1, 45.5, 44.3, 53.1, 43.0] % per year 2021..2025.

## Engine (not run — gate rule)

Per the assignment ("run the 4-phase engine only for variants that pass the gate") and
the frozen PLAN, NO engine rows were run: REF was not re-reproduced here (v421 G2
5.41 / 16.91 / 16.82 stands from oc_voltilt/oc_beargate reproductions to the digit), and
no V1/V2 engine DD, win-rate, 5y or full-path numbers exist. Dev4 robust pick:
none-eligible (no engine rows; replica gate failed both).

## Leakage checklist

- Feature timing: ch_q10 frozen (inherits truncation test); depth uses BTC closes with
  close_time <= T only (truncation-tested in tests/test_oc_crashgate.py: dropping later
  bars cannot change depth at kept times); exact (shift,T) match with causal ffill
  fallback; NaN -> allow (inert — full 180-bar windows for all of 2021-09-24..).
- Label windows: none fit here (frozen harness fits inherited, t_exit < A - 7d).
- Fit windows: frozen C2 fits (shift-0 + 7d embargo, anchor-y for year y); X = 15/10
  frozen ex-ante round numbers, never scanned or fit; no statistic from any test year
  feeds any choice.
- Fill timing: replica fills inherited (live 16..238 strict trade-through, stop-first);
  perms reassign mults within-year only (seeds 20261007+y / 20261008+y).
- Coverage: 4h closes cover every anchor year — no skipped year, nothing imputed.
- DISCLOSED (pre-registered in PLAN): the k2placebo ledger carries no exit-date/daily
  path, so the replica DD-half (DD <= base + 0.01 in >= 4/5) cannot be scored at the
  replica stage; the binding DD check would have been the 4-phase engine (not reached).
- Gate costs: inside the replica outcomes (maker 0.0002 / taker 0.00055, v293 settle
  funding); engine costs never invoked (no engine).

## What failed and why

The gate itself is the failure: V2 (+0.150) keeps more of the tilt's good years than V1
(+0.062) but both fall well short of the +0.273 placebo-p95 bar, and both lose a year
the ungated C2 wins (V1 2022, V2 clean 2025). Conditioning on realized crash depth does
not isolate the tilt's bad legs (2021/COVID-type): in 2021 the market ground sideways
with shallow 30d depths on V1's 16.8 %-allow but the tilt still had no edge to keep, and
the clean year (mostly bear-flagged elsewhere, 80.5 % bear) shows no gated timing.
Same lesson as oc_beargate: the regime variable is not the crash regime.

## Vietnamese verdict

Cả hai biến thể đều RỚT ở cửa replica+placebo (V1 dSum5y +0,062, V2 +0,150, đều < +0,273)
nên KHÔNG chạy engine 4-phase theo đúng quy tắc; timing năm sạch không có ý nghĩa
(V1 86,5%, V2 73,2%) — gate theo crash-depth không cứu được 2021/2022 như kỳ vọng.
Kết luận: REJECT ý tưởng crash-gate ở dạng đăng ký trước; không chọn biến thể nào,
không cần bằng chứng prospective.
