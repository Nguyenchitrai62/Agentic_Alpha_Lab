# oc_fmbookic — SUMMARY (diagnostic, nothing selected)

Q: do Chronos/Toto/TimesFM medians carry BOOK direction info (clean year)?
A: NO — Y4 pooled median ICs vs y_h are +0.01/-0.00/+0.02 (h=1), all ns at
h=1/2/6/18; per-coin 29/30 ns at h=1/2 (max|IC| 0.05, noise).
Dev spread positives (+0.02..+0.06 sig h=1/2) vanish on Y4 (≈0/negative, ns).
Spreads DO carry vol info: +0.16..+0.23 vs |y_h| on Y4, every year, all h.
Chronos median correlates +0.28 with FINAL book weights (all 5y) but has no
forward IC — same-side positioning, no new direction. Toto/TFM medians ~0 vs w.
Method: oc_kronosfeat Table-2 template (y at bar open T, sigma trailing-360,
week-block B=500); rows Y0..Y4 43800x4+43785; weight join 54750.
Verdict: KHÔNG dùng median FM cho book hướng; spread chỉ là tín hiệu biến động.
