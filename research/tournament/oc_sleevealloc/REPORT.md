# oc_sleevealloc REPORT — cross-sleeve drawdown-budget allocator (2026-10-08)

PLAN.md was written BEFORE any outcome; one code-bug fix after a crashed run
is logged in the post-hoc section (definitions unchanged). Heavy dip-only
engine via `heavy_slot` (51 s); overlay CPU-only (~44k hourly rows, 4h+1h only).

## 0. Reproduction gates (PASS, to the digit — else STOP)

- REF (G2 `R2B1D17BFG2`) == `v421_result.json`: years
  (2.588/10.86), (3.282/16.91), (6.045/15.81), (10.677/8.27), (4.648/12.90),
  5y 5.410, full-path DD 16.82. Asserted in-script.
- REF_CARRY one-account f=0.25 == `oc_carrycompound` `G2_f0.25` years
  (2.778/10.86), (3.353/16.75), (6.590/15.69), (10.956/8.20), (4.698/12.66)
  to the digit (validates frozen carry-mtm reuse: 33 trades, same fees).

## 1. Sleeve standalone equities (capital-split legs, all NET — no cost smuggling)

| year | G2-book-only (engine, sleeve OFF) | G2-dip-only (engine, books x0) | carry-unit (f=1.0/pair, frozen mtm) |
|---|---|---|---|
| 2021-09-24 | 0.585 / 9.76 (reset_metric; hourly-mean 0.585/9.76) | 0.762 / 12.35 (reset_metric; hourly-mean 0.762/12.35) | 0.735 / 17.74 |
| 2022-09-24 | 1.992 / 10.59 (hourly-mean 2.001/10.57) | 0.436 / 13.48 (hourly-mean 0.447/13.30) | 0.270 / 1.34 |
| 2023-09-24 | 2.818 / 14.60 (hourly-mean 2.837/14.61) | 1.227 / 10.68 (hourly-mean 1.442/10.67) | 1.770 / 4.10 |
| 2024-09-24 | 3.854 / 9.42 (hourly-mean 3.905/9.38) | 2.763 / 5.69 (hourly-mean 2.680/5.81) | 0.859 / 4.33 |
| 2025-09-24 | 3.438 / 10.24 (hourly-mean 3.472/10.24) | 0.390 / 10.16 (hourly-mean 0.478/9.68) | 0.133 / 2.07 |

R = %/mo geometric, DD % (reset_metric per-phase rebase is authoritative for the
engine legs; hourly-mean-of-4 rebase is the allocator's internal series — gaps
<= 0.22pp disclosed, same ordering). Book/dip legs are engine-NET (gate fees,
adverse long funding, limit trade-through from minute 5, SL market taker +
TP limit maker, stop-first inherited from the frozen runners). Carry is NET of
spot 0.001/side + fut 0.00055/0.0002 delivery drag, hold-to-delivery (a hedged
pair, so no SL/TP — disclosed difference from perp legs). Carry-unit peak
concurrent pairs = 4 (daily sample); at w_c = 0.5 that is ~2.0x total-account
notional — NEEDS BORROW (same flag as oc_carrymore); cap 0.5 never bound
(max fitted w_c = 0.4665 in 2025 V1).

## 2. Dev4 (anchors 2021..2024 — SELECTION SET; yearly weights frozen pre-anchor)

Yearly weights (book/dip/carry), trailing min(1460d, avail) ending anchor-7d,
<180d avail -> equal (2021 only):

| year | V1 (1/maxDD) | V2 (1/vol) |
|---|---|---|
| 2021 | 0.333/0.333/0.333 (fallback) | 0.333/0.333/0.333 (fallback) |
| 2022 | 0.427/0.338/0.235 | 0.438/0.454/0.108 |
| 2023 | 0.391/0.348/0.261 | 0.376/0.462/0.163 |
| 2024 | 0.349/0.372/0.279 | 0.348/0.452/0.200 |

Per-year R/DD of the capital-split account (exposure always 1.0, rebalanced yearly):

| year | REF (G2 total) | V1 | V2 | CTRL-EQ (1/3 fixed) |
|---|---|---|---|---|
| 2021 | 2.588 / 10.86 | 0.671 / 5.55 | 0.694 / 5.92 | 0.694 / 5.92 |
| 2022 | 3.282 / 16.91 | 1.160 / 6.36 | 1.142 / 6.96 | 1.096 / 6.29 |
| 2023 | 6.045 / 15.81 | 2.110 / 7.09 | 2.042 / 7.79 | 2.022 / 6.18 |
| 2024 | 10.677 / 8.27 | 2.621 / 3.92 | 2.803 / 3.83 | 2.421 / 3.77 |
| dev4 mean/W/maxDD/losing | 5.601 / 2.588 / 16.91 / 0 | 1.639 / 0.671 / 7.09 / 0 | 1.667 / 0.694 / 7.79 / 0 | 1.555 / 0.694 / 6.29 / 0 |
| full-path DD | 16.82 | 7.54 | 8.50 | 6.51 |

Robust pick on dev4 ONLY: V1 and V2 both satisfy DD<=20 with no losing year,
neither reaches mean>=5, W ties at 0.671 vs 0.694 -> highest WORST then mean
=> **V2** (W 0.694, mean 1.667 vs V1 1.639; CTRL-EQ 1.555 not selectable).
Dynamic-vs-static gap is +0.11pp (V2-EQ) — noise against a -3.9pp shortfall
vs G2 dev4 (1.667 vs 5.601).

## 3. Post-release year Y4 2025-09-24..2026-09-23 (scored ONCE for pick + REF, labelled)

