# oc_ddanat17 REPORT — drawdown anatomy of R2B1D17BF, phase s=0 (2026-10-05; PLAN pre-registered before any outcome)

## Setup
Exact v411 worker replica for shift=0 only (dips x1.7 inv-rule, budget 0.26x1.7,
bear-book filter, R2 agents from r2_table_s0, v216 grid trade policy, win_start=5),
one process, `eu.simulate` with events/attrib/path_out/bars. Live
2021-09-24..2026-09-23 (+12h mix end); 1m read to 2026-09-24 00:00 UTC. All five
years are research data (assignment override of RULES.md); no refit/selection.
Repro: `research/tournament/oc_ddanat17/{PLAN.md,run_ddanat17.py,results.json}`.

## Checks
- Rerun equity end 58.1758 == v411_runs.pkl s=0 R2B1D17BF 58.1758 (rel diff 0.0):
  bit-for-bit replica. Stats: 1312 book fills (197 stops/53 TPs), 5466 rungs
  (176 stops/2868 TPs), 0 liq, fees 0.068, funding 0.136 of equity.
- Attrib linear sums vs compounded eq move agree to <0.5pp (rest is compounding).

## Five largest 4h-close peak-to-trough episodes, s=0 (book-L / book-S / dip in % of episode-start equity)
| episode (bar-end UTC) | DD4h / DD1m | book long | book short | dip sleeve | worst dip kinds (sl/timeout/tp) | verdict |
|---|---|---|---|---|---|---|
| 2022-02-16 -> 2022-03-24 | 9.9 / 9.9 | -4.31 | -3.23 | -2.79 | sl 0.0 / timeout -4.86 / tp +2.07 | MIXED book-led bleed (no leg >50%) |
| 2022-11-04 -> 2022-11-10 (FTX) | 11.8 / 16.2 | -4.72 | +1.28 | -8.89 | sl -19.75 / timeout -5.32 / tp +16.18 | DIP stop cascade (72% of loss) |
| 2023-04-26 -> 2023-06-15 | 15.9 / 17.1 | -7.77 | +2.73 | -11.58 | sl -12.72 / timeout -9.06 / tp +10.21 | DIP stop cascade + timeout bleed (70%) |
| 2023-07-14 -> 2023-10-02 | 13.7 / 13.8 | -4.69 | -5.30 | -4.35 | sl -7.35 / timeout -3.51 / tp +6.51 | MIXED book short squeeze + long bleed |
| 2024-06-05 -> 2024-09-20 | 18.5 / 18.8 | -5.41 | -6.94 | -6.54 | sl -21.79 / timeout -1.56 / tp +16.81 | MIXED churn (dip stops churned vs TPs; XRP dip -11.8) |

## Per-coin book / dip per episode (same units)
| episode | BTC book/dip | ETH book/dip | SOL book/dip | BNB book/dip | XRP book/dip |
|---|---|---|---|---|---|
| 2022-02/03 | -1.90/-1.18 | -0.36/-0.55 | -1.90/-0.08 | -0.77/+0.03 | -2.62/-1.01 |
| 2022-11 FTX | -3.57/+1.50 | +0.53/+0.30 | -0.85/-12.63 | -0.51/+1.01 | +0.96/+0.94 |
| 2023-04/06 | -2.64/-0.51 | -2.34/-2.86 | +1.91/-2.10 | -3.30/-5.74 | +1.33/-0.36 |
| 2023-07/10 | -2.18/-0.59 | -2.56/-1.42 | -3.16/-0.08 | -0.20/-0.30 | -1.90/-1.97 |
| 2024-06/09 | -5.50/+1.88 | +1.28/+2.32 | -1.33/+2.45 | -3.02/-1.39 | -3.78/-11.81 |

## 20 worst dip rungs by loss (loss = weight x ret, % of bar-start equity)
17 of 20 are XRP stop-outs, all at FULL size (B1 count n=0: no other coin breached
2.5σ at the fill — idiosyncratic flushes, no downsize); fastest cluster 2024-06-07
fills 18:00/18:01 -> stop 18:05 (-3.17/-2.96/-2.75/-2.54%). Depths 2.5-5.0σ,
exits 19x rung_sl + 1x timeout; worst ret -14.4% (SOL 2022-05-11, weight 0.11).
Full list (exit_t, coin, n, depth, exit, loss%): see results.json worst20.

## Notes
- Dip TPs partly offset every cascade (up to +16.8 in ep5) — gross churn is large,
  the net is the stop-minus-TP remainder concentrated in one coin per episode.
- n=0 on all 20 worst rungs: the inv-rule correlation brake never engaged on the
  rungs that hurt most; sizing protection came only from the risk budget.
- Episodes 1/4/5 have no leg above 50%: capping dips alone would not remove them.

## Verdict
VERDICT: Dip stop cascades dominate 2 of the 5 largest s=0 drawdowns (FTX Nov-22 SOL, mid-23 BNB/ETH); the other three are mixed book+dip with no leg above 50%, and the 20 worst rungs are all full-size (n=0) single-coin — mostly XRP — stop-outs.
