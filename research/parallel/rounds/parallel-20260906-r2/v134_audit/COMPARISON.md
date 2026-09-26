# v134 blind audit — COMPARISON.md

## Part A (blind, saved before opening v134/)
- Built v133 from OPENCODE_V132_V133_AUDIT.md A2 without reading v132/v133/v134:
  v127 tranched books + v129 pvol (v114-panel pvol for v92 LO/v94 LS,
  v103-panel pvol for v103 LS, HGB v92 params, cutoff anchor-102x4h,
  rows t+44x4h<cutoff, pvol=exp(pred)) replacing vol42 before weights.
- v134 change only: v94/v103 LS short leg
  `((-pred).clip(0)/0.5).clip(upper=1)` where `rib == -1` (0 elsewhere);
  long legs unchanged (`rib != -1` gate + gross/active/5 scaling kept).
- Engine: tranche mean /6, own 0.20-cap-2 scales, books 0.25/0.25/0.5,
  target 0.15 sequential v110 ungoverned; hidden year v104 strict 1m rule
  ([T+2m,T+14m] through-check, T+15m fallback, missing-T taker) + v104
  cost path on tranched weights, no band.
- Post-hoc fix (logged, before opening v134/): first draft extended v103
  history like v114; corrected to non-extended v103 panel per v129 method
  and reran. pvol spearmans then match v129_v131_audit exactly.

## Replication vs v134/v134_result.json
| scenario | repl monthly / fullDD | v134 monthly / fullDD | diff |
|---|---|---|---|
| normal | 2.303 / 12.75 | 2.303 / 12.75 | 0 / 0 |
| fee_stress | 2.115 / 13.41 | 2.115 / 13.41 | 0 / 0 |
| execution_stress | 1.880 / 14.44 | 1.880 / 14.44 | 0 / 0 |
| hidden strict | net 20.96, DD 11.23, maker 0.848, orders 8863, fills 2155 | net 20.96, DD 11.23, maker 0.848, orders 8863, fills 2155 | 0 |
- Yearly nets/DDs/fills match exactly all 5 anchors x 3 scenarios.
- Return diff > 1pp or DD diff > 0.5pp: none — no explanation required.
- Context (leader refs in v134 JSON): v133 ref 2.44/2.222/1.95 hidden +29.0%
  DD 10.06; v127 ref 2.378/2.156/1.879 hidden +30.17% DD 9.98. Bear-only
  shorts lower both OOS return and hidden return in this sample.

## Look-ahead audit of v134_bear_only_shorts.py
- `raw_ls_bear_shorts`: same-t `pred`/`rib`/`vol42` only; long
  `where(rib != -1)`, short `where(rib == -1)`; `(long-short)/(vol*ANN)` +
  gross/active/5 scaling — same form as audited LS, gate narrowed per spec.
- Called via `v125.raw_ls = raw_ls_bear_shorts` before `v133.main()`, so
  both v94 and v103 books use it; `swap()` replaces vol42 with pvol BEFORE
  the weight call — matches "before the weight formulas".
- No new forward data: rib is daily SMA50/200 asof-backward on close_time;
  pvol training/cutoffs inherited unchanged from v129 (train_rows/spearmans
  reproduce v129_v131_audit exactly); engine uses shift(2)/shift(1)/rolling
  vol; hidden fill uses post-signal 1m bars only.
- File handling (`v133.HERE = HERE`, rename v133_result.json to
  v134_result.json, version relabel + reference_v133 stamp) does not touch
  metrics. Verdict: NO look-ahead.
- Caveat (script's own docstring): change is diagnostic-motivated by OOS
  per-side breakdown (shorts lose in bull years) — i.e. tuned on seen OOS
  years. Per rule 5 this is a hypothesis for the prospective log, not
  evidence; do not present as validated improvement.

## Files
- `replication.json` (Part A, blind), `replicate_v134.py`,
  `tests/test_v134_audit.py` pass.
