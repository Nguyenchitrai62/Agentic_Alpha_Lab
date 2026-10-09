# oc_carryhurdle REPORT — IDEAS11 #1: quarterly carry fee-hurdle (2026-10-08)

Method: frozen oc_cashcarry pair list (33 entered, threshold 0.04/yr) + verbatim
oc_carrycompound compounding overlay (ONE account A(t)=A(t-1)*(1+r_bot(t))+dU(t),
f=0.25, N=f x live A at each entry, held to delivery, causal hourly marks —
last CLOSED hourly strictly before t, 0 before entry-close, locked to frozen
ret_alloc at settlement; per-year reset to 1.0; spanning rebased to 0; v421
full-path DD). Hurdle applied LITERALLY as assigned (annualised basis number
vs H x round-trip cost): C=2*0.001+0.00055+0.0002=0.00275; V1 H=2.0 → T1=0.0055;
V2 H=1.5 → T2=0.004125; entry iff frozen-pass AND ann_basis ≥ H*C. Two BOT legs:
G2 Binance (v421 R2B1D17BFG2) and G2 Bybit-S5 (runs_S5.pkl REF; Bybit live from
2021-11-15 so y2021 SHORT). Repro: `analyze_carryhurdle.py` (one process,
hourly only, no 1m, no engine reruns). No fitting; H from the fee schedule only.

## Reproduction gates (PASS — else STOP)

- f=0 Binance == v421 G2 to the digit (5.41/W 2.588/DD 16.91/full 16.82).
- REF f=0.25 Binance == oc_carrycompound (5.634/W 2.778/DDmax 16.75/full 16.66).
- REF f=0.25 Bybit-S5 == oc_c2carry G2_carry_bybit_S5
  (5.111/W 2.321/DDmax 17.95/full 17.93; years 2.321/12.36, 2.808/17.95,
  5.484/16.67, 10.656/9.15, recent 4.493/12.13).

## Hurdle binding (pre-registered trap confirmed)

- All 33 frozen-entered pairs have ann_basis 0.0422–0.2611 (min 0.042188 BTC
  2026-03-27) >> T1=0.0055 > T2=0.004125. Extra skips beyond frozen: V1 0, V2 0.
  V1 = V2 = REF bit-exact on every row, both venues. The hurdle never binds
  because the frozen 0.04 filter is ~7x stronger than H*C by construction.

## Skipped pairs per year (frozen-skipped; V1/V2 skip nothing more)

Recomputed verbatim with the frozen cashcarry entry rule (hypothetical P&L =
gross − 0.00275, labelled hypothetical — never traded):

| anchor year | entered (frozen) | skipped | skipped pairs (ann_basis → hypo ret_alloc) | hypo sum_alloc (f=0.25 acct/yr) |
|---|---|---|---|---|
| 2021-09-24 | 4 | 4 | BTC 2022-09-30 0.034823→+0.006686; ETH 2022-09-30 0.028139→+0.006917; BTC 2022-12-30 0.008156→−0.000840; ETH 2022-12-30 −0.004667→−0.003907 | +0.008856 (+0.22%) |
| 2022-09-24 | 4 | 4 | BTC 2023-03-31 0.010170→+0.001764; ETH 2023-03-31 −0.001648→−0.003398; ETH 2023-06-30 0.037087→+0.007561; ETH 2023-12-29 0.032681→+0.010205 | +0.016132 (+0.40%) |
| 2023-09-24 | 8 | 0 | — | 0 |
| 2024-09-24 | 8 | 0 | — | 0 |
| 2025-09-24 (post-release context only) | 1 | 5 | BTC 2026-06-26 0.023771→+0.002604; BTC 2026-09-25 0.031128→+0.008472; ETH 2026-03-27 0.033983→+0.003341; ETH 2026-06-26 0.021506→+0.001397; ETH 2026-09-25 0.016745→+0.004444 | +0.020258 (+0.51%) |

Carry-pair hit rate: entered 33/33 profitable (min ret_alloc +0.00182); skipped
hypothetical 10/13 profitable, 3 negative (the two Dec-2022 expiry pairs +
ETH Mar-2023). V1/V2 realised P&L vs REF: +0.000000 (nothing skipped, nothing saved).

