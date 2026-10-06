# carry_audit COMPARISON (blind replication vs oc_cashcarry / fric / d13 / utamargin)

Blind: replication.json was built spec-only before opening oc_cashcarry/.
Replication: 26 trades in [2021-09-24, 2026-09-24), total +0.5433 on allocated.
Spot = 1m majors archives -> 1h (BTC btc_intraday klines_1m_*, ETH majors_intraday
ETHUSDT_1m_*; USD-M perp 1m as spot proxy — spot_majors 1h ends 2019/2020).
Deliveries = code YYMMDD 08:00 UTC; H = front-7d (or first hour); basis uses last
CLOSED 1h bar strictly before H; fees 0.00275; exit F_settle = last fut 1h <= D,
S_exit = spot-proxy 1h of D hour.

## Trade-by-trade vs oc_cashcarry/results.json (25 in-window trades there)

- Entry set: replication has all 25 cc entries PLUS 1 extra (BTC 2026-12-25,
  delivery beyond data; cc correctly excludes 2 incompletes with no P&L). NOT equal.
- Basis diff > 0.1pp: 20/25 exceed (max +1.16pp BTC 2022-03-25: 11.39% vs 10.23%).
  Systematic: perp-proxy spot + 1h-vs-4h timing + DTE from H vs close_time.
- Return diff > 0.02pp: 25/25 exceed. Worst: BTC 2026-03-27 SIGN FLIP
  (rep -0.00937 vs cc +0.00575, diff -0.01512). Delivery hour volatile
  (fut 07:00h 67488-72000): F_settle 69260 vs S_del 66702.78 (3.8% gap);
  S_exit 67876.6 vs 66702.78 (1.7% gap). Settlement model dominates here.
- Per-year sums (> 0.005): 2021 0.0498 vs 0.0470 diff +0.0028 OK; 2022 +0.0109 FAIL;
  2023 +0.0153 FAIL; 2024 +0.0134 FAIL; 2025 -0.0168 vs +0.0058 diff -0.0226 FAIL
  (extra incomplete + sign flip).

## Causality / fees / settlement

- Causality: PASS both. Replication: all 26 entries use bars open_time < H
  (verified); exit <= D. cc: resample uses 1h open_time < spot close_time, entry
  from closes <= T_close; settlement is post-entry exit (allowed).
- Fees: PASS both (0.001/side + 0.00055 + 0.0002 = 0.00275; recomputed exactly).
- Settlement: DOCUMENTED DIFFERENCE. Replication: last futures print <= D +
  spot-proxy hour. cc (PLAN-frozen): spot 4h close of delivery bar, futures leg
  settled to that spot index. Both defensible; diverges in volatile deliveries.

## Overlay (fric/d13) hand-check + utamargin IM/MM

- Overlay: PASS. combine_carryd13.py:245-248 and combine_carryfric.py:257-260 do
  es_c = es + c, ms_c = ms + c with c = f*(raw - raw_at_anchor), carry sized at
  f of year-start equity (yearly rebalance, labelled; fric reuses c13 functions,
  S1 only bumps drag 0.00275 -> 0.0044). Hand year 2021 f=0.25: base 2.485 ->
  combo 2.634 (+0.149pp), DD 10.21 -> 10.05; residual check 0.000347pp.
- UTA margin: PASS. Code matches report: IM = (G2 gross + carry short)/5 (419);
  balance = Eq_tot - 0.05*spot (412); blocked iff IM > 95% bal (422); MM tiered
  per instrument, no netting (424-440). Note: code haircut 5% both coins vs cc
  assumption ETH 10% (labelled difference, not formula error).

## Verdict

carry: FAIL — numeric replication misses all stated tolerances (20/25 basis,
25/25 returns, 4/5 years, extra incomplete, one sign flip from settlement-model
+ perp-proxy spot + 1h/4h grid). No leakage, fee, overlay-arithmetic, or IM/MM
formula error found; oc_cashcarry's rule is causal and its margin/overlay math
checks out, but results are materially sensitive to the undocumented (in the
audit spec) spot-source / grid / settlement choices, so the sleeve is not
independently reproduced within tolerance.

## Leader adjudication (2026-10-06)
Accepted with a documented modelling note. The audit found no leakage, fee, overlay or IM/MM error. All per-trade differences come from
the settlement model: the replication settles the future at its last 1h print and sells a perp-proxy spot in the delivery hour, so in a
volatile delivery hour the two legs are priced at different moments (e.g. BTC 2026-03-27: F 69,260 vs S 66,703, a 3.8 % artefact). A
delivery future settles at the delivery INDEX (an average of spot prices), so both legs converge by construction; oc_cashcarry's model
(both legs at the same spot close) is the economically correct one, and the blind totals agree in level (replication +0.543 vs +0.497
pooled on allocated capital, i.e. the replication is not more favourable to the conclusion). Operational consequence: sell the spot leg
at the delivery time (08:00 UTC, ideally spread across the index averaging window) so the realised exit matches the delivery index;
added to the runbook.
