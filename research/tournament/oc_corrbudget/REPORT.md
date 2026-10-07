# oc_corrbudget REPORT: 30d majors correlation as dip budget scaler

Universe: majors (BTC/ETH/SOL/BNB/XRP) x R2 depths (2.5/3/3.5/4/5), 6876 fills,
758 fill-days, outcome y1.0 (net, unit rung notional). Anchor years start each
2021-09-24 .. 2025-09-24 (fills/days = 990/109, 1045/127, 1330/137, 989/121,
1144/117). c(D) = 30d mean pairwise Pearson of majors hourly log returns, bar
END in [D-30d, D) only (strictly before D 00:00); 10/10 pairs valid on every
fill-day (coverage 100% in all 5 years). c drifts up over time (sequential
q33: 0.53/0.61/0.65/0.62/0.64), so late-year days pile into Hi (2021: 102/109
Hi; 2025: 97/117 Hi). y1.0 already nets fees + adverse funding; sums in bps
per unit rung notional.

## Verdict

NOT PROMISING under the pre-registered rule: E1 sequential 1/5, E1 LOYO 0/5,
scaler PASS 0/5. The scaler does shrink every worst day (~40% smaller loss)
but only by scaling EVERYTHING down ~40% (retention 0.54-0.62, always below
the 0.90 bar) — uniform 1/(1+c) with c in [0.5, 0.8] is ~0.55-0.67 every day,
so the retention leg is arithmetically out of reach. Crash days concentrate in
the MID tercile, not Hi, in 3 of 5 years.

## Tables

Per-year base vs scaled (equal notional daily sums; W = worst day):

year    S_base  S_scaled  ret   W_base   W_scaled  worst_date  pass?
21-22   +37766  +21441    0.57  -4301    -2489     2021-12-04  NO (ret)
22-23   +3934   +2118     0.54  -19236   -11620    2023-08-17  NO (ret)
23-24   +52761  +32468    0.62  -4963    -2983     2024-08-05  NO (ret)
24-25   +40658  +24494    0.60  -5070    -3125     2024-12-20  NO (ret)
25-26   +15380  +8446     0.55  -10180   -6018     2025-10-10  NO (ret)
(units bps; S_base > 0 every year, so the retention check is defined.)

Worst daily sum by correlation tercile, bps [n_days], sequential cut-offs
(previous data only; E1 = worst_Hi < worst_Lo, needs >= 10 days in Lo and Hi):

year    q33/q67        Lo worst     Mid worst    Hi worst     E1
21-22   0.53/0.64      — [0]        +184 [7]     -4301 [102]  FAIL (no Lo days)
22-23   0.61/0.75      +16 [15]     -19236 [93]  -63 [19]     True (fragile: Lo never lost)
23-24   0.65/0.73      -1734 [73]   -4963 [46]   -1105 [18]   False (worst in Mid)
24-25   0.62/0.72      -5070 [21]   -3351 [54]   -2416 [46]   False (worst in Lo)
25-26   0.64/0.72      — [0]        -10180 [20]  -3469 [97]   FAIL (no Lo days)

LOYO terciles (training = other 4 years; E1 needs >= 10 days in Lo and Hi):

held-out  Lo worst [n]     Hi worst [n]      E1
21-22     +77 [8]          -3535 [80]        FAIL (<10 Lo days)
22-23     -19236 [51]      +9 [11]           False (worst in Lo)
23-24     -4963 [110]      -170 [11]         False (worst in Lo)
24-25     -5070 [45]       -651 [9]          FAIL (<10 Hi days)
25-26     — [0]            -3469 [92]        FAIL (no Lo days)

Descriptive (NOT part of the rule): Spearman rho(c(D), s(D)) per year =
+0.05 / -0.00 / -0.20 / -0.10 / -0.23 (4/5 negative: higher correlation leans
toward worse daily sums, but the worst-day extremes do not sit in Hi).

## Caveats / post-hoc log

1. No post-hoc change to definitions, universe, cut-offs, or the decision
   rule. Code-only fixes after the first run attempt (path parents index,
   one paren) touched plumbing, not logic; results come from a single
   scoring run.
2. Correlation non-stationarity breaks the tercile design: 30d c rises from
   ~0.5 (2020) to ~0.7 (2025), so backward-looking cut-offs leave 2021 and
   2025 with zero Lo days (automatic FAILs). A detrended or trailing-window
   bucketing would be a different, unregistered variant.
3. The 2022 E1 "True" is hollow: Lo's worst day is +16 bps (no losing Lo day
   at all, n = 15) while the year's true crash (-19236 bps) sits in Mid.
4. The scaler was tested exactly as assigned (multiply EVERY day by
   1/(1+c)); a selective gate (scale only Hi days) could retain the sum but
   was not pre-registered and is not claimed here.
5. All five years are research data (assignment override to 2026-09-24);
   findings need prospective validation. No 1m data loaded; peak RAM ~0.3 GB.

## One-line verdict

NOT PROMISING: high-correlation days do not hold the worst crashes (E1 1/5
sequential, 0/5 LOYO) and uniform 1/(1+c) scaling cuts the yearly sum ~40%
(retention 0.54-0.62, 0/5 pass) — correlation is not a usable dip budget scaler
in this form.
