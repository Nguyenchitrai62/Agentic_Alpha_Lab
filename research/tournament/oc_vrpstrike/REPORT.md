# oc_vrpstrike REPORT — weekly short-straddle priced from REAL traded strike IV (STRIKE-V2)

Frozen rule (PLAN.md, pre-registered 2026-10-07, single variant, no selection):
V2-unhedged mechanics, premium = BS at the traded amount-weighted vwap_iv of
the exact next-Friday ATM instrument over Fri 08:00-10:59 minus h (0.5 BTC /
1.0 ETH), S_entry = 10:59 1m close; marks from the same instrument's last
traded bucket (ask = iv+h for SL, mid for TP), fallback r x DVOL
(r = entry iv / entry DVOL per leg) when no print in 24h; SL -1x hourly,
TP 0.3x at 4h, Deribit-style fees, q = 0.5 f E / S. Repro:
`run_strike.py {inventory|dev|final}` via heavy_slot + `tests/test_oc_vrpstrike.py`.
G2 f=0 reproduces v421_result (yearly R/DD, 5y R/W/DD, full-path DD) to the
digit (asserted in-script); else the run stops. No post-hoc changes.

## Standalone sleeve f=1, dev4 — ALL YEARS PARTIAL (months in STATUS.md)

| year | R %/mo / DD % / end / trades / win | TP/SL/expiry | r_med / prem_med / IV-RV gap |
|---|---|---|---|
| 2021-09-24 | 1.233 / 16.60 / 1.158 / 51 / 0.627 | 15/10/26 | 0.855 / 7.42% / -0.017 |
| 2022-09-24 | -0.455 / 17.50 / 0.947 / 22 / 0.591 | 5/8/9 | 0.824 / 5.19% / -0.018 |
| 2023-09-24 | 0.000 / 0.00 / 1.000 / 0 / — | 0/0/0 | no complete months, no trades |
| 2024-09-24 | -0.425 / 8.46 / 0.950 / 4 / 0.500 | 2/2/0 | 0.918 / 5.50% / -0.051 |
| dev4 | mean 0.086 / worst -0.455 / maxDD 17.50 / 2 losing + 1 empty | | |

Entry iv/DVOL 0.82-0.92 independently confirms B.json (pooled 0.862/0.868):
the DVOL-priced V2 premium overstated the tradeable 7d premium by ~11%.
IV - realised is NEGATIVE every year: no positive VRP edge at traded prices
on average; ~60% win rate with negative skew (small gains, crash-week SLs).
Sleeve-only full-path DD 30.66 (naked short-gamma tail, labelled).

## Overlay on G2 f=0.25, dev4 PARTIAL (G2 rows COMPLETE, sleeve PARTIAL)

| year | G2 R/DD | +STRIKE-V2 f=0.25 R/DD |
|---|---|---|
| 2021 | 2.588 / 10.86 | 2.935 / 10.89 |
| 2022 | 3.282 / 16.91 | 3.170 / 16.91 |
| 2023 | 6.045 / 15.81 | 6.045 / 15.81 (no sleeve trades) |
| 2024 | 10.677 / 8.27 | 10.563 / 8.27 |
| dev4 mean / worst / maxDD | 5.601 / 2.588 / 16.91 | 5.634 / 2.935 / 16.91 |
| full-path DD | 16.82 | 16.82 |

Gain over G2 dev4: mean +0.033 pp, worst +0.347 pp, DD +0.00 — inside the
DD <= G2+0.5 bar, but the mean gain is 3 bps on PARTIAL data (two losing
partial standalone years + one empty year). Daily-P&L corr (sleeve vs G2):
0.000 overall, -0.118 in G2's worst 20 days — no crash-hedge property.

## Most recent year 2025-09-24..2026-09-23, scored ONCE (descriptive, PARTIAL)

Standalone 1.799 / 18.31, 57 trades (24 BTC + 33 ETH), win 0.667, r_med
0.916, gap -0.049. Overlay f=0.25: 5.138 / 13.76 vs G2 4.648 / 12.90
(+0.490 pp mean, +0.86 DD — DD rise exceeds G2+0.5 on this year alone).
Not used for any choice (no choice exists); reported once, labelled.

## Leakage statement

Feature timing: strike buckets known at H+1h (entry uses 08/09/10 only, all
known at 11:00; marks use last bucket with close <= t via `last_traded_iv`,
unit-tested incl. 24h-fallback boundary); index08/S_entry/DVOL_entry known at
entry; settlement 07:30..07:59 known at 08:00; first exit check 12:00 Fri so
nothing fills in the first 5 min; 0 inexact 1m lookups. Label windows:
payoffs/marks use only post-entry data. Fit windows: r_leg/K*/thresholds
fixed at entry from entry-time values only; no fits on any test year; G2/1m/
DVOL inputs pre-exist and untouched. Fill timing: options at model marks +
Deribit-style fees (no book; half-spread compressed into haircut h,
labelled research simplification). Causality/truncation tests in
tests/test_oc_vrpstrike.py (7 passed).

