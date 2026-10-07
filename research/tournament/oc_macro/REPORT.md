# oc_macro REPORT: US macro windows (FOMC/CPI/NFP) vs dip-fill y1.0

Universe: majors (BTC/ETH/SOL/BNB/XRP) x R2 depths (2.5/3/3.5/4/5), 6876
fills, outcome y1.0 (unit rung size). Anchor years by T start each
2021-09-24 .. 2025-09-24 (n = 990/1045/1330/989/1144). Calendar:
182 releases (46 FOMC + 68 CPI + 68 NFP, 2021-01-08 .. 2026-09-16; no
Oct-2025 CPI/NFP - shutdown; all windows end before 2026-09-24) from
federalreserve.gov FOMC calendars + BLS release schedules (sources per row
in `macro_calendar.csv`). Window = [R, R+5h) half-open (release hour + 4 h
after; FOMC 14:00 ET, CPI/NFP 08:30 ET; EDT->18:00/12:30 UTC,
EST->19:00/13:30 UTC). SKIP = holding bar [T, T+4h) overlaps any window
(causal: calendar known at T; no market data loaded). 449/6876 rows SKIP=1
(6.5%); 319 fills land with t_fill inside a window.

## Verdict

NOT PROMISING per the pre-registered rule: inside-minus-outside spread
sign 3/5 positive (needs >= 4/5 either way) and LOYO sign agreement 1/5.
Skipping macro-window bids NEVER improves the yearly worst day (0/5; the
worst daily-sum day never contains a skipped rung) while cutting the yearly
sum by up to 64%. No macro skip/filter is supported; close the direction.

## Tables

Per-year SKIP=1 (holding-bar overlap) vs SKIP=0, y1.0 in bps:
year   n_in/n_out mean_in mean_out spread  win_in/win_out min_in/min_out
21-22  126/864    -6.5    +44.7   -51.2   0.722/0.683    -1444/-1304
22-23   94/951   +26.7     +1.5   +25.2   0.681/0.696     -552/-2210
23-24  106/1224  +45.5    +39.2    +6.3   0.811/0.770     -941/-1505
24-25   36/953   +19.9    +41.9   -22.0   0.667/0.700     -202/-1353
25-26   73/1071  +22.4    +12.8    +9.6   0.671/0.655     -361/-1195
sign: 2 negative, 3 positive -> 3/5 dominant = FAIL (>= 4/5 needed).

LOYO (held-out spread vs pooled other-4 spread, bps):
held-out  held   pooled  agree
21-22     -51.2   +6.8   no
22-23     +25.2  -15.5   no
23-24      +6.3  -12.1   no
24-25     -22.0   -4.3   yes
25-26      +9.6  -12.1   no
agreement 1/5 = FAIL. Overall pooled spread -9.3 bps (28.6 vs 37.9).

Skip simulation per year (unit size; cut = fraction of yearly sum given up):
year   S_full S_skip cut     worst_day_full worst_day_skip tail?
21-22  3.777  3.859  -0.022  -0.430         -0.430         no
22-23  0.393  0.143  +0.638  -1.924         -1.924         no
23-24  5.276  4.794  +0.091  -0.496         -0.496         no
24-25  4.066  3.994  +0.018  -0.507         -0.507         no
25-26  1.538  1.374  +0.106  -1.018         -1.018         no
Useful skip (tail improves AND 0 <= cut <= 5%): 0/5 years.

Descriptive per-series holding-bar spreads, bps [n] (NOT part of the rule):
FOMC: +79.3 [29], -31.4 [40], null [6], +34.2 [13], null [6] -> flips.
CPI:  -101.4 [84], +67.3 [51], +40.3 [54], -64.5 [19], -62.9 [20] -> flips.
NFP:  -17.8 [13], null [3], -34.8 [49], null [4], +39.4 [47] -> flips.
t_fill-inside-window mean y1.0 overall +23.0 bps (n=319) vs +37.9 outside -
same sign as SKIP pooled (-9 bps) but both positive; not actionable at T.

## Caveats / post-hoc log

1. No post-hoc change to calendar, windows, universe, outcome, minimum-n,
   or the decision rule. The only code fix (daily-sum groupby length) fired
   before any outcome was produced (first run crashed with no output).
2. First-four-year sensitivity (repo selection uses 2021-2024): spreads
   -51/+25/+6/-22 = 2/2 split, LOYO agreement on first four 1/4 - still a
   clear fail; the 2025 year does not rescue or condemn anything.
3. Small n_in per year (36-126, 2024 only 36 with no n>=10 FOMC/NFP split)
   is inherent: 5h windows x ~32 events/yr ~= 1.8% of clock time. The
   minimum-n bar (10) was fixed for this reason; raising it would only add
   FAILs. Effect sizes (+/-10..50 bps) sit near the ~4-8 bps cost scale but
   with flipping signs they are noise, not edge.
4. The worst-day result is structural, not a power issue: in all 5 years
   the worst daily-sum day consists entirely of non-overlapping bars, so no
   calendar skip of this form can touch the tail. A wider window (e.g. full
   release day) would cut far more sum for the same null tail benefit.
5. Causality: SKIP uses only T + the pre-published calendar (flag-recompute
   test drops all market/outcome columns); no minute at/after 2026-09-24
   is used. All five years are research data per the assignment; this
   negative finding needs no prospective follow-up beyond keeping the
   direction closed.

## One-line verdict

NOT PROMISING: macro-window dip fills differ from outside fills with
flipping signs (-51/+25/+6/-22/+10 bps, LOYO 1/5) and skipping them never
improves the yearly worst day while cutting up to 64% of the sum - no
macro filter; close the direction.