## Overlay results, per anchor-year R %/mo / DD % (reset metric, fresh 1.0)

V1=V2=REF on all rows below (hurdle binds nowhere). Dev4 = selection universe;
recent = post-release, scored ONCE for pick (V1) + REF only (V2 has no recent/5y/full by protocol).

| leg | 2021 | 2022 | 2023 | 2024 | recent 2025 (once) | dev4 mean/worst/DD/losing | 5y mean/worst/maxDD (pick+REF) | full-path m/c/full (pick+REF) |
|---|---|---|---|---|---|---|---|---|
| Binance REF/V1/V2 (dev4) | 2.778/10.86 | 3.353/16.75 | 6.590/15.69 | 10.956/8.20 | — | 5.870/2.778/16.75/0 | — | — |
| Binance V1=REF (5y) | ↑ | ↑ | ↑ | ↑ | 4.698/12.66 | — | 5.634/2.778/16.75/0 | 16.66/15.90/16.66 |
| Bybit-S5 REF/V1/V2 (dev4) | 2.321/12.36 SHORT | 2.808/17.95 | 5.484/16.67 | 10.656/9.15 | — | 5.266/2.321/17.95/0 | — | — |
| Bybit-S5 V1=REF (5y) | ↑ | ↑ | ↑ | ↑ | 4.493/12.13 | — | 5.111/2.321/17.95/0 | 17.93/17.34/17.93 |

Robust pick on dev4 ONLY: V1, V2 both DD≤20 + no losing year on both venues;
dev4 means ≥5%/mo on both venues; worst-year tie (Binance 2.778, Bybit 2.321) →
frozen tie-break picks V1 (larger H, more conservative). V2 dev4 rows identical,
kept for the record; V2 has no recent/5y/full-path rows (never scored).

## Leakage / causality checks (how verified)

- Feature timing: carry entries use only 4h closes ≤ entry close (frozen rule,
  re-verified by recompute: 13 skipped recovered exactly); MtM uses last CLOSED
  hourly strictly before t, 0 before entry-close; `test_carry_mtm_causal_truncation`
  recomputes from a truncated hourly table — identical on the kept prefix.
- Label windows: no labels fit here; hurdle constants from the fee schedule only.
- Fit windows: no refit; hurdle uses no data window (H*C fixed); BOT legs frozen.
- Fill timing: inherited engine (win_start=5, trade-through, stop-first); no 1m
  reads in this overlay. Tests: `tests/test_oc_carryhurdle.py`.

## What failed / caveats

- Nothing failed mechanically (all gates pass bit-exact); the idea fails
  substantively: the hurdle as literally specified (H*C = 0.55%/0.41%/yr) is
  ~7–10x weaker than the frozen 0.04/yr filter, so it cannot skip anything —
  carry add stays +0.224pp Binance / +0.228pp Bybit, DD flat, by identity.
- A hurdle that could bite would need H*C ≳ 0.04 (H ≳ 15) or a gross/net-profit
  formulation — both are NEW ideas, not this assignment; H was frozen at 2.0/1.5
  and must not be tuned on returns (trap respected).
- Carry leg close-marked (DD lower bound); Bybit y2021 SHORT; 5y rows are
  post-hoc on the same five years (needs prospective paper like all carry).

## Vietnamese verdict (3 lines)

- Hurdle H=2,0/1,5 theo đúng định nghĩa (0,55%/0,41%/năm) yếu hơn hẳn ngưỡng đông lạnh 0,04 nên không loại thêm cặp nào: V1=V2=REF trên cả Binance và Bybit, hiệu quả bằng 0.
- Robust pick trên dev4 (theo luật tie-break đã đóng băng): chọn V1; năm post-release chỉ chấm một lần cho V1 và REF (Binance 4,698 / Bybit 4,493, dưới ngưỡng 5%).
- Kết luận: reject — đóng hướng hurdle dạng này, không tune H trên lợi nhuận; muốn rào phí có tác dụng phải đăng ký hướng mới (ngưỡng tuyệt đối/lợi nhuận ròng).
