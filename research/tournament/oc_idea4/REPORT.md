# oc_idea4 REPORT: funding-surprise dip filter (IDEAS.md #4)

Universe: majors (BTC/ETH/SOL/BNB/XRP) x R2 depths (2.5/3/3.5/4/5), 6876
fills, outcome y1.0 (unit rung size). Anchor years by T each 2021-09-24 ..
2025-09-24 (n = 990/1045/1330/989/1144). Surprise at bar open T = last
settlement S < T (strict): V1 = settled(S) minus 60m premium TWAP before S
(primary, both legs from `data/raw/binance_premium_20260928`); V2 =
settled(S) minus previous settled (robustness). Per-coin walk-forward p80
from strictly previous dip rows (>= 100 rows else never flag); SKIP flagged
rows. No data at/after 2026-09-24 read. Script run ONCE; no post-hoc change.

## Verdict

NOT PROMISING per the pre-registered rule. The V1 surprise sign is strikingly
consistent (flagged-minus-kept negative 5/5 years, LOYO negative 4/5, agree
4/5) — surprised-coin fills do average worse every year — but the filter
fails the tail bar (worst day improves only 3/5 years) and its retention is
unstable (37-90% kept; the idea's >= 95% screen fails 5/5). V2 (settled
innovation) flips sign (2/5, LOYO 2/5, tail 0/5): the signal lives in the
premium leg, not in settled changes. A sign-consistent effect with no
reliable tail buy and up to a 54% sum cut is not a filter; close the
direction as a skip rule (the V1 spread as a descriptive crowding readout
may be reused by others, not as a trade filter).

## Tables

V1 (primary) per-year flagged vs kept, y1.0 in bps (spread = flagged - kept):
year   n_flag/n_kept mean_flag mean_kept spread  win_f/win_k ret
21-22  623/367       +32.7     +47.3    -14.6   0.677/0.706 0.37
22-23  425/620       -18.3     +18.9    -37.2   0.687/0.700 0.59
23-24  131/1199      +23.8     +41.4    -17.6   0.718/0.779 0.90
24-25  168/821       +14.4     +46.6    -32.2   0.625/0.714 0.83
25-26  411/733        +9.9     +15.5     -5.6   0.681/0.641 0.64
year neg: 5/5. V1 LOYO spread (held-out vs pooled-other-4, bps): -17.1 / -49.6
/ -12.7 / -1.9 / +12.3 -> neg 4/5, sign agreement 4/5 (only 25-26 disagrees).

V1 skip simulation (unit size; cut = fraction of yearly sum given up):
year   S_full S_skip cut     worst_full worst_skip tail?
21-22  3.777  1.738  +0.540  -0.430     -0.366     yes
22-23  0.393  1.171  -1.977  -1.924     -0.648     yes
23-24  5.276  4.965  +0.059  -0.496     -0.537     no
24-25  4.066  3.824  +0.060  -0.507     -0.507     no
25-26  1.538  1.133  +0.263  -1.018     -0.802     yes
tail improves 3/5 = FAIL (>= 4/5 needed). Retention >= 95%: 0/5 years.

V2 (innovation) spreads, bps (expect negative): +15.1 / +47.2 / -22.9 / -1.2 /
+3.3 -> neg 2/5; LOYO +39.5 / +51.3 / -34.1 / -0.3 / +4.3 -> neg 2/5, agree
2/5; tail improves 0/5 (worst day never contains a flagged rung). Retention
0.86-0.98. V2 = FAIL on all three bars.

## Caveats / post-hoc log

1. No post-hoc change to definitions, universe, cutoffs, minimum-n, or the
   decision rule. results.json is the single run of the pre-registered script.
   Test-side fixes after the run (script untouched, no outcome recomputed):
   causality-test sampling stride, threshold tolerance for the 3-decimal
   stored thr_bps, and the no-intraday scan now matches path-like tokens only
   (the generic substring also hit the docstring); PLAN.md's test bullet was
   clarified to name premium_1m as the only allowed 1m source.
2. 2021 V1 retention is 37% (623/990 flagged): the p80 fit on pre-2021 rows
   (short, bull-regime premium history; SOL/BNB series start 2020) does not
   transfer to 2021-22 — the same non-stationarity disease that killed the
   funding LEVEL (oc_fundregime), now in the threshold rather than the sort.
   2022's negative cut (-1.98) is arithmetic, not edge: flagged mean was
   negative (-18.3 bps), so dropping it raises the sum while retention is 59%.
3. First-four-year read (repo selection uses 2021-2024): V1 yearly neg 4/4 but
   tail 2/4 — fails there too, so the verdict does not hinge on the most
   recent year. Most-recent-year alone: spread -5.6 (sign holds), tail yes,
   retention 0.64.
4. Scale note (disclosed pre-run): premium std (6 bps BTC, 39 bps SOL) dwarfs
   funding steps (~1 bp), so V1 surprise is premium-dominated by construction;
   V2's failure shows settled changes alone carry nothing. Any future use of
   V1 must re-derive units (e.g. z-scored surprise), pre-registered separately.
5. All five years are research data per the assignment; this negative filter
   finding needs no prospective follow-up beyond keeping the skip direction
   closed.

## One-line verdict

NOT PROMISING: the premium-based funding surprise separates worse fills with a
consistent sign (5/5 years, LOYO 4/5) but skipping them fails the tail bar
(3/5), keeps only 37-90% of rows with cuts up to 54%, and the settled-only
variant flips sign — no skip/scale-down filter; close the direction.
