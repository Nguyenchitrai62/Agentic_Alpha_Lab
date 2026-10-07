# OpenCode task oc_relflush - inside a multi-coin flush, size the coin that overshoots the others more (bot_only dip screen)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_relflush/` and `tests/test_oc_relflush.py`.

## Why
The deployed corr-aware sizing (v399 B1) cuts every rung to w = 1 / (1 + n_fill), n_fill = number of OTHER majors that are >= 2.5 sigma below
their own 4h bar open at minute f - 1. It treats all coins of a flush alike. Closed variants changed the SHAPE in n (oc_b1shape, oc_b1soft),
the detector (oc_b1wide, oc_b1btc) or the price (oc_b1deeper) - none used the cross-section INSIDE the flush. Hypothesis: within a flush, the
coin that has fallen further than the others (in its own sigma units) holds an idiosyncratic overshoot on top of the market move and rebounds
more; the coin that lags the flush is more likely to catch down.

## Harness
Use the dip replica of `research/tournament/oc_placebo_dip/compute_placebo_dip.py` (read its docstring and REPORT.md): exact D0 rung outcomes
(TP 1 sigma, close5 stop 4 sigma, 8-sigma backstop, timeout at next 4h open, gate fees, settle funding) with B1 sizes, four clock phases, majors
x R2 depths {2.5, 3, 3.5, 4, 5}, bars [2021-09-24, 2026-09-24). Copy what you need into your folder (do not edit oc_placebo_dip). Reproduce its
base 5y 4-phase-mean sum 7.718 first; else stop.

## Variants (fixed; all bot_only, information up to minute f - 1 of the fill)
For a fill of coin i at minute f with n_fill >= 1: d_x = -log(P_x(f-1) / O_x) / sigma_x for every major x (P = 1m close of minute f - 1,
O = the bar open on the same clock, sigma = the ladder's sigma of coin x); F = the set of OTHER majors with d_x >= 2.5 (the B1 flush set);
rel = d_i - mean_{x in F} d_x. Fills with n_fill = 0 keep w = 1.
- R1: w = 1/(1+n) * (1.5 if rel > +0.5; 0.75 if rel < -0.5; else 1).
- R2 (sign control): w = 1/(1+n) * (0.75 if rel > +0.5; 1.5 if rel < -0.5; else 1).
- R3: w = 1/(1+n) * clip(1 + 0.25 * rel, 0.6, 1.4).
Budget / caps exactly as the replica (no re-normalisation).

## Judgement
- Established dip-screen gate (calibrated on all five years, so the most recent year is part of it - label this): PROMISING iff
  PASS_sum in >= 4/5 years AND PASS_dd (DD within +1 pp) in >= 4/5 years AND 5y 4-phase-mean sum delta >= +0.273 (placebo p95).
- Protocol view (also report): the same legs on the four dev years only (>= 3/4), choose among R1 / R3 on dev4; R2 must look like the mirror
  image of R1 for the mechanism to be believed.
- Also report: share of fills with n_fill >= 1, distribution of rel, mean outcome by rel tercile per year (descriptive, 5 years).
- Only if PROMISING: say so in bold; the leader decides whether it goes to the 4-phase engine (do NOT run the engine yourself).
