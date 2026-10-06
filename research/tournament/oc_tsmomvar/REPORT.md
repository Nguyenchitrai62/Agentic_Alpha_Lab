# oc_tsmomvar REPORT: two pre-registered TSMOM sleeve variants (idea: diversifier)

Rules frozen in PLAN.md before any outcome was scored; each variant run once.
Sleeve mechanics reuse `oc_tsmom/run_tsmom.py` exactly (daily O/C from
`research/tournament/ext/hourly_ext.parquet`, t < 2026-09-24 00:00 UTC only;
next-day-open execution; taker 0.00055 on |dpos|; longs fund 0.0003/day,
shorts zero). Base = R2B1D17BF reset-convention year path (F(a0) = 1.0,
reproduces oc_kpi R to 0.024pp/month; DD on daily-00:00 grid, no 1m marking).
Combined = base daily + 0.25 x sleeve daily, per anchor year [A, A+365d),
364/365/365/365/364 holding days (year 0 drops the 2021-09-24 partial day;
last year ends 2026-09-22 — no 2026-09-24 open). Same daily grid as oc_tsmom.
One process, no 1m, peak RAM ~0.3 GB. All five years are research data; any
finding needs prospective validation. Repro:
research/tournament/oc_tsmomvar/{PLAN.md,run_var.py,results.json};
test tests/test_oc_tsmomvar.py.

V1 = oc_tsmom 30d long/short rule on all five majors (BTC/ETH/SOL/BNB/XRP,
equal 10% risk per coin, cap 1.0x). V2 = BTC/ETH 90d long-only (flat when
ret90 <= 0; 90d vol, same 10% target/cap; shorts never held so no short
funding effect).

## Verdict

NOT PROMISING for either variant under the pre-registered gate (DIV >= 4/5
AND LOYO >= 4/5): V1 DIV 0/5 (pos 4/5, corr<0.15 1/5; LOYO 5/5), V2 DIV 0/5
(pos 2/5, corr<0.15 1/5; LOYO 5/5). Neither variant lowers correlation below
0.15 while keeping a positive sleeve mean in >= 4/5 years.

## Tables

Per anchor year — sleeve standalone, then base vs combined (descriptive),
corr and DIV gate (operative):

V1 (5-coin 30d):
year    sleeve m% / tot% / Sharpe / DD%     base m% / DD%     comb m% / DD%     excess / dDD     corr    pos? corr? DIV?
21-22   +3.06 / +43.7 / 1.09 / 30.7         2.83 / 7.7        3.72 / 8.6        +0.88 / +0.92    0.20    YES  NO   NO
22-23   -2.06 / -22.0 / -0.46 / 39.7        3.51 / 15.3       3.09 / 15.5       -0.41 / +0.19    -0.03   NO   YES  NO
23-24   +2.54 / +35.2 / 0.97 / 32.2         4.67 / 15.5       5.33 / 17.3       +0.66 / +1.77    0.50    YES  NO   NO
24-25   +2.65 / +37.0 / 1.02 / 22.7         11.27 / 6.0       12.06 / 8.7       +0.79 / +2.68    0.33    YES  NO   NO
25-26   +0.59 / +7.3  / 0.38 / 35.8         5.04 / 10.8       5.21 / 13.5       +0.17 / +2.72    0.54    YES  NO   NO
(m% = year total^(1/12)-1; DD = daily-grid max peak-to-trough; excess/dDD =
combined minus base, pp.)

