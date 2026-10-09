# oc_spotlongs2 REPORT: spot-routed book longs with HONEST spot fees

Idea: oc_spotlongs V1 routed every book long to spot-margin at PERP fees
(maker 0.0002) and measured +0.230 pp/mo dev4 of funding save (5y +0.228).
Bybit spot VIP0 charges 0.1% maker AND taker, so the saving may disappear.
This study reprices the spot legs at honest fees and re-scores: REF (G2),
SPOT_F10 (V1 routing, spot 0.001/0.001, borrow APR 10%), SPOT_F06
(sensitivity 0.0006/0.0006, labelled). Mechanism = oc_spotlongs base pipe
(v321, corr-aware 1/(1+n)*1.7, bear books, budget 0.26*1*1.7, G=2.0,
win_start=5, gate costs) through the spot-fee-patched simulate
(spot_patch2.py: verbatim engine_user + SPOT-FEE PATCH P0-P5, asserted; REF
defaults reproduce the audited engine bit-exact). THE ONE change vs V1 is P5:
long-side book legs (entry of ps>0, TP/SL/partial/scale of cur_q>0) while
spot-routed pay the spot rate (limits -> spot_maker, market SL -> spot_taker);
short legs stay perp; dip sleeve untouched. Routing is unconditional V1 (all
book longs spot), so nothing is fit. All engine work via heavy_slot, one job
at a time, heartbeat 600 s, logs under tmp/.

## Reproduction gate: PASS

REF dev years 0..3 == v421 R2B1D17BFG2 to the digit
([2.588/10.86, 3.282/16.91, 6.045/15.81, 10.677/8.27]).

## Per-year %/mo (geometric, reset metric) / DD — dev 2021-2024

| row | 21-22 | 22-23 | 23-24 | 24-25 | dev4 mean / WORST | dev DDmax |
|---|---|---|---|---|---|---|
| REF (gate) | 2.588 / 10.86 | 3.282 / 16.91 | 6.045 / 15.81 | 10.677 / 8.27 | 5.601 / 2.588 | 16.91 |
| SPOT_F10 (spot 0.001) | 2.560 / 10.77 | 3.329 / 16.94 | 6.267 / 15.83 | 10.738 / 8.27 | 5.675 / 2.560 | 16.94 |
| SPOT_F06 (spot 0.0006) | 2.613 / 10.67 | 3.349 / 17.03 | 6.271 / 15.81 | 10.884 / 8.27 | 5.730 / 2.613 | 17.03 |

Dev4 robust pick (frozen rule, REF vs SPOT_F10 only; SPOT_F06 never picked):
both eligible (DD<=20, no losing year), both mean>=5 -> highest WORST ->
**REF** (2.588 > 2.560). The V1 edge of +0.258 (5.859 vs 5.601 at perp fees)
shrinks to **+0.074** at honest 0.001 fees, with a worse worst year.

## Book turnover + fee/funding split (mean across 4 shifts, fraction of equity/yr)

| row | year | turnover (x) | spot fees | perp fees | funding saved | funding paid | borrow |
|---|---|---|---|---|---|---|---|
| REF | 21-22 | 33.64 | 0.000000 | 0.007065 | 0.000000 | 0.009202 | 0.000000 |
| REF | 22-23 | 54.52 | 0.000000 | 0.012931 | 0.000000 | 0.026455 | 0.000000 |
| REF | 23-24 | 60.82 | 0.000000 | 0.014597 | 0.000000 | 0.024153 | 0.000000 |
| REF | 24-25 | 76.77 | 0.000000 | 0.017169 | 0.000000 | 0.043037 | 0.000000 |
| SPOT_F10 | 21-22 | 33.65 | 0.015551 | 0.003771 | 0.009206 | 0.000000 | 0.000002 |
| SPOT_F10 | 22-23 | 54.59 | 0.032903 | 0.004884 | 0.026434 | 0.000000 | 0.000164 |
| SPOT_F10 | 23-24 | 60.91 | 0.036318 | 0.005865 | 0.024288 | 0.000000 | 0.000202 |
| SPOT_F10 | 24-25 | 76.82 | 0.048283 | 0.006357 | 0.043053 | 0.000000 | 0.001040 |

