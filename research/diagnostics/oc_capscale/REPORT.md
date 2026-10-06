# oc_capscale REPORT — Capital scaling of R2B1D17BFG2 (2026-10-06; PLAN pre-registered)

## Setup
Deployment config R2B1D17BFG2 (v421 wiring: inv-correlated dip x kd=1.7,
risk_mult 1.0, budget 0.26x1.7, gross cap G=2.0, win_start=5, bear-halved
books), 4-phase (clock shifts 0..3h) x 5 anchor years 2021-2025, reset
metric + conservative full-path DD (same code as v421). Rows: total account
A = 2000 / 5000 / 10000 / 25000 USDT, each phase sub-book E = A/4,
`eu.ACCOUNT = A/4`, Bybit-like minimum notional 5 USDT every symbol
enforced natively in-path for book entries (exact). Qty steps + dip rungs
counted post-hoc from events with causal info only (see PLAN.md). Lot
rules fetched LIVE from Bybit: BTC 0.001 / ETH 0.01 / SOL 0.1 / BNB 0.01 /
XRP 0.1, min notional 5 USDT. Unconstrained = v421 cache, same metrics.
Repro: research/diagnostics/oc_capscale/{PLAN.md,run_oc_capscale.py,results.json}.

## Performance per account (reset metric; deltas vs unconstrained)
| A (E=A/4) | 5y %/mo | Worst yr | max yr DD | full-path DD | dR5 | dfullDD |
|---|---|---|---|---|---|---|
| 2000 (500) | 5.41 | 2.588 | 16.91 | 16.82 | 0.000 | 0.00 |
| 5000 (1250) | 5.41 | 2.588 | 16.91 | 16.82 | 0.000 | 0.00 |
| 10000 (2500) | 5.41 | 2.588 | 16.91 | 16.82 | 0.000 | 0.00 |
| 25000 (6250) | 5.41 | 2.588 | 16.91 | 16.82 | 0.000 | 0.00 |
Unconstrained: 5.41 / 2.588 / 16.91 / 16.82 (years 2.588, 3.282, 6.045,
10.677, 4.648). Per-year rows are identical at every size.
Finding: the 5-USDT notional minimum binds NOTHING at any tested size -
paths are bit-identical across sizes within each phase (entry floor =
5% signal threshold x E >= 25 USDT even at A=2000). The binding
constraint is the Bybit qty step (one BTC step = 60-126 USDT over the
window), which the engine does not enforce in-path.

## Placeability under Bybit rules (pooled 4 phases; 9051 book sizings, 21513 rungs)
| A | book entries+adds (count / weight) | dip rungs (count / net / gross P&L) |
|---|---|---|
| 2000 | 0.9585 / 0.9704 | 0.9269 / 0.9950 / 0.9804 |
| 5000 | 0.9990 / 0.9995 | 0.9780 / 0.9985 / 0.9967 |
| 10000 | 1.0000 / 1.0000 | 0.9908 / 1.0014 / 0.9992 |
| 25000 | 1.0000 / 1.0000 | 0.9965 / 0.9999 / 1.0000 |
In-path book-entry skip for minimums: 0.000 at every size.
Bottleneck = BTC then ETH (count share book / dip):
A=2000 BTC 0.844/0.799, ETH 0.954/0.895; A=5000 BTC 0.996/0.930,
ETH 0.999/0.980; A=10000 BTC 1.000/0.972; SOL/BNB/XRP books placeable at
every size, dip >= 0.97 everywhere except BTC/ETH at A=2000.

## Caveats
- The R5/DD rows at small A are UPPER bounds: the engine traded the
  qty-step-unplaceable orders (mostly tiny BTC/ETH Sizings). The true drag
  is bounded by the skipped weight/gross shares (A=2000: ~3% of book
  weight, ~2% of dip gross; A=5000: ~0.05% / ~0.3%).
- Dip minimums are counted, not enforced in-path (no engine hook sees
  equity + fill price); skipped rungs are dust (< max(5, step-value) USDT
  on >= A/4 equity), hence the gross-share bound.
- Dip net share > 1 at A=10000 (1.0014): the few skipped dust rungs were
  net losers - arithmetic, not an error.
- Five research years, one config, no selection; needs prospective
  confirmation like every retrospective cut.

## VERDICT (khuyen nghi trien khai)
- Tai khoan TOI THIEU: 5000 USDT (1250/sub-book). Tai day >= 99% book
  sizings (99.90%, 99.95% trong so) va >= 99% dip gross P&L (99.67%) dat
  duoc; R5/DD bang unconstrained (sai so duoi bound ~0.3%).
- Muc THOAI MAI: 10000 USDT (2500/sub-book) - book 100%, dip gross
  99.92%, chi con rung rac (< 0.1% gross) khong dat. Muon dat gan nhu
  moi rung (dem, khong phai P&L) thi 25000 USDT (dip 99.65%).
- DUOI 5000 USDT (dac biet 2000) KHONG nen chay cau hinh nay nhu mo
  phong: ~16% book BTC va ~20% rung dip BTC khong dat duoc lot Bybit,
  chu yeu do qty step BTC/ETH.
