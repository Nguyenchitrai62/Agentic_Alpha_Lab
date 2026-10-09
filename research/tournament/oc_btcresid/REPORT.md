# oc_btcresid — REPORT (IDEAS8 §1: BTC-residual idiosyncratic book)

Rule: `w_resid_c(T) = w_c(T) - beta_c[A(T)] * w_BTC(T)` after the exact v421 bear
filter, before the shifted-clock ffill (BTC leg -> 0). V1 raw beta, V2 beta clipped
[0,1]. Betas = OLS(coin 4h log-ret on BTC 4h log-ret) over [A-372d, A-7d), frozen per
anchor year. C1/C2 = exposure-matched constant controls (`m = mean gross_V /
mean gross_REF` per year, in-year diagnostic). Members frozen (`research_books_d2`).
Engine vs G2 (R2B1D17BFG2), gate costs inside. REF reproduces v421 to the digit.

Betas (pre-anchor, embargoed): 2021: ETH 1.03 SOL 1.12 BNB 1.02 XRP 1.04;
2022: 1.15/1.33/0.92/0.93; 2023: 1.06/1.61/0.83/1.03; 2024: 0.99/1.39/0.81/0.80;
2025: 1.19/1.33/0.71/1.28 (BTC == 1).

## Dev years 2021-2024 (4-phase reset %/mo R / DD; book_win pooled over 4 shifts)

| row | 2021 | 2022 | 2023 | 2024 | dev4 R | W | DDmax | losing | book_win (trades) |
|-----|------|------|------|------|--------|---|-------|--------|-------------------|
| REF | 2.588/10.86 | 3.282/16.91 | 6.045/15.81 | 10.677/8.27 | 5.601 | 2.588 | 16.91 | 0 | 0.511 (3934) |
| V1 | -0.104/20.51 | -0.249/28.69 | -1.399/22.58 | 1.048/23.66 | -0.180 | -1.399 | 43.84 | 3 | 0.500 (2894) |
| V2 | -0.102/19.68 | 0.011/28.21 | -0.323/21.35 | 1.421/24.43 | 0.249 | -0.323 | 42.39 | 2 | 0.497 (2930) |
| C1 | 2.680/10.63 | 4.117/16.31 | 5.542/15.26 | 9.638/9.91 | 5.463 | 2.680 | 16.31 | 0 | 0.515 (3941) |
| C2 | 2.665/10.78 | 3.692/17.05 | 6.314/15.82 | 10.095/9.11 | 5.653 | 2.665 | 17.05 | 0 | 0.511 (3805) |

Realised gross scale m (variant/REF): V1 0.82/1.34/1.17/1.35, V2 0.78/1.20/0.97/1.22.
Controls track REF (5.46/5.65 vs 5.60) while residuals collapse: the loss is
composition (removing the BTC beta leg removes the P&L), not exposure.

## Robust pick (dev4 only, among V1/V2): none-eligible

V1: DD 43.84 > 20, 3 losing years. V2: DD 42.39 > 20, 2 losing years.
beats-control: V1 False (R -0.18 < 5.46 AND DD worse), V2 False (0.25 < 5.65).
No last-year scoring for variants (nothing eligible to score).

## Scored-once year 2025-09-24..2026-09-23 (REF only, labelled)

REF Y4 = 4.648 %/mo, DD 12.90 (reproduces v421 G2 Y4 to the digit); 5y = 5.41 %/mo,
W5y = 2.588, full-path DD 16.82 (marked 16.82 / close 16.05). Y4 book_win 0.5365.

## Fee split (engine stats, mean per phase sub-account, dev stage)

| row | fees | funding (longs pay) | fills | stops | TPs | liq |
|-----|------|------|-------|-------|-----|-----|
| REF | 0.0518 | 0.1028 | 992 | 151 | 35 | 0 |
| V1 | 0.0360 | 0.0263 | 733 | 93 | 7 | 0 |
| V2 | 0.0368 | 0.0264 | 742 | 93 | 6 | 0 |
| C1 | 0.0567 | 0.1122 | 995 | 158 | 37 | 0 |
| C2 | 0.0530 | 0.1071 | 962 | 149 | 36 | 0 |

All R above are NET of these costs. Residuals pay less funding (BTC/long beta leg
zeroed: 0.026 vs 0.103) but lose ~5.4pp/mo of return anyway; TP rate collapses
(7/6 vs 35-37 take-profits per sub-account).

## Leakage checklist

- Feature timing: C4(T)/r(T) use closes <= T only; residual uses close-known weights
  + pre-anchor betas; truncation-tested (`test_causality_truncation_synthetic`,
  `test_no_future_hour_synthetic`); T < 2021-09-24 never adjusted.
- Label windows: no labels fit (betas are unsupervised OLS slopes, not returns-to-trade).
- Fit windows: betas from [A-372d, A-7d) per anchor, 7d embargo; embargo verified by
  `test_beta_embargo_uses_only_window` against stored `rets_std.parquet`; no test-year
  statistic feeds any choice; thresholds: none (only frozen windows + OLS formula).
- Fill timing: win_start=5 + 1m trade-through + stop-first, inside `engine_user`
  (untouched); costs maker 0.0002/taker 0.00055, longs 0.0001/8h, shorts 0.
- Selection: dev4 only; Y4 scored once for REF (validation, reproduces v421 exactly);
  variants never see Y4. CLOSED rows oc_xsrev/oc_dombook read; this direction is now
  CLOSED (tested, rejected).

## Post-hoc log

- 2026-10-08: `compute_beta.py` indexing bug (`m.to_numpy()` on ndarray) fixed before
  any outcome; PLAN definitions unchanged.
- 2026-10-08: after first dev outcomes, `run_engine.py` extended to ALSO record the
  engine's own `stats` dict (fees/funding/fills; no rule/engine-input change) and both
  stages re-run; new runs verified bit-identical (equity + wins) to the backed-up
  first runs (`tmp/*.equitybak.pkl`). Original rows stay; no extra variant added.

## Verdict: REJECT (clean negative; direction closed)

Residualising the book on BTC beta destroys the edge it was meant to isolate:
V1 -0.18 / V2 +0.25 %/mo vs +5.6 controls, DD > 40, book_win back to ~0.50.
The BTC beta leg carries the book P&L (oc_bookattrib timing, not beta to remove).

Nhan dinh tieng Viet (3 dong):
- Y tuong residual-BTC that bai sach: V1 -0.18%/thang, V2 +0.25%/thang, DD > 40, thua xa control khop-exposure.
- Phan beta-BTC chinh la nguon P&L cua book, khong phai phan can loai bo.
- Dong huong nay: REJECT, khong can bang chung bo sung.