Yearly dev4 means: funding saved 0.0257/yr (~0.21 %/mo, matches V1's 0.4118/16
exactly); extra book fees vs REF 0.0255/yr (~0.21 %/mo); borrow 0.0004/yr
(immaterial, book leverage ~never binds). **Direct arithmetic nets to ~zero**
(saved - extra - borrow = -0.0001/yr): honest fees eat the whole funding save.
The measured +0.074 pp/mo residual is exposure second order (fills differ by a
handful per ~1000 book trades via governor/min-notional feedback: book fills
926/858/999/1159 vs REF 926/855/994/1159), not a real edge. The book churns
~56x equity/yr, so every 1 bp of fee rate costs ~0.047 %/mo — fee honesty
dominates this direction. Dip-sleeve fees stay implicit in rung returns
(engine convention, labelled).

## Frozen pick REF: post-release year + 5y + full-path DD (STORED rows, labelled)

Pick is REF, so no new Y4 is scored (SPOT_F10/SPOT_F06 stay dev-only, never
re-scored — the discipline holds). REF stored: Y4 25-26 = 4.648 / 12.90
(post-release diagnostic: oc_spotlongs already scored this year once for V1);
5y mean / WORST = 5.410 / 2.588, no losing year, full-path DD 16.82
(DDmax 16.91). Gate read-out for REF: (a) 5y 5.410 >= 5 PASS; (b) Y4
4.648 >= 5 FAIL; (c) no losing year PASS; DD 16.82 <= 20 PASS.

## Bybit-price row S5 for the pick (REF_S5 side row, read-only, 2021 short window)

| row | 21-22* | 22-23 | 23-24 | 24-25 | dev4 mean / WORST | DDmax |
|---|---|---|---|---|---|---|
| REF_S5 (oc_c2bybit, read-only) | 2.129 | 2.735 | 4.932 | 10.377 | 4.994 / 2.129 | 18.11 |

No in-engine S5 rerun was needed (pick = REF; side row exists and is never
recomputed). SPOT rows have no S5 (not picked, correctly unscored).

## Win rates (pooled 4 shifts, dev years)

REF book/rung/all: 21-22 0.503/0.638/0.613 (926/4077), 22-23 0.516/0.689/0.658
(855/3940), 23-24 0.519/0.732/0.697 (994/4979), 24-25 0.508/0.720/0.671
(1159/3857). SPOT_F10: 0.503/0.638/0.613, 0.514/0.689/0.658, 0.523/0.732/0.697,
0.507/0.720/0.671 — fills differ from REF by ~5/1000 (second order only).

## Feasibility: Bybit spot TP/SL order types (public docs only, no keys/calls)

