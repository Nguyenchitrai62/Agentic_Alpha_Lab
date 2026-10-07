# oc_idea10 REPORT: 1h-confirmation filter on 4h dip bids (IDEAS.md #10)

Universe: majors (BTC/ETH/SOL/BNB/XRP) x R2 depths (2.5/3/3.5/4/5), 6876
fills, outcome y1.0 (unit rung size). Anchor years by T start each
2021-09-24 .. 2025-09-24 (n = 990/1045/1330/989/1144). Gate (frozen in
PLAN.md): state = (open_T - min low of prior six 1h bars) /
(open_T * sigma_ret), 1h bars strictly < T, sigma_ret = v293 360-bar std
(min_periods 120, ddof=1, shift 1) on 4h opens from hourly_ext; KEEP iff
state > 1.0 strict, NaN -> drop (fail-closed). Hourly_ext + fills_U_ext
only (no 1m); state coverage 100% in all 5 years; cutoff 2026-09-24 00:00.
Equal-exposure rescale: S_kept_eq = S_kept * n_full/n_kept, worst-day on
T-date daily sums rescaled by the same factor. All five years are research
data per the assignment; a PROMISING filter would still need prospective
validation.

## Verdict

NOT PROMISING per the pre-registered rule: kept-vs-full spread positive
2/5 (needs >= 4/5), LOYO sign agreement 0/5, worst-day improvement 2/5.
The gate halves the ladder (kept-share 34-57%, far below the ~90%
interest bar) while flipping sign year to year; win rate lifts only in
2/5 years. No 1h-confirmation filter; close the direction.

## Tables

Per-year kept (state > 1.0) vs full, y1.0 in bps (spread = kept - full):
year   kept/n  share  mean_kept mean_full spread  win_kept/win_full S_full S_kept_eq gain_eq cut_raw
21-22  335/990  0.338   +31.3    +38.2    -6.9   0.675/0.688       3.777  3.097   -0.680  +0.723
22-23  496/1045 0.475   -12.8     +3.8   -16.6   0.683/0.695       0.393 -1.339   -1.732  +2.615
23-24  762/1330 0.573   +54.9    +39.7   +15.3   0.806/0.773       5.276  7.304   +2.028  +0.207
24-25  509/989  0.515   +27.7    +41.1   -13.4   0.692/0.699       4.066  2.740   -1.325  +0.653
25-26  548/1144 0.479   +24.3    +13.4   +10.9   0.679/0.656       1.538  2.781   +1.243  +0.134
sign: 2 positive, 3 negative -> 2/5 = FAIL (>= 4/5 positive needed).
Pooled overall: kept mean +31.9 bps (n=3544) vs full +37.3 bps -> spread -5.4 bps.

LOYO (held-out spread vs pooled other-4 spread, bps):
held-out  held   pooled  agree
21-22     -6.9    +2.2   no
22-23    -16.6    +4.1   no
23-24    +15.3    -6.7   no
24-25    -13.4    +3.3   no
25-26    +10.9    -2.5   no
agreement 0/5 = FAIL. Every held-out year disagrees with its pooled other-4.

Tail (T-date daily sums, equal exposure; worst day + maxDD of cumulative):
year   worst_full worst_kept_eq tail?  maxDD_full maxDD_kept_eq
21-22  -0.430     -0.392        yes    -0.435     -0.848
22-23  -1.924     -2.020        no     -2.282     -2.743
23-24  -0.496     -0.440        yes    -0.496     -0.440
24-25  -0.507     -0.651        no     -0.507     -0.812
25-26  -1.018     -1.044        no     -1.269     -1.268
tail improves 2/5 = FAIL (>= 4/5 needed). MaxDD_kept_eq worse than full in
3/5 years (2021 maxDD doubles despite a better worst day).

## Caveats / post-hoc log

1. No post-hoc change to gate, universe, outcome, minimum-n, or decision
   rule. Two pre-outcome code fixes only (tz-aware -> int64 ns key
   conversion in analyze_idea10.py + tests; no outcome had been produced).
2. Effect sizes (-17/+15 bps spreads) sit near the ~4-8 bps cost scale but
   flip sign (2023/2025 positive, 2021/2022/2024 negative) with LOYO 0/5:
   noise, not edge. Kept means stay positive every year, so the gate is
   not toxic -- just non-predictive.
3. Retention 34-57% misses the IDEAS.md interest bar (>= 90%) by a wide
   margin: the 1.0 threshold on a median state of 0.65-1.24 removes about
   half the ladder and cuts 13-72% of the raw yearly sum (2022 kept sum is
   negative, cut 262%). Win-rate lift (+3.3pp in 2023, +2.3pp in 2025) does
   not replicate (down in 2021/2022/2024).
4. First-four-year sensitivity (repo selection uses 2021-2024): spreads
   -7/-17/+15/-13 = 1/4 positive, LOYO on first four 0/4, tail 2/4 -- still
   a clear fail; the 2025 year does not rescue or condemn anything.
5. Causality: state uses only hourly rows with t <= T (truncation +
   future-perturbation tests), sigma is rolling-360/shift-1 on 4h opens
   strictly before T, KEEP recomputed after dropping all y-columns is
   identical. One process, hourly + fills only, RAM < 1 GB.

## One-line verdict

NOT PROMISING: 1h-confirmation (state > 1.0) flips sign (-7/-17/+15/-13/+11 bps, LOYO 0/5) and improves the equal-exposure worst day in only 2/5 years while keeping just 34-57% of fills -- no filter; close the direction.