| row | R / DD |
|---|---|
| V2 (dev4 pick, weights 0.267/0.396/0.337 frozen pre-anchor) | 1.274 / 4.89 |
| REF (G2 total) | 4.648 / 12.90 |
| REF_CARRY f=0.25 (one-account ref) | 4.698 / 12.66 |
| CTRL-EQ | 1.487 / 4.82 |

Five-year path (reported, never selected): V2 1.588 / W 0.694 / maxDD 7.79 /
full 8.50, losing 0; CTRL-EQ 1.541 / 0.694 / 6.29 / 6.51; REF 5.410 / 2.588 /
16.91 / 16.82; REF_CARRY 5.634 / 2.778 / 16.75 / 16.66.

## 4. Bybit-price row S5-approx for the dev4 pick (diagnostic, labelled)

BOT leg = Bybit G2 total (`runs_S5.pkl` REF hourly; 2021 SHORT window from
2021-11-15); carry leg = same hourly marks (venue-independent); pick yearly
w_carry frozen (no refit); book/dip split NOT re-estimated on Bybit (stated
limit — full sleeve-split S5 would need 8 extra Bybit phase sims):

| year | REF_S5 (this grid; oc_c2bybit REF_S5 dev4 4.994/2.129/18.11) | V2 S5-approx |
|---|---|---|
| 2021 (SHORT) | 2.129 / 12.36 | 1.687 / 8.92 |
| 2022 | 2.779 / 18.09 | 2.539 / 16.77 |
| 2023 | 5.657 / 16.09 | 5.123 / 14.23 |
| 2024 | 10.135 / 9.94 | 8.858 / 8.68 |

V2 trails REF on Bybit in ALL four dev years (same sign as Binance) — the
failure is venue-consistent, not a Binance artefact.

## 5. Why it fails (the load-bearing mechanism)

Standalone sleeves earn far less than the joint engine: dev4 means are
book-only ~2.3, dip-only ~1.3, carry-unit ~0.9 (sparse: 3-14 trades/yr) vs
G2-total 5.6. The joint engine's return lives in the INTERACTION the splitter
throws away — shared compounding inside each phase sub-account, the governor
scaling book+dip together, and dip TPs firing inside book-held trends. A
capital-splitter that re-divides the same risk into three standalone pots pays
full exposure for a third of the synergy in each pot: DD halves (7-8 vs 16.9)
but return quarters (1.6 vs 5.6). Risk-parity then loads the thinnest sleeve
(the 2025 carry weight 0.34-0.47 buys the 0.133 %/mo sleeve). This is the same
lesson as the CLOSED rows, now across sleeves: oc_corrbudget/oc_idiocap (within-
sleeve rescaling = exposure dial, no edge), oc_governor (loosening = risk dial),
oc_phaserebal (rebalancing the SAME compounding path lowers return). The one
untested dial was allocation — tested now: it is also a risk dial, and an
expensive one.

## 6. Leakage / causality checks (how verified)

- Feature timing: engine legs inherit causal fills (limit trade-through, nothing
  minutes 0-4, stop-first); allocator weights for year y use sleeve data ending
  y-anchor minus 7d ONLY (`test_weights_use_preanchor_only`: recompute from a
  truncated table — identical on the kept prefix).
- Label windows: no labels fit here; carry trades frozen with t_exit < anchor-7d
  inherited from oc_cashcarry/oc_carrycompound.
- Fit windows: trailing min(1460d, avail) ending anchor-7d; year y uses anchor-y
  weights only, never later; S5 reuses frozen Binance weights (no Bybit refit).
- Fill timing: no fills in the overlay (return algebra on settled equity + causal
  carry marks); `tests/test_oc_sleevealloc.py` 6/6 pass (causality/truncation +
  hand-checked synthetic cap + weight math).
- Gate costs: book/dip engine legs carry gate costs (maker 0.0002/taker 0.00055,
  longs 0.0001/8h, shorts 0); carry carries entry/delivery fees; NOTHING is
  double-counted or smuggled (per-sleeve table above is the receipt).
- `tests/test_oc_sleevealloc.py` run with `.venv/Scripts/python.exe -m pytest -q`.

## 7. Post-hoc log

- 2026-10-08, before any result was written: fixed a double-/100 in `metric_dd`
  (`dd_of` already returns a fraction; the extra /100 pinned every sleeve at the
  0.5% floor so V1 printed equal weights). The first run crashed (KeyError on a
  dict-indexed gate row) before writing `results.json`; no selection had been
  made. Definitions, variants, windows and rules are unchanged from PLAN.md.

## Vietnamese verdict (3 lines)

- Cả V1 (dev4 1,64%/tháng) lẫn V2 (1,67%/tháng, pick) đều thua xa G2 (5,60% dev4; 5,41% 5 năm) dù DD thấp hơn nhiều (7-8 so với 16,9): chia vốn ra ba sleeve độc lập vứt bỏ phần lợi nhuận nằm ở tương tác trong engine (gộp lãi chung, governor, TP trong trend), còn control tĩnh CTRL-EQ (1,56%) gần như tương đương nên dynamic không có edge.
- Năm sạch chấm MỘT lần cũng thua xa (V2 1,27% so với G2 4,65%), và hàng Bybit S5-approx thua REF cả 4 năm dev — thất bại nhất quán giữa hai venue, không phải artefact giá Binance; carry weight cap 0,5 không bao giờ chạm (max 0,47).
- Kết luận: REJECT hướng này (kết quả âm nhưng hợp lệ), đóng direction theo IDEAS10 (đúng prior 10% — đa dạng hoá sleeve chỉ là núm rủi ro đắt đỏ, không phải edge), không cần thêm bằng chứng prospective cho allocator này.