## Verdict

With real traded prices the overlay adds +0.03 pp dev4 mean / +0.35 pp worst
at equal DD — technically inside the DD bar but economically zero on partial
data with negative IV-RV gaps, two losing partial years and an empty year;
the recent year adds return only with +0.86 DD. NOT adopt-worthy now; needs
the full-coverage re-run (fetch still filling) plus prospective evidence.

Tiếng Việt:
Lớp phủ giá thật chỉ hơn G2 0,03 điểm trung bình dev4 (dữ liệu từng phần, 2 năm lỗ từng phần, 1 năm trống), worst hơn 0,35 điểm, DD bằng nhau.
Năm gần nhất tăng lợi nhuận nhưng DD tăng 0,86, vượt ngưỡng 0,5 nên chưa đạt để paper.
Chưa triển khai; chờ fetch đủ dữ liệu chạy lại toàn diện và thêm bằng chứng prospective.

---

# FULL COVERAGE extension (fetch complete 2026-10-07; partial section above KEPT as-is)

Method (rule frozen, code reused UNCHANGED): `vrpstrike.py` + `run_strike.py`
were NOT edited — `tmp/run_full.py` only imports them and calls the same
functions (`load_dvol/load_1m/load_strike/build_positions/simulate_year/
year_slices/g2_paths/diagnostics_for_year`). The ONLY difference vs the
partial run is the inventory source: every parquet file on disk is treated as
a complete month (fetchers write atomically via tmp+rename), instead of only
manifest-listed months. Overlap months present in both folders were compared
row-for-row and one copy used. G2 f=0 reproduces `v421_result.json`
(R2B1D17BFG2 yearly R/DD, 5y R/W/DD, full-path DD) to the digit in this run
too (asserted in-script); else the run would have stopped. Results:
`results_full.json` + `tmp/final_full.json` + `tmp/inventory_full.json` +
`trades_strike_full.parquet` (407 trades, 5 anchors). Partial artifacts
(`results.json`, `trades_strike_dev4/recent.parquet`, STATUS.md) untouched.

Coverage FULL: BTC union 69 months 2021-01..2026-09 (forward 55
2021-01..2025-07 + backward 15 2025-07..2026-09); ETH union 69 months
2021-01..2026-09 (forward 66 2021-01..2026-06 + backward 15 2025-07..2026-09).
Missing vs 2021-01..2026-09: none for either coin. Overlaps identical
(shape + sorted full-frame equality): BTC 2025-07 (87306 rows); ETH
2025-07..2026-06, 12 months (68846/86280/64422/78023/61766/49413/45946/
49406/51532/45006/36881/36546 rows). One copy used; `load_strike` deduped
174612 identical BTC + 1470606 identical ETH overlap rows, zero conflicts.
Grid 2021-09-24 04:00 .. 2026-09-23 12:00 (43809 hourly steps).
520 Friday coin-weeks: 414 traded, data-gap 0, low-volume 96 (entry window
< 0.1 coin/leg), no-pair 10, no-vol/no-price 0, 0 inexact 1m lookups.
Year-boundary weeks with expiry past year-end skipped per year (n_skip
2/2/1/2/0). No year is PARTIAL any more — all tables below are FULL.

## Standalone sleeve f=1, dev4 FULL

| year | R %/mo / DD % / end / trades / win | TP/SL/expiry | r_med / prem_med / IV-RV gap |
|---|---|---|---|
| 2021-09-24 | 1.751 / 35.85 / 1.232 / 102 / 0.627 | 24/18/60 | 0.857 / 8.09% / -0.030 |
| 2022-09-24 | -1.556 / 29.66 / 0.828 / 73 / 0.575 | 20/22/31 | 0.836 / 4.87% / -0.020 |
| 2023-09-24 | -2.765 / 31.07 / 0.714 / 78 / 0.500 | 10/24/44 | 0.888 / 5.49% / -0.061 |
| 2024-09-24 | -1.350 / 29.97 / 0.850 / 82 / 0.585 | 21/24/37 | 0.921 / 5.95% / -0.048 |
| dev4 | mean -0.994 / worst -2.765 / maxDD 35.85 / 3 losing | | |

