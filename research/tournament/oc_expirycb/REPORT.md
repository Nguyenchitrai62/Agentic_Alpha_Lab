# oc_expirycb REPORT: COMBINATION of oc_expirybook + oc_cbpremium on the BOT book

Post-hoc informed combination, labelled. BASE = `forward_v205.research_books_d2`
(rebuilt exactly, cf oc_dvolshort) + v410 bear-long filter FIRST (control);
opens = v154 4h opens. Grid = 10955 bars (2021-09-24..2026-09-23 16:00 UTC;
last bar dropped, no forward open) x 5 coins = 54775 rows.
PREM = BASE with book LONG targets x1.15 when premium z > 1, x0.85 when
z < -1, else x1.0 (BTC-only Coinbase-premium signal to all 5 coins;
shorts/flats/NaN-z bit-identical; z exactly as oc_cbpremium/oc_optctx with
strict as-of end <= T - 1s). EXP = BASE x0.5 both sides on holding bars with
T in [E-48h, E) for E = last Friday of month 08:00 UTC (68 expiries,
exactly as oc_expirybook), else BASE. BOTH = expiry halving applied AFTER
the premium tilt (w_both = 0.5*w_prem on window bars, else w_prem).
Screen = open-to-open 4h returns with gate costs, exactly as the parents:
net cell = `w*R1 - 0.0002*|w - w_prev|` per sym (first prev = 0; each of the
4 paths its own prev chain). Equity per year reset to 1 and compounded as
`eq *= 1 + sum_s pnl`; maxDD = peak-to-trough; worst week = min 42-bar
compounded return. Full tables in `results.json`; `panel.parquet` holds
per-(T,sym) rows. Coverage of z is 100% all years; expiry share ~6.6%
(2021 = 134 bars, partial first window). Cost note: the assignment text says
"0.05% per unit turnover" but tells us to reuse oc_dvolshort's code, which
(and both parents) uses maker 0.0002; this screen uses 0.0002 so that
EXP reproduces oc_expirybook and PREM reproduces oc_cbpremium exactly
(verified below). No LOYO: neither parent has a fitted parameter, and the
combination adds none, so LOYO is N/A by construction.

## Verdict

NOT PROMISING (as assigned): vs BASE, the combination has P&L higher in 4/5
years (needs >= 4/5: pass) BUT maxDD not worse in only 1/5 years (needs
>= 4/5: fail). It adds the premium return (both beats prem-only P&L only in
3/5, beats exp-only P&L in 4/5) but does NOT keep the expiry DD benefit
(expiry-only DD not worse is 4/5 in its report; both-vs-base DD passes only
2022; both-vs-exp DD is not-worse in only 2/5: 2022 better, 2023 tie, rest worse).

## Per-year screen (net, portfolio-return units; costs included)

| year | book P&L base / exp / prem / both | worst week base / exp / prem / both | maxDD base / exp / prem / both | both DD<=base | both P&L>base |
|---|---|---|---|---|---|
| 21-22 | 0.291959 / 0.272183 / 0.295310 / 0.272588 | -0.055143 / -0.055143 / -0.062919 / -0.062919 | 0.086514 / 0.090484 / 0.083498 / 0.087415 | no | no |
| 22-23 | 0.252013 / 0.266552 / 0.259930 / 0.274769 | -0.046676 / -0.046676 / -0.046676 / -0.046676 | 0.071462 / 0.070298 / 0.067830 / 0.066661 | yes | yes |
| 23-24 | 0.564138 / 0.566512 / 0.573746 / 0.576693 | -0.069232 / -0.069232 / -0.069232 / -0.069232 | 0.087278 / 0.087278 / 0.087397 / 0.087397 | no (+0.000119) | yes |
| 24-25 | 0.539535 / 0.544192 / 0.541817 / 0.546098 | -0.045264 / -0.045264 / -0.043038 / -0.041787 | 0.062817 / 0.059411 / 0.070370 / 0.066968 | no | yes |
| 25-26 | 0.413608 / 0.427729 / 0.431642 / 0.444429 | -0.074825 / -0.074825 / -0.079609 / -0.079609 | 0.085657 / 0.085657 / 0.089602 / 0.089602 | no | yes |

