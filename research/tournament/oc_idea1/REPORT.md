# oc_idea1 REPORT: late-fill fast-TP (TP 0.5 sigma iff f >= 209)

## Setup

Majors (BTC/ETH/SOL/BNB/XRP) R2 rungs (`x1` in {2.5,3,3.5,4,5}) from
`research/tournament/ext/fills_U_ext.parquet` joined 1:1 to
`research/tournament/oc_b1shape/fills_n.parquet` (`n` = `n25` detections
among the 4 other majors; reused for the 1/(1+n) weights ONLY, no 1m read
here). Join keys (sym, Bx=T, t_fill, f, k): 6876/6876 rows joined,
max |y1.0 diff| = 0. Years = 5 anchors 2021-09-24..2025-09-24,
`[anchor, anchor+365d)` keyed by `T` (5498 fills: 990/1045/1330/989/1144;
1378 rows outside dropped). Outcomes `y0.5/y1.0/y1.5` are exact nets
(fees/funding in; stops/timeout unchanged). Late = f >= 209 (last 30 fillable
minutes; 16.4% of 5y fills; per-year share 17.6/17.0/12.3/14.3/21.5%). All 5
years are research data per assignment (disclosed vs RULES.md hidden-year
rule); a PROMISING rule still needs prospective validation.

## Mean net by fill-timing bucket (unweighted rung means; win = y1.0 > 0)

| year | early f<209: mean y0.5/y1.0/y1.5 (n, win) | late f>=209: mean y0.5/y1.0/y1.5 (n, win) | mean(y0.5-y1.0) early / late |
|---|---|---|---|
| 2021-09-24 | .003071/.004092/.003802 (816, .712) | .001898/.002516/.002245 (174, .575) | -0.001021 / -0.000618 |
| 2022-09-24 | -.000647/.000552/.000899 (867, .731) | -.000343/-.000479/-.000347 (178, .517) | -0.001199 / +0.000136 |
| 2023-09-24 | .001910/.004353/.005269 (1166, .788) | .001046/.001226/.001873 (164, .665) | -0.002443 / -0.000179 |
| 2024-09-24 | .003171/.004664/.005047 (848, .730) | .000929/.000786/.001161 (141, .511) | -0.001493 / +0.000143 |
| 2025-09-24 | .000451/.000947/.000815 (898, .669) | .001621/.002794/.003320 (246, .606) | -0.000496 / -0.001172 |
| overall | .001581/.002981/.003273 (4595, .730) | .001075/.001497/.001790 (903, .578) | -0.001400 / -0.000422 |

Late fills trail early fills on y1.0 in 4/5 years (as in oc_filltime) but the
fast-TP leg y0.5 beats y1.0 on late fills in only 2/5 years (2022, 2024, by
+13.6/+14.3 bps); in 2021/2023/2025 y0.5 loses to y1.0 even on late fills.

## Rule test at sizes 1/(1+n), equal exposure (w' = w/mean(w) per year)

A = always TP 1.0 (`yA = y1.0`); B = TP 0.5 iff late else 1.0
(`yB = y0.5 if f>=209 else y1.0`). S = sum(w'*y); days by T.floor(D).

| rule | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| A always1.0 S | 3.9546 | 0.2905 | 5.7374 | 3.9523 | 1.2367 |
| B tp05_if_late S | 3.8392 | 0.2738 | 5.5837 | 3.9980 | 1.0157 |
| D = B - A | -0.1154 | -0.0167 | -0.1537 | +0.0457 | -0.2210 |
| LOO mean D excl. year | -0.0864 | -0.1111 | -0.0769 | -0.1267 | -0.0600 |

Tails: worst-day per year A: -0.7134/-1.0811/-0.3979/-0.3312/-0.9030
(overall -1.0811, maxDD -1.6976); B: -0.7134/-1.0447/-0.3979/-0.3312/-0.9156
(overall -1.0447, maxDD -1.7200). Worst-day-not-worse (B >= A): 4/5 years
(only 2025 worse); overall worst day improves (-1.04 vs -1.08) but full-path
maxDD deepens slightly (-1.72 vs -1.70).

## Decision (PROMISING = D>0 in >=4/5y AND LOO D>0 in >=4/5 AND worst-day-not-worse in >=4/5)

D>0 in 1/5 years (only 2024); LOO>0 in 0/5; worst-day-not-worse in 4/5. First
two conditions fail decisively.

## Verdict

NOT PROMISING: late-fill fast-TP (0.5 sigma iff f>=209) loses vs always-1.0 in 4/5 years (D>0 only 2024; LOO 0/5) despite meeting the worst-day bar 4/5; keep always-1.0.

## Caveats / repro

- No post-hoc change: threshold 209, weights 1/(1+n), equal-exposure rescale,
  and the 3-part decision rule were all pre-registered in PLAN.md before any
  outcome was computed.
- The fast-TP leg does not harvest a timeout bleed: on late fills y0.5 < y1.0
  in 3/5 years (2021/2023/2025), and the single winning year (2024, +0.0457)
  is the smallest |D| of the five.
- Repro: `research/tournament/oc_idea1/{PLAN.md,analyze_idea1.py,
  results.json,REPORT.md}` (reuses `oc_b1shape/fills_n.parquet`; one process,
  no 1m, RAM < 1 GB) + `tests/test_oc_idea1.py`.
