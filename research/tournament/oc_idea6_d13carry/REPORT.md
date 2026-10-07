# oc_idea6_d13carry REPORT — DD<15 stretch: D13BF + concentrated (max-coin) carry f=0.50, split capital

PRE-REGISTRATION (frozen BEFORE any run; no other variants will be added):

- S1: D13BF (v424 R2B1D13BF, frozen 4-phase base) + idea-#4 max-coin carry
  (per delivery, when both BTC and ETH pass the frozen 4% ann-basis filter,
  enter ONLY the higher-basis coin; single-coin deliveries unchanged),
  f=0.50, split-capital deployment per oc_utamargin (f=0.50 NOT cleared
  additive on one UTA; separate capital / borrow accepted).
- S2: S1 with idea-#1 K1 dip sizing (budget-normalised 1/(1+n)-prior x
  Kelly-fraction 0.25) on the BOT leg. S2 needs a full 4-phase engine rerun
  with 1m data; book legs are judged ONLY in the 4-phase engine, never a
  vectorised screen — so S2 is pre-registered but NOT scored by any proxy
  here (status ENGINE-REQUIRED, see §S2). No further variants.

Selection protocol (AGENTS.md): compare and choose ONLY on the four dev
years 2021-2024 (anchors 2021-09-24..2024-09-24). Robust criterion: among
variants with dev max-DD <= 20 and no losing dev year, prefer dev4 mean
>= 5 %/mo (if any), then the highest dev4 WORST year; ties -> higher mean.
The most recent year 2025-09-24..2026-09-23 is scored ONCE, for the chosen
variant only. Everything below that re-uses already-scored years is
labelled POST-HOC (these rows were already seen; folds must transfer or
the stretch direction closes).

Gate costs: maker 0.02 %, taker 0.055 % (Bybit VIP0); longs pay 0.01 %/8h,
shorts zero. Carry delivery futures pay NO funding (oc_cashcarry).

Baseline gate (assignment): reproduce G2 + carry compounding baseline
(5.634 / DD 16.75 / full 16.66, oc_carrycompound) or G2 (5.41) exactly
first, else STOP and report. Reset metric:
research/diagnostics/r2_decompose5/reset_metric.py year_reset; full-path DD
v421/v422 convention + chained-reset convention (both labelled).

STATUS: PRE-REGISTERED — results follow after the run (pre-reg lines above
unchanged).

## Method (audited blocks reused, nothing refit)

Base = v424 R2B1D13BF stored 4-phase runs via reset_metric.year_reset
exactly. Carry = frozen oc_cashcarry rule (33 trades reused verbatim).
Max-coin M1: per delivery keep the higher ann-basis coin (entry-bar-known
only — causal); 18 kept / 15 excluded over 18 deliveries. Combination =
oc_carryd13 equity-level convention (f=0.50 of year-start equity, hourly
causal marks, chained-reset full-path DD, labelled); NOT the
oc_carrycompound live-A compounding convention. POST-HOC throughout.

## Baseline gate: reproduced exactly (else would have stopped)

G2 official 5.41 / W 2.588 / DD 16.91 / full 16.82; D13BF 4.971 / 2.485 /
14.98 / full 14.86 (both recomputed to the digit via year_reset); G2 +
carry compounding f=0.25: 5.634 / 2.778 / 16.75 / full 16.66 (+0.224pp);
both-coin D13 maps f=0.25 5.104/14.85, f=0.50 5.234/14.71.

## S1 dev years 2021-2024 ONLY (selection basis; R %/mo / DD %)

| year | S1 max-coin f0.50 | D13BF base | carry lift |
|---|---|---|---|
| 2021-09-24 | 2.632 / 10.05 | 2.485 / 10.21 | +0.147 |
| 2022-09-24 | 3.358 / 14.71 | 3.286 / 14.98 | +0.072 |
| 2023-09-24 | 5.320 / 14.64 | 4.975 / 14.76 | +0.345 |
| 2024-09-24 | 9.642 / 7.30 | 9.526 / 7.33 | +0.116 |
| dev4 | 5.203 / W 2.632 / DD 14.71 / losing 0 | dev4 5.033 | +0.170 |

Robust criterion: S1 is the sole scored variant, DD 14.71 <= 20, no losing
dev year, dev4 5.203 >= 5 → winner = S1. S2 ENGINE-REQUIRED (see §S2).

## Winner scored once on the most recent year (POST-HOC)

S1 2025-09-24: 4.764 / 10.84 (base 4.723/10.97, lift +0.041 — filter idled,
1 of 6 opportunities passed). 5y POST-HOC: 5.115 / W 2.632 / DD 14.71 /
losing 0. Reset metric per-year above; full-path DD chained-reset 14.71
(dev 14.71, full 14.71; D13BF official continuous-mix full 14.86 vs chained
14.98 — convention gap, not a finding). Both-coin f0.50 refs: 5.234/14.71;
max-coin gives up -0.119pp (18 vs 33 pairs) at equal DD.

## UTA margin (split capital per oc_utamargin/2)

Max-coin peak overlap 2 pairs, peak indexed spot cost 1.0 of year-start Eq
(both-coin ref 3 pairs / 1.799). oc_utamargin: f=0.50 additive = 1 blocked
hour + borrow; oc_utamargin2: f=0.50 blocked under haircut stress at EVERY
leverage. Verdict: SPLIT CAPITAL ONLY (separate USDT wallet, borrow
accepted); NOT cleared additive on one UTA.

## Frictions (bound, no new run)

Stored S1-S5 runs (oc_d13robust/v421_audit) are absent in this tree.
Published oc_carryfric bound: both-coin D13BF+carry f0.50 keeps stretch
only at base (5.234/14.71) and S2-f0.50 (5.062/14.80); fails S1/S3/S4/S5.
Max-coin lift is SMALLER, so it cannot pass where both-coin fails.

## §S2 status

ENGINE-REQUIRED: K1 dip sizing needs a full 4-phase engine rerun with 1m
data; book legs are judged ONLY there, never a vectorised proxy — S2 not
scored, no proxy used for selection.

Win rate: BOT all-trade win UNCHANGED (equity overlay, zero new trades);
kept carry pairs 18/18 net positive on allocated capital, reported
separately. Leak audit: marks use last CLOSED hourly bar strictly before t;
max-coin pick uses entry-bar basis only; sizes/thresholds frozen
pre-anchor; no test-year stat feeds any choice; BOT fills from the frozen
engine (t+1/minute-5 rules already inside, not re-judged).

## Verdict

Base-case stretch passes thinly (5.115/14.71 POST-HOC) but concedes -0.12pp
vs both-coin, fails frictions by bound, needs split capital with borrow,
and at ~5.1 is ~2.9pp short of the BOT 8 %/mo goal. Direction closes to
new variants; only prospective paper could qualify the stretch leg.
TỪ CHỐI cho mục tiêu BOT 8%/tháng: S1 chỉ ~5,1%/tháng (dev4 5,203), thiếu ~2,9 điểm phần trăm.
CẦN bằng chứng prospective cho chân stretch DD<15: base đạt mỏng (5,115/14,71 POST-HOC) nhưng trượt ma sát và đòi tách vốn.
Đóng hướng stretch với biến thể mới: giữ paper, không mở thêm S nào khác.
