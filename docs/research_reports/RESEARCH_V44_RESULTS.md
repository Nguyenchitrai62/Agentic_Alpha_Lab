# BTC research v44 — 2026-09-06

V44 tested a causal meta-ranker over the already replay-audited v29 forecasts.
For each fold, the shared HGB net/fill model used only earlier valid v29
forecast rows whose labels matured at least 8 days before the fold's `asof`,
within a 730-day window. The input contained 40 context features, six
candidate parameters, per-seed expected-net/fill outputs, and their mean/std.

The result was rejected. At 1x, the continuous policy produced 79 fills and
`+20.662%` net / `-28.423%` drawdown / `+0.559%` monthly geometric net in
normal costs; gross PnL was `+29.076%`, fees `3.519%`, and funding `4.895%`.
Fee stress produced `+14.150%` net / `-28.937%` DD / `+0.393%` monthly with
gross `+28.294%`, fees `9.399%`, funding `4.745%`, and 79 fills. Execution
stress produced `+7.603%` net / `-24.745%` DD / `+0.218%` monthly with gross
`+15.852%`, fees `4.435%`, funding `3.813%`, and 66 fills. The 0.5x branch
reduced drawdown to `-13.104%` in execution stress but reached only `+0.141%`
monthly. No scenario met the 5% monthly and 20% DD gate together.

Data/protocol: 4,076 continuous decisions, 2023-06-01 through 2026-03-23,
2.809092589 years; all dates are development data, not an independent test.
No live approval.

Config: `configs/swing_v44_meta_ranker_probe.json`.
Summary: `artifacts/research/v44_meta_ranker_probe/summary.json`.
Config SHA-256: `E02E567BC352141E8513BF62EAB0447639023EC5A19FF3254AA9D453C3E5FF52`.
Summary SHA-256: `82D981BA2DD0AC87D0FADC5FB0B62BDA4CB6C731F6E78656BB9A111F0610C3C9`.

The next materially different heavy hypothesis remains the packaged v33
action-margin GRU. Its private Kaggle upload still requires explicit user
authorization because the package contains internal BTC research source/data;
no upload occurred.
