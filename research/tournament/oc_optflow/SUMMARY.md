# oc_optflow SUMMARY (≤15 lines)
Q: does informed (short-dated OTM taker/block) Deribit flow predict majors? Descriptive, dev 2021-09-24..2025-09-23.
F1=24h taker-imbalance, F2=24h block-imbalance, F3=4h taker-imbalance, all / 30d mean|flow|; SOL/BNB/XRP←BTC.
(a) BOOK pooled |IC| ≤ 0.018/yr (overall ≤ 0.009); only F1/z1 same-sign 4/4 but |IC|≈0.004; CIs ±0.2-0.6 cover 0.
(b) DIPS (base 7.718 reproduced exactly): F1 +0.017/+.038/+.051/−.016, F3 +.007/−.093/−.065/−.048; terciles non-monotonic.
CANDIDATES: none (rule: same sign 4/4 + pooled |IC|≥0.02). No trading rule scored or proposed.
Leakage: F(T) uses hours ending ≤T−1s only (unit-tested); labels strictly post-T; dev-only rows.
Costs N/A (descriptive; ICs vs 4-8 bps cost ⇒ nothing exploitable).
Files: compute_optflow.py, results.json, ic_book.csv, dips_terciles.csv, REPORT.md; tests/test_oc_optflow.py (3 passed).
Verdict: REJECT — hướng đóng lại. / LOẠI informed-flow. / Không rule tiếp theo.
