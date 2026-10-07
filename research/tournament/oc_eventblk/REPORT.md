# oc_eventblk REPORT: scheduled US-macro event blackout for dip bids (idea #16)

Universe: majors (BTC/ETH/SOL/BNB/XRP) x R2 depths (2.5/3/3.5/4/5),
6876 fills, outcome y_dep (exact net at deployed TP, fees + adverse
funding inside). Anchor years 2021-09-24 .. 2025-09-24
(n = 990/1045/1330/989/1144). Flag: 4h holding bar [T,T+4h) contains a
scheduled FOMC-statement (14:00 ET) or CPI-release (08:30 ET) instant
(EDT -> 18:00/12:30 UTC, EST -> 19:00/13:30 UTC). Calendar from 18 raw
official pages (Fed live + archived 2020-12 snapshot; archived BLS CPI
schedules 2020-02..2026-02 + BLS 2021 selected-releases pages; direct
BLS fetch is 403 from here, archive bytes carry the same official
tables) + manifest.json (sha256). 54 FOMC + 82 CPI instants before the
2026-09-24 cutoff; zero PLAN dates missing from officials. Blackout =
size 0 on event bars, size_dep elsewhere, harness5 equal-exposure
renorm per year. No 1m/hourly data; one process, peak RAM ~0.3 GB.

## Verdict

NOT PROMISING under the pre-registered rule: spread sign only 3/5
(positive dominant, i.e. event bars slightly BETTER in 3/5 years),
LOYO agreement 2/5, worst-day not-worse 0/5. Event bars looked toxic
in 2021-22 (spread -135/-71 bps, gain +0.82/+0.28) then flipped sign
in 2023-25 (+22/+10/+12 bps on thin n_in = 17/15/8) — the exact
opposite of a stable information-vs-liquidity mechanism.

## Tables

Per anchor year (means bps; sums native size*y_dep, renorm sizes):

year    n     n_in  mean_in  mean_out  spread   S_dep   S_new   gain    pass?
21-22   990   67    -86.3    +48.9     -135.2   4.485   5.309   +0.824  YES
22-23   1045  38    -61.4    +9.3      -70.7    0.924   1.208   +0.284  YES
23-24   1330  17    +67.2    +45.0     +22.2    6.627   6.582   -0.045  NO
24-25   989   15    +53.4    +42.9     +10.5    4.265   4.240   -0.025  NO
25-26   1144  8     +25.1    +13.0     +12.1    1.906   1.896   -0.010  NO
(gain/spread sign agreement 5/5; no framing conflict.)

Worst daily sum + maxDD of daily-sum cumsum path (renorm sizes):

year    W_dep    W_new    tail pass?  maxDD_dep  maxDD_new  raw retention
21-22   -0.434   -0.463   NO          0.539      0.575      1.11
22-23   -1.915   -1.976   NO          1.914      1.976      1.27
23-24   -0.577   -0.584   NO          0.577      0.584      0.98
24-25   -0.703   -0.713   NO          0.703      0.713      0.98
25-26   -0.498   -0.503   NO          0.588      0.594      0.98

LOYO (pooled other-4 spread vs held-out):

held-out  held_spr  pooled_other4  agree?
21-22     -135.2    -30.7          YES
22-23     -70.7     -71.0          YES
23-24     +22.2     -83.0          NO
24-25     +10.5     -81.4          NO
25-26     +12.1     -81.9          NO

Per-series spreads, bps (descriptive, min-n 5/30; null = thin):

year    FOMC n/spr       CPI n/spr
21-22   10 / +115.5      57 / -179.1
22-23   18 / -115.7      20 / -30.2
23-24   5 / +33.1        12 / +17.7
24-25   10 / +60.7       5 / -90.0
25-26   6 / +17.5        2 / null
(neither series is sign-stable; the 2021-22 pooled effect is all CPI.)

Overall pooled: n_in 155, mean_in -19.5 bps vs mean_out +40.6 bps
(spread -60.1 bps) — dominated by the two early high-n years.

## Caveats / post-hoc log

1. No outcome-driven changes. Two calendar-parser bug fixes during
   construction (before analyze ran, outcomes unseen): cross-month Fed
   ranges ('Jan/Feb 31-1' = Feb 1, not Mar 1) and the archived page's
   Jan-2022 note inside the 2021 section (explicit ', YYYY' wins).
   Covered by PLAN's official-source cross-check clause; final
   calendar has zero PLAN dates missing.
2. Tail 0/5 is partly mechanical: event bars are ~1-7% of rungs, so
   equal-exposure renorm scales non-event sizes up ~1.01-1.07x and
   deepens the worst non-event day even in the two winning years.
   The tail clause binds as pre-registered; a no-renorm tail read
   would be a different (unregistered) rule.
3. Thin late sample: n_in falls 67 -> 8 across years (fewer deep-rung
   fills land on event bars recently); 2023-25 spreads rest on
   8-17 rungs each and the 2025 CPI split is null (n=2).
4. Shutdown revisions: the Nov-2025 BLS snapshot still scheduled
   Oct-ref Nov 13 / Nov-ref Dec 10 2025; the Feb-2026 revision moved
   Nov-ref to Dec 18 and dropped Oct-ref. Union keeps all three bars
   (real-time-schedule convention); only ~2 event bars in 2025-26.
5. All five years are research data; any finding needs prospective
   validation. No engine run claimed.

## One-line verdict

NOT PROMISING: the event-bar spread flips sign after 2022 (3/5
positive, LOYO 2/5) and the blackout deepens the worst day in all 5
years (0/5 not-worse) — scheduled FOMC/CPI bars do not robustly mark
worse dip fills.
