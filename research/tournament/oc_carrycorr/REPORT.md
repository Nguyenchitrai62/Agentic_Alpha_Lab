# oc_carrycorr REPORT — does the carry sleeve diversify G2?

Question: correlation of the frozen cash-carry sleeve's daily mark-to-market
with G2 (R2B1D17BFG2) daily returns — overall, in G2's 10 worst weeks and DD
episodes; entry basis vs the BOT's return in the same quarter window; carry
MtM on the 5 worst crash days. Repro:
`research/tournament/oc_carrycorr/analyze_carrycorr.py` (1h+4h only, one
process, no 1m, no engine reruns) + `tests/test_oc_carrycorr.py`.
Inputs frozen: `oc_cashcarry` 33 trades reused verbatim (hourly mark exactly
as `oc_carryd13`: last closed hourly bar strictly before t, entry fee 0.00155
in MtM, full 0.00275 in ret_alloc); G2 = continuous hourly mix (mean of 4
phases, v388.hourly ffill, 2021-09-24 04:00 .. 2026-09-23 12:00 UTC);
daily sampled at 00:00 UTC (G2 logret vs carry P&L at f = 0.25 of unit
capital; correlations scale-free). All five years are research data;
diagnostic only, no selection claim.

## (1) Daily correlation (1,824 days, 2021-09-25 .. 2026-09-23)

- Overall: Pearson −0.0909 / Spearman −0.0782 (logret vs carry P&L;
  simple-return Pearson −0.0871). Effectively uncorrelated, tiny negative tilt.
- 10 worst non-overlapping G2 weeks (7d logret −0.059..−0.116, sum −0.8557):
  carry 7d P&L at f = 0.25 sums to +0.0097 (positive in 6/10 weeks, flat 0.0
  in 2 gap weeks with no pair open, −0.0009 worst). Daily corr inside worst
  weeks: Pearson −0.3777 / Spearman −0.0283 (Pearson driven by a few large-G2
  down days against a flat/slightly-up carry, not by carry losses); outside
  worst weeks: −0.0364 / −0.0853. Mean carry/day is HIGHER inside worst weeks
  (+0.000139) than outside (+0.000075).
- 3 deepest daily-path DD episodes (15.99% 2023-04-17..06-15, 12.55%
  2023-08-16..10-01, 11.80% 2024-01-03..01-04): carry P&L at f = 0.25 is
  +0.0018 / +0.0029 / +0.0068 over the episode, never dipping below the
  episode-start level (min 0.0). Daily corr inside DD: −0.6527 / −0.1611
  (again: G2 falls while carry drifts up/flat).

Answer (1): NO — carry does not lose when the BOT loses. It is flat-to-up
during G2 stress (idle gaps + locked-basis drift).

## (2) Entry basis vs BOT return in the same holding window (25 trades with G2 defined; 8 pre-G0 excluded)

- Pearson −0.1561 / Spearman −0.0235 between frozen ann_basis and G2
  holding-window return (mix at settlement / mix at entry − 1).
- Median split (median basis 6.86%/yr): mean G2 hold return 0.2389 above
  median vs 0.2016 below — indistinguishable given ~90d windows.
- High-basis regimes (e.g. 2023, mean ~13%) coincide with strong BOT years,
  but per-trade there is no slope: a rich basis does not predict a weak BOT
  quarter, nor a strong one.

Answer (2): DIVERSIFICATION by uncorrelation, not concentration — entry
richness tells you nothing about the BOT's quarter; the two P&Ls stack
additively.

## (3) Crash days: carry MtM (basis widening vs collapse)

5 worst G2 daily logrets:

| date | G2 logret | carry f=0.25 | BTC logret | read |
|---|---|---|---|---|
| 2024-01-04 | −0.1256 | +0.00677 | −0.0485 | widening |
| 2025-09-26 | −0.0898 | +0.00014 | −0.0389 | widening/flat |
| 2023-06-06 | −0.0833 | +0.00010 | −0.0526 | widening/flat |
| 2024-03-06 | −0.0818 | −0.00030 | −0.0689 | tiny collapse |
| 2024-06-08 | −0.0789 | −0.00058 | −0.0207 | tiny collapse |

5 worst BTC spot days (market cross-check, −0.110..−0.167): carry is
−0.00055 / −0.00048 / 0.0 / +0.00009 / +0.00014 — sign mixed, magnitude
<= 0.06% of account at f = 0.25, while spot moves 11–17%.

Answer (3): NO collapse — even on true market crashes the pair's net moves
<= 6 bps (f = 0.25); the delta hedge holds, residual is second-order basis
noise. 3/5 of G2's own worst days even print a positive carry (widening).

## Verdict

Carry is a genuine diversifier to G2: ~zero daily correlation (−0.09),
positive-or-flat through every stress cut (worst weeks sum +0.97% at f = 0.25
while G2 lost −85.6 log points; DD episodes all positive; crash days <= 6 bps),
and entry basis uncorrelated with the BOT's quarter (−0.16 / −0.02). It adds
its locked drift without adding stress loss — consistent with the earlier
sleeve-level findings (oc_cashcarry worst −0.66% at f = 0.25; oc_carryd13 DD
never rises; oc_utamargin clears f = 0.25 on one UTA).

KẾT LUẬN (tiếng Việt): carry là lớp đa dạng hóa thật sự cho BOT G2 — tương
quan ngày gần bằng 0 (−0,09), không lỗ khi BOT lỗ (10 tuần tệ nhất của G2 vẫn
lãi +0,97% ở f = 0,25; 3 đợt drawdown đều dương; 5 ngày crash chỉ lệch tối đa
6 bps), và basis lúc vào lệnh không dự báo gì về lợi nhuận của BOT trong quý
đó. Nói ngắn gọn: carry không cứu BOT khi sập (quá nhỏ để cứu), nhưng cũng
không sập theo — nó cộng thêm phần premium bị khóa mà không cộng thêm rủi ro
lúc stress. Giá trị đa dạng hóa: có, nhưng nhỏ và một chiều (lợi nhuận cộng
thêm, rủi ro không cộng thêm), đúng như các phân tích trước đã kết luận.