Counts (both vs base): DD not worse 1/5; P&L higher 4/5. Full 5y path
(context, compounded from year-1 start): total P&L base 2.061253 /
exp 2.077167 / prem 2.102446 / both 2.114578 (both highest); maxDD base
0.100471 / exp 0.090484 / prem 0.102295 / both 0.089602. Both-vs-singletons
(context): P&L both > exp in 5/5 (2021 is close, +0.000405, but still higher);
P&L both > prem in 4/5 (fails only 2021: 0.272588 < 0.295310; wins 2022-2025); DD both <= exp in 2/5 (2022, 2023-tie;
2021/2024/2025 worse); DD both <= prem in 3/5 (2021 worse, 2022 better, 2023
tie, 2024 better, 2025 tie => 3/5 with ties).

Read: the premium tilt's variance dominates the combination. The only year
both legs pass is 2022 (expiry window loss halved AND premium tilt DD win
stack: DD 0.0715 -> 0.0667, P&L 0.2520 -> 0.2748). In 2023 the DD fail is
+0.01pp (a tie-to-loss inherited from prem); in 2024 the expiry DD win
(0.0628 -> 0.0594 alone) is more than undone by the premium tilt
(prem 0.0704, both 0.0670); in 2025 both inherits prem's DD loss exactly
(0.0857 -> 0.0896) while adding its P&L gain; in 2021 both fails both legs
like expiry-only (window was profitable, halving hurt) plus prem's worst-week
worsening (-0.0551 -> -0.0629). Worst week: both equals prem every year
(the expiry gate never touches the year's worst 7-day stretch; the premium
tilt worsens 2021/2025, improves 2024). Both-path turnover costs run highest
every year (+0.0005 to +0.0012 over base) from stacking two tilt round-trips.

## Parent reproduction cross-check (same grid, same 0.0002 costs)

- EXP per-year P&L / maxDD reproduce `oc_expirybook/results.json` rule leg
exactly (0.272183/0.266552/0.566512/0.544192/0.427729;
0.090484/0.070298/0.087278/0.059411/0.085657).
- PREM per-year P&L / maxDD reproduce `oc_cbpremium/results.json` rule leg
exactly (0.295310/0.259930/0.573746/0.541817/0.431642;
0.083498/0.067830/0.087397/0.070370/0.089602).
- BASE per-year P&L / maxDD reproduce both parents' base exactly
(0.291959/0.252013/0.564138/0.539535/0.413608;
0.086514/0.071462/0.087278/0.062817/0.085657; total 2.061253, full DD 0.100471).

## Caveats / post-hoc log

1. No post-hoc change to hypothesis, calendar, window, factor (0.5),
multipliers (1.15/0.85, z +/-1), bear rule, costs, or the decision rule.
PLAN.md was written before `compute_expirycb.py` ran.
2. Post-hoc informed by construction (parents' outcomes 4/5-DD expiry and
5/5-P&L premium were known when this combination was specified); labelled
as such. No new parameter was fitted, but selection of THESE two parents
used their test-year scores, so this screen is in-sample over research data
and needs prospective validation.
3. Vectorised open-to-open screen only (no vol target, governor, dip sleeve,
funding, SL/TP, or engine limit path); maker cost only (0.0002/unit
turnover, each path's own chain). Assignment's "0.05%" cost text logged in
PLAN.md; no 0.0005 variant was run (LIGHT single run to keep the parents
exactly comparable).
4. In 2021 the expiry window is the partial first window (134 vs 144 bars);
2021 is the only year both-vs-exp P&L comparison is close
(+0.000405) and the only year both loses to prem on P&L.

## One-line verdict

NOT PROMISING (as assigned): halving the premium-tilted book in the 48h before monthly Deribit expiry lifts book P&L vs base in 4/5 years but keeps DD not worse in only 1/5 (2022) — the premium tilt's variance survives the expiry gate, so the combination adds return without keeping the DD benefit.
