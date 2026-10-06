# oc_placebo REPORT: false-positive rate of the vectorised BOT book screen

Seeded placebo study for the two vectorised-screen PROMISING rules that both
failed the full 4-phase engine check (`oc_expiry4p` VERDICT: NO,
`oc_cmegap4p` VERDICT: NO): `oc_expirybook` (idea #62, 48h pre-expiry book
halving) and `oc_cmegap` (idea #69, CME weekend-gap long tilt).

## Setup (fixed before running)

Screen (per assignment, unified for all rules here): BASE = rebuilt
`forward_v205.research_books_d2` + v410 bear-long filter FIRST (longs x0.5
where BTC 4h open < rolling-1200 mean, min 600); open-to-open 4h returns;
0.0005/unit turnover (each path own prev, first prev = 0); per-year equity
reset to 1, `eq *= 1 + sum_s pnl`; peak-to-trough maxDD. Grid = 10955 bars
(2021-09-24..2026-09-23 16:00 UTC, last bar dropped) x 5 coins, identical to
both original studies. Seed 20261006; windows use ONLY grid timestamps + RNG
(never returns/weights). 1000 expiry-like + 1000 CME-like rules, streaming
(one rule at a time; no per-rule panels). Full tables in `results.json`;
script `compute_placebo.py`.

Placebo shapes (literal geometry; coverage hints in the assignment understate
4h-bar arithmetic, realised shares reported): (a) expiry-like: one contiguous
12-bar window per calendar month, uniform start inside the month (fully inside,
no overlap), halve both sides -> 61 x 12 = 732 bars, mean coverage 0.066819
(real expiry: 710 bars, 0.0648). (b) CME-like: per anchor year 10 windows,
length uniform in {12,18,24} bars, uniform start inside the year,
non-overlapping, random sign per window (longs x0.75/x1.25; shorts/flats
unchanged) -> mean coverage 0.081935 (real CME: 742 bars, 0.0677).

Criteria (same legs as each original report): expiry: DD not worse in >= 4/5
years AND total P&L >= 98% of base in >= 4/5 years. CME-strict (report text):
total P&L >= base in >= 4/5 AND DD not worse in 5/5; CME-loose (compute code):
both legs >= 4/5 (sensitivity row only).

Real-rule reference is rescored under this SAME 0.0005 screen (expiry calendar
rebuilt; CME windows from `oc_cmegap/panel.parquet` mapped onto the rebuilt
base; base bit-matches the CME base: yearly totals 0.278895 / 0.235444 /
0.544150 / 0.517693 / 0.394724, full maxDD 0.104644).

## Real rules under the unified 0.0005 screen (context)

| rule | legs | 5y dPnl (rule-base) | full-path dDD |
|---|---|---|---|
| expiry (real 48h halving) | DD 3/5, ret98 4/5 -> FAILS legs | +0.013292 | -0.008425 |
| CME (real gap tilt) | P&L 4/5, DD 5/5 -> passes strict+loose | +0.005655 | -0.000000 |

Cost-change disclosure: at its ORIGINAL 0.0002 costs the expiry rule passed
4/5 + 4/5 (5y dPnl +0.015914, dDD -0.009987). Under the unified 0.0005 screen
the 2023 DD tie (0.087902 vs 0.087902 at 6dp) flips to a microscopic loss, so
DD falls to 3/5. The CME rule is unaffected (its original costs were already
0.0005: 5y +0.005655, dDD 0.0).

## False-positive rates (share of placebos passing each criterion)

| family | criterion | FPR |
|---|---|---|
| expiry-like (n=1000) | 4/5 DD + 4/5 ret98 | 0.037 (37 pass; legs: DD>=4 0.302, ret>=4 0.082) |
| CME-like (n=1000) | strict 4/5 P&L + 5/5 DD | 0.002 (2 pass) |
| CME-like (n=1000) | loose 4/5 + 4/5 (sensitivity) | 0.024 (24 pass; legs: P&L>=4 0.159, DD==5 0.014, DD>=4 0.125) |

Binomial SE ~0.6pp at 3.7% (95% CI ~2.5-4.9%), ~0.14pp at 0.2%.

## Placebo distributions vs the real rules (5y book P&L delta, full-path maxDD delta)

Expiry-like placebos (halving a profitable book at random times loses money):
dPnl mean -0.077005, p5 -0.163713, p50 -0.075762, p95 +0.005795, max +0.081580.
dDD mean -0.001509, p5 -0.007659, p50 -0.001136, p95 +0.005339.
Real expiry (+0.013292 / -0.008425): P&L percentile 97.0 (better than 97% of
placebos), DD percentile 1.8 from below = better than 98.2% (top-tail DD
improvement). Genuine outlier vs random halving -- but the leg-count criterion
still lets 3.7% of random halvings through.

CME-like placebos (random long tilts average ~flat): dPnl mean -0.003823,
p5 -0.050464, p50 -0.004370, p95 +0.042143, max +0.077921. dDD mean +0.000324,
p5 -0.004164, p50 +0.000069, p95 +0.005251.
Real CME (+0.005655 / -0.0): P&L percentile 63.0, DD percentile 48.1 --
squarely inside the null (a typical random tilt). The strict 5/5-DD criterion
is stringent (FPR 0.2%), so the CME screen pass looks like selection luck
across many tested ideas rather than a real edge -- consistent with the
engine NO (2023 -0.416 %/mo).

## Recommended stricter screen (FPR <= 5%)

Require the original legs PLUS joint placebo-tail gates: 5y dPnl >= placebo
p95 AND full-path dDD <= placebo p05. Gates: expiry dPnl >= +0.005795 and dDD
<= -0.007659; CME dPnl >= +0.042143 and dDD <= -0.004164. Realised joint FPRs:
expiry legs+both-tails 0.002; CME strict+both-tails 0.000 (single-tail rows:
expiry legs+pnl-tail 0.017, legs+DD-tail 0.002; CME strict+pnl-tail 0.000,
strict+DD-tail 0.000 -- all <= 0.05). Neither real rule passes the joint gate
(expiry fails the DD leg-count 3/5 under unified costs despite passing both
tails; CME passes the legs but fails both tails), so neither would have been
promoted -- matching both engine NO verdicts. Adopt legs + both placebo tails
(p95 / p05, i.e. placebo-percentile >= 95 on both effect sizes) as the screen;
it holds FPR at ~0.2% / 0.0% with margin under the 5% budget.

## Caveats

1. Unified 0.0005 costs flip the real expiry leg-count vs its original 0.0002
   report (disclosed above); percentiles are apples-to-apples under 0.0005.
2. Coverage hints in the assignment (~4% / ~1.5%) understate 4h-bar
   arithmetic; literal window geometry was used and realised shares (6.7% /
   8.2%) match the real rules (6.5% / 6.8%) better than the hints.
3. N=1000 per family: tail-gate FPRs of 0.000-0.002 have large relative Monte
   Carlo error; the <= 5% budget holds with wide margin regardless.
4. Vectorised open-to-open screen only (no vol target, governor, dip sleeve,
   funding, SL/TP, engine limit path); placebo says nothing about engine
   transfer beyond the two observed NOs.
5. FPRs are within-criterion rates for one idea; they do not include
   multiple-testing across the ~100-idea tournament (which only strengthens
   the "CME pass was luck" reading).

## Verdict

WEAK SCREEN: random calendar halving passes the expiry legs 3.7% of the time (real expiry is a genuine tail outlier yet fails the unified leg-count on a tie-break); random long tilts pass the CME loose legs 2.4% (strict 0.2%) with the real CME tilt sitting at placebo percentiles 63/48 -- adopt legs + placebo p95/p05 joint tails (joint FPR 0.2%/0.0%), under which neither rule promotes, consistent with both engine NOs.