Entry iv/DVOL medians 0.84-0.92 again confirm B.json (~0.87): the traded 7d
premium is ~11% below DVOL-implied. IV - realised NEGATIVE all four years:
no positive VRP edge at real traded prices; win rates 50-63% with negative
skew (small TP gains, crash-week SLs; worst weeks -9.6%..-15.7%).
Sleeve-only full-path DD 67.01 (naked short-gamma tail), end 0.72.

## Overlay on G2 f=0.25 FULL (G2 rows COMPLETE, unchanged)

| year | G2 R/DD | +STRIKE-V2 f=0.25 R/DD |
|---|---|---|
| 2021 | 2.588 / 10.86 | 3.139 / 13.08 |
| 2022 | 3.282 / 16.91 | 2.909 / 18.19 |
| 2023 | 6.045 / 15.81 | 5.355 / 15.78 |
| 2024 | 10.677 / 8.27 | 10.400 / 8.19 |
| dev4 mean / worst / maxDD | 5.601 / 2.588 / 16.91 | 5.408 / 2.909 / 18.19 |
| 5y R/W/DD | 5.410 / 2.588 / 16.91 | 5.332 / 2.909 / 18.19 |
| full-path DD | 16.82 | 18.11 (close 17.33) |

Overlay vs G2 on dev4 FULL: mean -0.193 pp (BELOW G2), worst +0.321 pp, DD
+1.28 (dev4) / +1.29 (full path) — FAILS the DD <= G2+0.5 bar. Daily-P&L
corr (sleeve vs G2): -0.075 overall, -0.171 in G2's worst 20 days — no
crash-hedge property (mildly anti-correlated at best).

## Most recent year 2025-09-24..2026-09-23 — RESCORED ONCE ON FULL DATA

This year was already scored once on partial data (standalone 1.799/18.31,
overlay 5.138/13.76 vs G2 4.648/12.90). Per the extension it is rescored
exactly ONCE on full data (never used for any choice; single variant, no
selection exists):

FULL rescore: standalone 1.265 / 22.03, 72 trades (38 BTC + 34 ETH), win
0.611, TP/SL/expiry 23/16/33, r_med 0.918, prem_med 5.22%, gap -0.047,
worst week 2025-11-27 -9.36. Overlay f=0.25 FULL: 5.025 / 13.77 vs G2
4.648 / 12.90 (+0.377 pp mean, +0.87 DD — DD rise exceeds G2+0.5 on this
year alone, same pattern as the partial scoring).

## Leakage statement (FULL run; same checks as partial)

Feature timing: strike buckets known at H+1h (entry uses 08/09/10 only, all
known at 11:00; marks use last bucket with close <= t); index08/S_entry/
DVOL_entry known at entry; settlement 07:30..07:59 known at 08:00; first
exit check 12:00 Fri so nothing fills in the first 5 min; 0 inexact 1m
lookups. Label windows: payoffs/marks use only post-entry data. Fit
windows: r_leg/K*/thresholds fixed at entry from entry-time values only;
no fits on any test year; no statistic from any test year fed back into a
choice (no choice exists; single frozen variant). Fill timing: options at
model marks + Deribit-style fees (no book; half-spread compressed into
haircut h, labelled research simplification). Disk files trusted as
complete per the atomic-write fetcher guarantee stated in the extension
assignment. Causality/truncation tests in tests/test_oc_vrpstrike.py
(unchanged, re-run below).

## Verdict (FULL coverage)

With real traded prices on full 2021-01..2026-09 data the overlay LOSES
0.19 pp dev4 mean vs G2 (5.408 vs 5.601), gains 0.32 pp worst year, but
adds +1.3 DD (18.19 vs 16.91, full-path 18.11 vs 16.82) — it FAILS the
DD <= G2+0.5 bar and the mean bar simultaneously, with 3 losing standalone
years and negative IV-RV gaps every year. The rescored recent year repeats
the partial pattern (return +, DD +0.87 over bar). REJECT for paper/dev;
no prospective evidence can fix a negative edge with a fatter tail.

Tiếng Việt:
Dữ liệu đủ 69 tháng giá thật: lớp phủ thua G2 0,19 điểm trung bình dev4 (5,41 so với 5,60), worst hơn 0,32 điểm nhưng DD tăng 1,3 (18,2 so với 16,9), rớt cả hai ngưỡng mean và DD; sleeve độc lập lỗ 3/4 năm, IV-RV âm mọi năm.
Năm gần nhất chấm lại một lần trên dữ liệu đủ vẫn tăng DD 0,87, vượt ngưỡng.
Không triển khai; đóng hướng này với giá thật (trừ khi đổi quy tắc và đăng ký lại từ đầu).
