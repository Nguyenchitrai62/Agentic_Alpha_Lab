# Audit COMPARISON — oc_carrymore (Binance COIN-M carry, BTC/ETH/BNB/SOL/XRP)

Blind replication (`replicate_carrymore.py`, independent code from
`fetch_cm_quarterly.py`+`MANIFEST.json`, `oc_cashcarry/PLAN.md`,
`oc_carrycompound/` method) wrote `replication.json` BEFORE
`oc_carrymore/REPORT.md`+`results.json` were opened. Tolerances: 0.01 %/mo,
0.05 pp DD, trade count exact.

## Gated metrics (replication vs REPORT)

| metric | replication | REPORT | diff | status |
|---|---|---|---|---|
| trades entered total | 55 | 55 | 0 | EXACT |
| per coin BTC/ETH/BNB/SOL/XRP | 18/16/5/3/13 | 18/16/5/3/13 | 0 | EXACT |
| all 55 trades ann_basis/ret_alloc/worst | — | — | 0.0 (<=1e-6) | EXACT |
| F_entry/S_entry/S_del per trade | — | — | 0 (rel <1e-9) | EXACT |
| (a) G2+cm BTC+ETH 5y %/mo | 5.626 | 5.626 | 0.000 | PASS |
| (a) worst year | 2.746 | 2.746 | 0.000 | PASS |
| (a) max yearly DD / full-path DD | 16.91 / 16.82 | 16.91 / 16.82 | 0.00 | PASS |
| (a) per-year R | 2.746/3.314/6.600/10.971/4.702 | same | 0.000 | PASS |
| (b) G2+cm ALL 5y %/mo | 5.771 | 5.771 | 0.000 | PASS |
| (b) worst year | 2.853 | 2.853 | 0.000 | PASS |
| (b) max yearly DD / full-path DD | 16.91 / 16.82 | 16.91 / 16.82 | 0.00 | PASS |
| (b) per-year R | 2.853/3.327/6.902/11.263/4.730 | same | 0.000 | PASS |
| f=0 reproduces G2 base | 5.410/2.588/16.91/16.82 | same | 0 | EXACT |
| pooled in-window sums | 0.040904/0.042749/0.517057/0.227397/0.005598 | same | 0 | EXACT |

## Capital (methodology note, not a mismatch)

Max concurrent pairs recomputed from replication trades: 4 (BTC+ETH),
8 (ALL) — matches REPORT §5. Peak spot-notional vs LIVE equity on the
compounded path: 1.04x (BTC+ETH), 1.75x (ALL); REPORT's 1.0x/2.0x is the
static pairs×f count. Both agree borrowing is needed for (b) at f=0.25/coin.

## Known immaterial difference (no P&L impact)

Skip/incomplete bucketing for 2 contracts that BOTH fail the 4%/yr threshold
AND deliver beyond the data (SOL 261225 ann 1.87%, XRP 261225 ann 2.67%):
replication counts threshold-first (skipped 54 / incomplete 3), REPORT counts
delivery-first (skipped 52 / incomplete 5). PLAN.md does not fix the check
order; no entered trade, no return, no overlay value changes either way.

## Look-ahead checks (all pass)

- F resampled as last 1h close with 1h open_time < spot close_time (strict).
- Entry uses only closes at T_k (F_entry/S_entry from bars with close <= T close).
- Settlement = delivery-bar spot close; 3 undeliverable excluded, none imputed.
- Overlay marks: last CLOSED hourly bar strictly before t, 0 before
  entry-close, frozen ret_alloc from settlement; assert ts > tc per trade.
- Truncation spot-check in `tests/test_audit_carrymore.py`: data cut at entry
  close reproduces F_entry/S_entry.
- Replication script references no 1m/intraday paths.

## Verdict line

PASS — oc_carrymore replicates to the digit on trade count, all 55 trades,
both G2 overlay rows and drawdowns; the only delta is skip/incomplete
labelling of 2 never-entered contracts.
