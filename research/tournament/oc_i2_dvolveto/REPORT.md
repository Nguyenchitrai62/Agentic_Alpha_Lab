# oc_i2_dvolveto REPORT — DVOL-spike dip veto (IDEAS2 §1)

## 0. PRE-REGISTRATION (written BEFORE any run; no other variants)

Idea: IDEAS2_20261007 §1 "DVOL-spike dip veto (change, not level)".
Why new: nearest closed are oc_dvol (LEVEL context), oc_dvolshort (LEVEL
short-gate screen), oc_idea7 VRP budget dial (CLOSED), oc_optctx (CLOSED).
This is a 1d DVOL CHANGE spike veto, not a level filter.
Data (local only, no download): data/raw/deribit_dvol_20261005 (BTC+ETH
hourly DVOL, 2021-04-01..2026-09-23) + data/raw/dvol_20260924 (BTC, from
2021-03-24; used only as a cross-check, primary = 20261005 BTC series).
Rule: skip NEW dip bids when Deribit BTC DVOL rose > p95 of its trailing
90d change distribution (spike days). Holds/exits of already-open rungs
unchanged; stops/TP/timeout identical.
Leak discipline: DVOL change at decision bar T uses only hourly closes with
bar END <= T (as-of = last hourly END <= T minus the END 24h earlier; never
the spike-day close itself beyond what is closed at T); the p95 threshold
for anchor year k is fit on spike history in [2021-06-30, A_k - 10d) only
(pre-anchor + 10d embargo >= the ~4h dip horizon); no statistic from any
test year feeds any choice.
Costs (gate): maker 0.0002 (entries/TP), taker 0.00055 (stops/timeouts),
longs pay 0.0001/8h on settling timeouts (dip replica = oc_dipexit D0
exact + B1 sizes w = 1/(1+n)).
Pre-registered variants (2, no others):
- V1: veto NEW dip bids on spike-flagged signal bars (holds/exits
  unchanged). Judged on the 4-phase dip replica screen + placebo gate.
- V2: V1 dip veto + on spike-flagged bars halve BOOK longs (w>0 -> 0.5w;
  diagnostic vectorised open-to-open screen only; any book claim needs the
  4-phase engine, never this screen).
Selection (AGENTS.md): compare/choose V1 vs V2 ONLY on dev years 2021-2024
(anchors 2021-2024); robust criterion (DD <= 20, no losing dev year; prefer
dev4 mean >= 5 then highest dev4 WORST year — applied in dip-screen units
as: sum leg + DD leg + magnitude). Score 2025-09-24..2026-09-23 ONCE, for
the chosen variant only; label it POST-HOC (all five years are research
data now; clean proof is prospective paper only).
Gate to 4-phase engine: full PROMISING legs (sum>=base 4/5 AND
DD<=base+0.01 4/5) PLUS dSum5y >= +0.273 (oc_placebo_dip pooled p95).
Engine runs ONLY if the screen passes; otherwise close with no engine run.
Baseline to reproduce first: oc_carrycompound G2+carry f=0.25
(5.634 / DD 16.75 / full 16.66) with f=0 == v421 G2 (5.41 / 2.588 /
16.91 / full 16.82) to the digit; else STOP and report.
Reset metric: research/diagnostics/r2_decompose5/reset_metric.py year_reset
(per-anchor reset to 1.0) + v421 continuous full-path DD.

## 1. Baseline reproduction (read-only, no engine rerun)

f=0 reproduces v421 G2 (R2B1D17BFG2) TO THE DIGIT, asserted in-script:
per-year R 2.588/3.282/6.045/10.677/4.648, 5y R 5.41, W 2.588, DD 16.91,
full-path DD (marked/close/full) 16.82/16.05/16.82. G2+carry f=0.25:
per-year R 2.778/3.353/6.590/10.956/4.698, 5y R 5.634, W 2.778,
DD 16.75, full 16.66/15.90/16.66, carry add +0.224 pp/mo. PASS — screen
work proceeds. (Sources: v421_result.json, oc_carrycompound results.json.)

## 2. Spike-flag definition + event rates (leak-free)

D(d) = BTC DVOL hourly close of the bar END == (d+1) 00:00 UTC; chg(d) =
D(d)-D(d-1) finalised at the start of d+1; q95_k = p95 of chg over
FIT_k = [A_k-100d, A_k-10d) (90d trailing, pre-anchor + 10d embargo);
veto(x) = chg(x-1) > q95_k (yesterday's FINALISED change; never the
spike-day close itself). Hourly grid gap-free (max step 1h, 2021-04-01..
2026-09-23). Cross-check vs data/raw/dvol_20260924: max abs diff 0.0
over 2002 matched midnights (identical series).

| year | q95 (DVOL pts) | n_fit | veto-days |
|---|---|---|---|
| 2021-09-24 | 4.2425 | 90 | 21 |
| 2022-09-24 | 4.6240 | 90 | 17 |
| 2023-09-24 | 3.6975 | 90 | 22 |
| 2024-09-24 | 3.5425 | 90 | 7 |
| 2025-09-24 (POST-HOC) | 1.7945 | 90 | 42 |
| total | — | — | 109 |

Caveats: relative-change veto is regime-sensitive — the quiet 2025
fit window gives q95 = 1.79 (vs ~3.5-4.6) so noise trips 42 veto-days;
2024 has only 7. Vetoed fills (15.9% of the ledger) exceed the ~5%
veto-day share because spike days cluster in high-flush regimes when
many rungs print.