- Spot limit orders accept attached TP/SL at creation: `takeProfit` /
  `stopLoss` with `tpOrderType` / `slOrderType` = Market or Limit
  (+ `tpLimitPrice` / `slLimitPrice` for Limit). Docs example "Spot Limit
  order with limit tp sl" is exactly our structure (limit entry + limit TP +
  limit SL), and `slOrderType` = Market covers our market-SL variant.
  Source: Bybit V5 `POST /v5/order/create`
  (https://bybit-exchange.github.io/docs/v5/order/create-order),
  `orderFilter` = `tpslOrder` ("Spot TP/SL order, the assets are occupied even
  before the order is triggered") vs `StopOrder` (conditional, assets free
  until triggered).
- Fees confirm the repricing: Bybit VIP0/Non-VIP spot = 0.1% maker AND taker
  (= 0.001, our SPOT_F10), perp = 0.055% taker / 0.02% maker (= gate costs).
  Source: Bybit fee structure
  (https://www.bybit.com/en/help-center/article/Trading-Fee-Structure) and
  spot-fees explainer
  (https://www.bybit.com/en/help-center/article/Bybit-Spot-Fees-Explained).
- Caveats for the simulation: (1) `POST /v5/position/set-trading-stop` is
  valid for linear/inverse/option ONLY — spot has no position-level
  trading-stop; attachment happens at order creation (or via `tpslOrder` /
  `StopOrder` conditionals / OCO). Moving SL/TP mid-trade means amending or
  replacing conditional orders, not a native position stop. (2) Stop-first
  when SL and TP trigger in the same minute is NOT documented exchange
  behaviour; our stop-first rule stays a conservative assumption (labels the
  worse fill). (3) Leveraged spot longs need margin (`isLeverage=1`, borrow);
  our APR-10% borrow haircut stands in for margin interest and is immaterial
  here. Net: the simulated structure (limit entry + market SL + limit TP) is
  executable on Bybit spot, with SL/TP management friction the simulation does
  not price.

## Leakage checklist (how each was checked)

- Feature timing: books known at close of T, held [T,T+1); routing is
  unconditional (no funding signal, nothing fit); borrow uses only this bar's
  end quantities and bar-start equity. Truncation test in pytest recomputes
  F7/med from a truncated panel — identical on the kept prefix (inherited).
- Label windows: no label fit anywhere; the engine consumes the realised 1m
  path only.
- Fit windows: NOTHING is fit (no medians/thresholds; spot fees 0.001/0.0006
  and borrow APR 10% fixed ex-ante). No test-year statistic feeds any choice.
- Fill timing: win_start=5 asserted (no fill minutes 0-4); limits fill only on
  1m trade-through strictly through the price; stop-first inherited from the
  audited engine (fee sites only change the RATE, never the fill logic);
  spot-perp fill basis 0 is a labelled assumption (same 1m cube); SL market
  taker / TP limit maker attached as now (now at honest spot rates).
- Contamination: dev years were available when IDEAS10/oc_spotlongs were
  written (post-hoc direction); Y4 was scored once for V1 in oc_spotlongs and
  is NOT re-scored for any spot row here (pick = REF stored row); S5 side row
  is read-only.

## Post-hoc log

- 2026-10-08, before outcomes: PLAN frozen (REF/SPOT_F10/SPOT_F06 + S5 +
  turnover/fee-split records + feasibility; no overlays, no refit).
- 2026-10-08, after dev outcomes: NO plan change. Pick = REF per the frozen
  rule, so the pre-registered last-stage and S5 engine runs were correctly
  SKIPPED (nothing to score: REF rows are stored, SPOT rows dev-only).

## Verdict

NOT ADOPTED: at honest Bybit spot fees (0.001 both sides) the V1 funding edge
collapses from +0.258 to +0.074 pp/mo dev4 with a worse worst year (2.560 vs
2.588), and the per-leg accounting shows why — saved funding 0.0257/yr vs
extra fees 0.0255/yr net to zero on a book that churns ~56x/yr. The robust
dev4 rule picks REF. Even the 0.0006 sensitivity keeps only half the edge
(+0.129) with DD 17.03. Close this direction; do not route book longs to spot
for funding reasons.

## Vietnamese verdict (3 lines)

- KHÔNG deploy: SPOT_F10 chỉ còn +0.074%/tháng so với REF (từng +0.258 ở phí
  perp), worst-year 2.560 < 2.588 nên rule robust chọn REF — phí thật 0.0255/năm
  ăn trọn khoản funding tiết kiệm 0.0257/năm vì book churn ~56x vốn/năm.
- Kế toán từng leg khớp từng chữ số (saved ≈ REF paid trong 2e-4, borrow ~0);
  phần dư +0.074 chỉ là hiệu ứng đường đi (fills lệch ~5/1000), không phải edge.
- Feasibility Bybit spot OK (limit entry + TP limit + SL market qua tpslOrder,
  phí VIP0 đúng 0.1%/0.1%), nhưng không cứu được bài toán — đóng hướng này.
