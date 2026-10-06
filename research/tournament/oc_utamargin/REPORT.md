# oc_utamargin REPORT — ONE Bybit UTA: G2 + frozen carry overlay at f = 0.25 / 0.50

Question: can ONE Bybit Unified Trading Account run G2 (R2B1D17BFG2) AND the
frozen cash-carry pair (spot BTC/ETH bought with the account's USDT, 95%
collateral; short quarterly at 5x) as an ADDITIVE overlay without margin
calls or liquidation at G2's worst minutes? Repro:
`research/tournament/oc_utamargin/analyze_utamargin.py` (one process, hourly,
43,805 hours 2021-09-24 00:00 .. 2026-09-23 04:00 UTC, no 1m, no engine
reruns) + `tests/test_oc_utamargin.py`. All five years are research data.

## Method (frozen inputs, nothing refit)

- G2 legs rebuilt HOURLY from stored `oc_kpi_g2` events/barsum with the exact
  `oc_margin` q-units math (book flats zeroed, dip FIFO, Hedge-Mode gross =
  |book_net| + |dip_net| per coin), hourly_ext marks (causal: last 1h bar with
  open_time < H), equity ffill. Recon vs barsum gross_book (`oc_margin`
  convention): median 0.0012/0.0015/0.0021/0.0021 per phase (oc_margin
  0.0006-0.0013) — rebuild OK; max 0.32-0.71 (hourly-mark timing +
  bar-boundary, disclosed, not used for the verdict).
- `v421_runs.pkl` equity series verified BIT-IDENTICAL to barsum (the pkl
  stores only t/eq/eq_min — no exits; exits come from `oc_kpi_g2` events).
- Carry: 33 frozen `oc_cashcarry` pairs reused verbatim (signal, F/S_entry,
  deliveries, ret_alloc untouched); legs = f x total mix equity at entry
  hour (`oc_carrycombo` convention), spot marked with hourly_ext proxy,
  shorts with qbasis 1h (causal). Max overlap 3 pairs (cost up to 3f).
- UTA math: IM = (G2 gross + carry short) / 5 (5x runbook minimum);
  MM = per-instrument TIERED (live Bybit tiers fetched 2026-10-06, frozen in
  results.json; no netting perp vs quarterly); balance = total equity −
  5% x spot value (BTC/ETH 95% base tier per Bybit UTA docs; < 10k stays
  base). Blocked iff IM > 95% balance; liquidation iff balance < MM.
  A0 = 10,000 USDT starting account for tier lookups (ratios scale-free).
- Plus: the 10 worst G2 minutes from `oc_margin` (hourly proxy, no 1m loaded
  — stated limitation) and a −10% all-coin instant gap at the worst UTA hour.

## Live Bybit tiers used (2026-10-06, `GET /v5/market/risk-limit?category=linear`)

| symbol | tier-1 limit | tier-1 MMR | max tier reached (A0 = 10k) |
|---|---|---|---|
| BTCUSDT | 300,000 | 0.33% | 0 |
| ETHUSDT | 300,000 | 0.33% | 0 |
| SOLUSDT | 50,000 | 0.50% | 1 |
| BNBUSDT | 10,000 | 0.67% | 4 |
| XRPUSDT | 50,000 | 0.50% | 2 |

5x is below every tier's max leverage (no forced deleverage). Even in the
top BNB tier, total MM stays <= 2.3% of balance — maintenance is negligible.

## Per-f results (43,805 hours; worst hour 2025-09-25 18:00 = G2's worst minute zone)

| f | min free margin | max IM/bal | hours IM>95% | MM breaches | max MM/bal | max spot cost/Eq | gap −10% loss |
|---|---|---|---|---|---|---|---|
| 0.25 | 22.49% | 77.51% | 0 | 0 | 1.95% | 95.8% | −28.85%, no liq |
| 0.50 | 1.85% | 98.15% | 1 | 0 | 2.29% | 179.9% | −29.07%, no liq |

- f = 0.25: ZERO blocked hours, ZERO MM breaches in five years; the −10% gap
  at the worst hour loses 28.9% of balance (71% left, no liquidation). G2
  gross there 2.85 + carry short 1.01 (fractions of mix equity). Funding
  caveat: spot legs lock up to 95.8% of equity as cost basis (headroom
  +4.2%); in the worst overlap hour a small UTA auto-borrow interest may
  accrue (NOT modelled — bounded, negligible vs the sleeve's +0.21%/mo).
- f = 0.50: ONE blocked hour (2025-09-25 18:00, IM 98.15%, free 1.85% — too
  thin for 1m wicks on top of the hourly proxy). That hour scheduled 21
  events, ALL exits (13 rung_tp + 8 rung_timeout, 0 new opens) — nothing to
  skip in hindsight, but the line is crossed. Worse: spot cost peaks at
  179.9% of equity (headroom −79.9%) — the USDT wallet MUST borrow for whole
  overlap stretches (interest unmodelled, no longer negligible).
- Worst-10 G2 minutes with the pair on: free margin 0.25-0.60 at f = 0.50,
  gap losses 30-35% of balance, NO liquidation and NO MM breach at any of
  them at either f.

## Verdict

ADDITIVE OK at f = 0.25 (largest safe f). f = 0.50 is NOT cleared on one
account (1 blocked hour + structural USDT borrowing) — above 0.25:
SPLIT CAPITAL ONLY.

KHUYEN NGHI: chay additive f = 0.25 tren mot UTA (5x, cross, hedge) — 5 nam
0 gio bi chan lenh, khong margin-call/liquidation ke ca gap −10% o phut te
nhat; f = 0.50 phai tach von (vua cham tran 95% vua thieu USDT mua spot).
Sleeve carry khong lam thay doi ket luan margin cua G2 (oc_margin giu nguyen).
