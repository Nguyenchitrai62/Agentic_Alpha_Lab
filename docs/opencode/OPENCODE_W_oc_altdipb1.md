# OpenCode task oc_altdipb1 - the G2 dip ladder WITH corr-aware sizing on three large alts (research only; trading them needs the owner's OK)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_altdipb1/` and `tests/test_oc_altdipb1.py`.
Print progress at least every 10 minutes.

## Why
v398 X11 (11-coin dip sleeve) was rejected as "correlated weak alts" (4.39 / DD 31.6) - but it ran BEFORE the corr-aware sizing (v399 B1:
w = 1/(1+n)), which is exactly the tool that defuses correlated flushes (DD 25 -> 14 on the majors). Universe rule: the owner trades only
BTC/ETH/SOL/BNB/XRP; research on other coins is allowed, deployment is not (a positive result would only be shown to the owner).

## Setup (fixed)
Dip replica of research/tournament/oc_placebo_dip/compute_placebo_dip.py (reproduce the majors base 7.718 first), extended to DOGE, ADA, TRX
(Binance USD-M 1m; find data/raw/alts2020_intraday_20260930 or data/raw/alts_intraday_20260926; check coverage 2021-09-24 .. 2026-09-24 and
listing dates). Same rules (R2 depths, TP 1 sigma, close5 4 sigma + 8 sigma backstop, timeout, gate costs, 4 clock phases).
- ALT8: the 3 alts traded alongside the 5 majors; n_fill counts flushing coins among ALL 8 (B1 rule 1/(1+n)); budget per coin as the majors.
- ALT3: the 3 alts only (n counts all 8 coins, sizes as ALT8) - the incremental sleeve.
Report per year (4-phase mean): standalone sum, DD, fills, win, stop rate for ALT3; for ALT8 vs MAJORS (base): sum, DD, and the established
dip-gate legs (labelled). Correlation of ALT3 daily P&L with the majors sleeve. Vietnamese 3-line verdict ("show to owner" only if ALT8 beats
MAJORS on sum in >= 4/5 years with DD within +1 pp in >= 4/5).
