# OpenCode task oc_kronosmanual - an EX-ANTE (bar-open) substitute for corr-aware dip sizing in the MANUAL product, from Kronos drop forecasts
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_kronosmanual/` and `tests/test_oc_kronosmanual.py`.

## Why
MANUAL (human-placeable bracket dip limits + book) earns ~3.73 %/month honestly (research/diagnostics/manual_human; floor 5). The BOT's key
DD tool - corr-aware sizing w = 1/(1+n), n = other majors flushing at the fill minute (v399) - needs minute data, so a human cannot use it; a
STATIC proxy failed 0/5 (oc_manual3). Kronos gives, at the bar open, each coin's probability of a > 2-sigma drop inside the bar (pdrop2): the
expected number of OTHER coins flushing, E[n] = sum over other majors of pdrop2, is known before the human places the bracket orders.
CAVEAT: dev years likely inside Kronos' pretraining (released 2025-08) -> dev = upper bound; most recent year = clean test.

## Inputs
`research/tournament/oc_kronoshidden/kronos_features_4shift.parquet` (all four shifts; wait until all 20 (shift, sym) groups exist, poll every
10 minutes, at most 2 hours). MANUAL harness: research/diagnostics/manual_human/manual_human.py and the oc_manualcap copy used by
research/tournament/oc_manualsplit (reproduce M5_human 3.728 / DD 17.94 / full 17.79 bit-exact first, as oc_manualsplit did).

## Rule (fixed; dip bracket sizes only, book unchanged)
At each bar open T (clock shift s uses its own rows): E_n(coin) = sum of pdrop2 of the four OTHER majors.
- KM1: every bracket rung of that coin and bar x 1 / (1 + E_n).
- KM2: x 1 / (1 + 2 E_n) (stronger).
- CTRL: x 1 / (1 + c) with c = the mean of E_n over the training rows (constant scaling, exposure control).
Then rescale each variant's budget so that its average dip notional over the TRAINING rows (before each anchor minus 7 d) equals M5's (so the
comparison is at equal average risk, not just less exposure) - state the scale factors.
Score dev4 (4-phase mix, MANUAL human schedule) choose KM1 vs KM2 by the robust criterion; most recent year once for the chosen, CTRL and M5.
Verdict: does the chosen row close part of the MANUAL gap (>= 5 %/month, DD < 20, win >= 55 %)? State the gap in pp. Vietnamese 3 lines.
