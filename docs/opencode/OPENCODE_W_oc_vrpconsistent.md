# OpenCode task oc_vrpconsistent - weekly short-straddle overlay re-priced CONSISTENTLY at the observed 7d-ATM / DVOL ratio
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_vrpconsistent/` and `tests/test_oc_vrpconsistent.py`.
Copy the code of research/tournament/oc_vrprobust/run_robust.py / research/tournament/oc_vrpstraddle (vrp.py, run_vrp.py); do not edit them.

## Facts so far
- oc_vrpstraddle V2 (blind audit PASS-WITH-NOTES): sold at 0.97 x DVOL, SL marks 1.05 x DVOL, TP marks 1.0 x DVOL. Overlay on G2 f 0.25:
  dev4 6.57 / worst 4.37 / DD 16.10.
- oc_vrprobust part B (research/tournament/oc_vrprobust/tmp/B.json): traded 7-day ATM IV on Fridays 08:00-12:00 / DVOL = 0.868 mean,
  0.862 median, p10 0.786, p90 0.941 (61 Fridays, mostly 2021 + 2023-03 + 2025-06). So the TRUE short-dated IV is ~0.87 x DVOL.
- oc_vrprobust part A lowered ONLY the sale price (k x DVOL) but kept marks at 1.05 x DVOL - inconsistent (the SL fires too often).

## Rule (pre-registered; only these rows)
Define the true IV proxy sigma_true = r x DVOL. Re-run V2 exactly, with every sigma scaled consistently:
sale at 0.97 x sigma_true (bid haircut), SL check / SL buy-back marks at 1.05 x sigma_true (ask), TP marks at 1.0 x sigma_true, plus the
pre-registered SL/TP/settlement/fee rules unchanged.
- R087: r = 0.87 (observed median / mean).   - R080: r = 0.80 (observed p10, stress).   - R100: r = 1.0 (= the original V2; must reproduce
  6.566 / 4.365 / 16.10 on dev4 overlay exactly, else stop).
Rows: standalone V2 (dev4) and G2 overlay f = 0.25 and f = 0.10 (dev4), plus the most recent year once for R087 f = 0.25 and G2 (the recent year
has been seen for r = 1.0 only; label it).
Also report, for R087 f = 0.25: gap stress at the worst minute like oc_vrprobust C4 (-10 / -15 / +10 / +15 %) - research/tournament/oc_vrprobust/tmp/C4.json
has the method and numbers to reproduce for r = 1.0 first.

## Verdict
In bold: R087 overlay dev4 mean / worst / DD vs G2 (5.601 / 2.588 / 16.91) and the gain in pp. Adopt-worthy as a PAPER candidate only if R087
f = 0.25 beats G2 on dev4 mean AND worst year with DD <= G2 + 0.5 and R080 does not lose more than 0.3 pp vs G2. Vietnamese 3 lines.