V2 (BTC/ETH 90d long-only):
year    sleeve m% / tot% / Sharpe / DD%     base m% / DD%     comb m% / DD%     excess / dDD     corr    pos? corr? DIV?
21-22   -0.71 / -8.2  / -0.76 / 19.7        2.83 / 7.7        2.66 / 7.7        -0.18 / +0.00    0.06    NO   YES  NO
22-23   -0.12 / -1.4  / -0.03 / 14.4        3.51 / 15.3       3.46 / 17.2       -0.04 / +1.86    0.39    NO   NO   NO
23-24   +2.38 / +32.7 / 1.72 / 8.9          4.67 / 15.5       5.28 / 16.1       +0.61 / +0.59    0.34    YES  NO   NO
24-25   +1.51 / +19.7 / 1.30 / 10.0         11.27 / 6.0       11.69 / 6.4       +0.42 / +0.44    0.21    YES  NO   NO
25-26   -0.43 / -5.1  / -0.47 / 15.2        5.04 / 10.8       4.90 / 12.1       -0.13 / +1.25    0.49    NO   NO   NO

Sleeve operating stats (avg |pos| per coin; cost/fund drag bps/day):
V1: 21-22: BTC 0.15 ETH 0.12 SOL 0.14 BNB 0.14 XRP 0.16, cost 0.54, fund 0.82.
22-23: 0.25/0.21/0.25/0.23/0.22, 1.30, 1.18. 23-24: 0.22/0.19/0.21/0.18/0.26,
0.98, 1.70. 24-25: 0.25/0.15/0.34/0.24/0.31, 0.97, 1.96. 25-26:
0.26/0.18/0.29/0.31/0.29, 1.35, 1.74.
V2 (long-only, smaller book when flat): 21-22: BTC 0.06 ETH 0.05, cost 0.08,
fund 0.33. 22-23: 0.13/0.09, 0.17, 0.66. 23-24: 0.12/0.08, 0.10, 0.59.
24-25: 0.14/0.07, 0.12, 0.62. 25-26: 0.12/0.06, 0.14, 0.52.

LOYO pooled sleeve mean (other 4 years, bps/day; operative): V1 full-5y
+6.75; pools 21-22 +7.82, 22-23 +9.83, 23-24 +5.95, 24-25 +5.98, 25-26 +7.21
— sign match 5/5. V2 full-5y +1.70; pools +2.56, +2.17, +0.53, +1.05, +2.33
— sign match 5/5 (means small; V2 pools all positive only because 23-24 and
24-25 dominate).

Combined-vs-base (descriptive only, same grid): V1 combined return higher in
4/5 (all but 22-23) but DD not-worse in 0/5 (worse every year, +0.2..+2.7pp).
V2 combined return higher in 2/5 (23-24, 24-25) and DD not-worse in 1/5
(21-22 equal; else worse by +0.4..+1.9pp).

## Caveats / post-hoc log

1. No post-hoc changes: PLAN.md frozen before scoring; two fixed rules, one
   run each. No amendment.
2. DDs are daily-00:00 grid only (no 1m marking): base DDs match oc_tsmom to
   the stored penny (same code path); live DD would be worse for both legs.
3. V1's 5-coin book is intrinsically more volatile (sleeve DD 22.7-39.7%,
   corr 0.20-0.54 except the 22-23 loss year): equal risk per coin sums to
   ~5x the single-sleeve gross exposure, so 0.25x sizing does not contain the
   correlated tail. V2's long-only 90d book is calmer (DD 8.9-19.7%) but its
   mean is near zero (positive only 2/5) and corr is < 0.15 in only 1/5.
4. No lookahead: signals use only closes <= D (31 closes for 30d, 91 for
   90d), vol uses only past log returns, positions execute at next open;
   hourly cap asserted in code; costs/funding deducted daily as in oc_tsmom.
5. Checks: base monthly gap vs oc_kpi R <= 0.024pp; compounding residuals
   <= 0.0005pp; v411 keys {t,eq,eq_min}; n_days 364/365/365/365/364 both
   variants (same grid as oc_tsmom).

## One-line verdict

NOT PROMISING — neither variant decorrelates (corr < 0.15 in only 1/5 years
each) while staying positive (V1 4/5 positive but correlated; V2 long-only
positive only 2/5): DIV 0/5 both, so the direction is closed with no sleeve.