## 3. Dip-replica screen (4-phase D0+B1, gate costs)

Exact oc_dipexit D0 (TP 1sg, close5 stop 4sg, 8sg backstop, timeout at
next-bar open; maker 0.0002/taker 0.00055; settle funding) + B1 sizes
w=1/(1+n), majors x R2 2.5..5.0, live 16..238, 4 clock phases, bars open
[2021-09-24, 2026-09-24). Fidelity: phase-0 fills/coin
1067/1126/952/1179/1174 and base 4-phase-mean sums
0.911/0.833/2.100/3.197/0.677 (sum5y 7.718) = placebo base exactly
(phase-0 max abs diff 0.0005 <= 1e-3). Ledger n = 22312; V1 skips 3540
fills (15.9%). Year = signal-bar-open anchor year; daily sums by exit
date; 4-phase means.

| year | S_base -> S_V1 | DD_base -> DD_V1 | n_base -> n_V1 |
|---|---|---|---|
| 2021 (dev) | 0.9113 -> 0.5889 | 0.8560 -> 0.8329 | 1042.75 -> 833.75 |
| 2022 (dev) | 0.8326 -> 0.6890 | 0.9506 -> 0.9554 | 1014.75 -> 889.00 |
| 2023 (dev) | 2.0998 -> 1.7656 | 0.8000 -> 0.7841 | 1338.00 -> 1160.75 |
| 2024 (dev) | 3.1974 -> 3.0515 | 0.3545 -> 0.3439 | 989.50 -> 915.25 |
| 2025 (POST-HOC, chosen-variant display) | 0.6772 -> 0.1149 | 0.6073 -> 0.7422 | 1193.00 -> 894.25 |
| 5y sum | 7.7183 -> 6.2101 | mean 0.7136 -> 0.7317 | — |
| full pooled (4x mean sums) | 30.8732 -> 24.8403 | dDDfull +0.0203 (worse) | 22312 -> 18772 |

Decision on DEV years 2021-2024 only: S_V1 >= S_base in 0/4; DD_V1 <=
DD_base+0.01 in 4/4; dSum5y = -1.508 (gate needs >= +0.273).
NOT PROMISING — the veto deletes winners in every year (consistent with
oc_dvol: high DVOL LEVEL predicts BETTER y1.0; CHANGE spikes mark the
flushes that pay). 2025 shown once, POST-HOC: also loses
(0.677 -> 0.115, DD worse). No 4-phase engine run (gate failed).

## 4. V2 book-leg diagnostic (vectorised, NOT an engine claim)

Open-to-open 4h screen (oc_dvolshort-exact books/opens grid, maker
0.0002/unit turnover): halve longs (w>0 -> 0.5w) on flagged bars.

| year | total P&L ungated / gated | maxDD ungated / gated | flagged bars |
|---|---|---|---|
| 2021 (dev) | 0.309477 / 0.329057 | 0.131523 / 0.123885 | 5.75% |
| 2022 (dev) | 0.306504 / 0.278818 | 0.069606 / 0.067100 | 4.66% |
| 2023 (dev) | 0.563893 / 0.540575 | 0.086094 / 0.085474 | 6.01% |
| 2024 (dev) | 0.557065 / 0.557471 | 0.062817 / 0.066051 | 1.92% |
| 2025 (POST-HOC) | 0.475135 / 0.434226 | 0.078414 / 0.090970 | 11.51% |

Dev4: P&L not lower 2/4, DD improves 3/4 — fails the joint reading, and a
vectorised screen can never pass a book idea (rules). V2's dip leg IS V1
(closed above). No engine run for V2 either.

## 5. Decision + leak audit + verdict

Selection used ONLY dev 2021-2024: V1 sum leg 0/4 (dSum5y -1.508 <<
+0.273); V2 book leg 2/4 P&L with no engine standing. Neither variant
qualifies; nothing goes to the 4-phase engine; direction CLOSED.
Leak audit: (a) feature timing — chg uses hourly closes with END <= T
only (asof searchsorted side='left' on T-1ns; veto(x) uses chg(x-1)
finalised before day x); (b) label windows — dip y1.0 exits race
identically to D0 with the minute-5+ trade-through convention untouched;
(c) fit windows — q95_k from [A_k-100d, A_k-10d), no test-year statistic
feeds any threshold; (d) fill timing — skipped fills claim no fill, kept
fills keep exact D0 exits. All five years are research data; clean proof
would need prospective paper (not proposed — the screen signs negative).
Repro: research/tournament/oc_i2_dvolveto/compute_dvolveto.py (spike-only
is light; full run via scripts/heavy_slot.py) + results.json +
tests/test_oc_i2_dvolveto.py. No commits. GIT untouched.

## Vietnamese verdict (3 lines)

Dòng 1: REJECT — veto spike DVOL-change loại đúng lệnh thắng cả 5 năm (dev4 0/4, dSum5y -1.508 so với gate +0.273), V2 cũng fail nên không chạy engine 4-phase.
Dòng 2: Bằng chứng leak-free (flag chỉ dùng close đã đóng, ngưỡng fit pre-anchor + embargo 10d, baseline khớp tới digit, fidelity replica 0.0005).
Dòng 3: Đóng direction, không cần prospective paper vì screen âm rõ ràng.
