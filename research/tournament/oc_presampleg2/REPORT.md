# oc_presampleg2 REPORT (2026-10-08; PLAN pre-registered before any outcome)

## Setup (one pre-registered variant PB + two attribution rows, no tuning, no selection)

Deployed G2 = book (`research_books_d2`: A/Aq/B/Bq 0.2 each + D/Dq 0.1 each) + dip sleeve + caps.
No deployed member prediction exists before 2021-09-24 (all 7 cached members start there; probe).
Part B replays G2 mechanics at REPLICA level (PLAN-frozen label, NOT the v421 stack: no R2
walk-forward tables, no grid policy, no bear scaler, no DD governor - all fit on 2021-2026 and
unavailable pre-2020; R2 agent size = scale = governor = 1, same convention as oc_presample).
- PB book = 0.8*o1' + 0.2*d', o1' = (B_ps+Bq_ps)/2, d' = (D_ps+Dq_ps)/2 (pre-registered
  renormalisation with A/Aq dropped; the D-fallback was NOT needed - all four built).
- Dip leg = oc_presample2 G2 primitives BY IMPORT (never edited, never copied).
- Book leg = PLAN-frozen mechanics: ONE resting limit 10 bps better, live minutes 5..59 (no fill
  in first 5 min), strict trade-through, expire unfilled; SL = entry*(1-/+3*sg_d) market taker +
  TP = entry*(1+/-6*sg_d) limit maker (engine_user defaults); stop-first; gate costs; adverse
  funding; shared within-bar gross cap 2.0; causal one-bar lag (PB row known at row_t+4h).
- Rows: DIP0 = dip alone, BOOK0 = book alone, PB = book + dip (attribution by standalone legs;
  *_pnl sums are diagnostic - scales differ per bar).
- G1 GATE: PASS - DIP0 reproduces ALL 16 oc_presample2 G2 cells bit-for-bit on all 18 CELL_FIELDS
  (tmp/gate.json). v421-stack reproduction is out of scope pre-2020 (no G2 books exist there;
  pre-registered in PLAN so the omission is explicit, not hidden).
- Determinism: PB recomputed after the BOOK0 wiring fix below reproduces its book ledger exactly
  (80127 x 2 = 160254 combined rows); dip ledger checksum unchanged (4cbb528faafc0ce6, 9731 rows).
- Full numbers in results.json (32 PB/BOOK0 cells + 16 DIP0 reference cells + checksums).

## Part A - feasibility per G2 book member (read-only probes, tmp/probe.json; span = 2018-01..2020-09)

| member | defining inputs (beyond the v144 price base) | availability 2018-01..2020-09 | verdict |
|---|---|---|---|
| A/Aq (O1 orders) | 6 order-level whale-flow features on the PERP orders table | perp orders start 2020-01-01 (BTC/ETH; BNB 2020-02-10, XRP 2020-01-06): 23-27% of span; 0% for every 2018/2019 anchor's train+test | NOT AVAILABLE (frozen builder). Spot-flow substitution banned by PLAN (venue change) |
| B/Bq (TV+options) | 17 TV features (price-derived) + 5 Deribit options-flow | TV 100%; options BTC 2019-01-01.., ETH 2019-03-21.. (56-64% of span) | BUILDABLE WITH DISCLOSED PARTIAL OPTIONS (frozen v233 recipe run as-is; options NaN where the archive has nothing - HGBR-native, precedented by funding-NaN in the frozen 2017 prefix) |
| D/Dq (premium) | 5 Coinbase-premium features (market-wide, joined on t) | Coinbase 1h from 2017-08-01 (BTC/ETH): ~100% | BUILDABLE (frozen v154/v285 recipe on the spot-stitched panel) |
| base panel | 4h with taker-buy cols (v103 kline-flow), 1d (ribbon), funding | perp 4h starts 2019-09..2020-02 (too late); spot prefix + spot_majors cover 2017-08.. with taker cols; funding NaN pre-2019-09 (HGBR-tolerant) | panel OK (spot venue, disclosed) |

A/Aq carry the deployment's whale-flow edge and cannot be rebuilt frozen for 2018-2019: a full
deployed-G2 replay is IMPOSSIBLE under frozen rules. Part B replays the system MINUS the A family.

## Part B - pre-sample book (walk-forward, frozen recipes, fresh module copies)

Panel: stitched Binance SPOT 4h/1d (prefix for t < 2019-09-01, spot_majors after, dedup; 1d after
the cut resampled from 4h - no spot_1d files exist). Coins BTC/ETH/BNB/XRP (SOL excluded).
B/Bq = v233 TV+options recipe; D/Dq = v154/v285 premium recipe; imports UNCHANGED, only the
panel loader + anchor lists repointed (composition mirrors the frozen glue line-for-line).
Anchors: annual 2018-09-24/2019-09-24; quarterly 2018-03-24..2020-06-24 (v202 rhythm, 10 quarters);
train = everything before A minus frozen embargoes (v92 102 bars / v103 78 bars, all >= 7d).
Coverage: Bq/Dq from 2018-03-24, B/D from 2018-09-24 (4374/5481 rows); missing = 0.0 (frozen
fillna(0) convention). Blend 0.8*o1'+0.2*d' (5481 bars, mean|w| 0.058, mean gross 0.23).

## Part B - engine results (4-phase means; DD = 1m-marked incl. open positions)

| year | DIP0 %/mo (= oc_presample2 G2) | BOOK0 %/mo | PB %/mo | DIP0 DD | BOOK0 DD | PB DD / worst-phase |
|---|---|---|---|---|---|---|
| Y2017 (partial) | 10.71 | 0.00 (no coverage) | 10.71 (= DIP0) | 5.04 / 6.03 | - | 5.04 / 6.03 |
| Y2018 | 2.50 | -0.11 | 2.39 | 8.43 / 9.56 | 14.60 / 14.96 | 15.43 / 18.24 |
| Y2019 | 0.48 | -1.38 | -0.89 (LOSING) | 11.30 / 14.34 | 18.46 / 19.77 | 19.34 / 22.47 |
| Y2020p | 0.27 | 0.35 | 0.53 | 17.52 / 24.53 | 23.22 / 25.43 | 30.81 / 39.34 |

Book activity: 17103/25716/18217 fills (2018/2019/2020p, 4 phases); book exit win rate ~1.4% is
EXITS ONLY (SL/TP events; most exposure is held and marked - do NOT read it as a trade win rate;
the book leg is scored by its standalone equity, BOOK0). Per-phase PB 2019: -1.77/-0.85/+0.24/-1.18
(3 of 4 phases negative while DIP0 is +0.48 on the mean). PB Y2020p worst single phase DD 39.3%.

## Key question

**NO - the deployed design, as far as it can be replayed under frozen rules (B/D-family book,
A-family unavailable, replica-level engine), does NOT make money in years nobody looked at: the
combined book+dip replay prints a losing year (2019, -0.89 %/mo) and DD far above 20% (2020p mean
30.8, worst phase 39.3). The dip sleeve alone stays green in every pre-sample year (reproduced
bit-for-bit); the pre-sample book loses in 2 of 3 years (2018 -0.11, 2019 -1.38 %/mo) and drags the
combination negative. This extends the oc_presamplebook/oc_presampleflow verdicts (IC ~ 0 for every
7d family proxy) to the full-ensemble members: no pre-sample directional skill, costs do the rest.
Scoped honestly: this is evidence against the BOOK transferring, not a gate verdict on deployed G2
(which has the A-members, R2 sizing and grid execution that cannot be replayed pre-2020).**

## Post-hoc disclosures (no frozen choice changed after outcomes)

- BOOK0 wiring bug (found BEFORE finalize through the impossible all-zero Y2020p row while PB
  showed 4500+ fills): run_cells built book targets only for row=="PB", so BOOK0 ran naked
  (flat 1.0). Fixed to row in ("PB","BOOK0"), reran BOOK0+PB; PB book ledger reproduces exactly
  (determinism check above); DIP0/gate untouched. Original buggy BOOK0 cells were never reported.
- Test-authoring fix (before any outcome): the hand-check expectation missed the 08:00 funding
  settlement (synthetic T+4h = 08:00); corrected to include FUND*0.5 - also covers funding logic.
- `train_ic`-style positive controls were not logged per anchor (fits.json has anchors/coverage;
  the loop demonstrably fits: predictions nonzero, blend nnz ~5k/coin).

## Leakage / execution statement

Features: frozen functions on bars <= t only (v92/v103/TV/options/premium imports unchanged;
warm-up masks pre-eligible coins; NaN never forward-filled except the 1m-mark hold inside outage
gaps for DD, inherited from the gated replica). Labels: opens t+1..t+H only (frozen v92/v103
code). Fits: rows with label end < anchor - frozen embargo (cutoffs inside frozen train_predict;
verified by construction - anchors are the only substituted parameter, per PLAN). Fills: strict 1m
trade-through, dip minutes 16..238, book minutes 5..59 (tested: no fill at touch/equality, none in
minutes 0..4, interval truncation to [S,E) tested). Book targets: PB row known at row_t+4h,
joined asof-causal onto phase grids (tested). No test-year statistic enters any choice (weights
0.8/0.2 frozen, blend fallback unused). Tests: tests/test_oc_presampleg2.py, 12 tests - all pass.

## Verdict (tieng Viet, ket luan chinh)

Dip sleeve dung yen lãi tat ca cac nam pre-sample (xanh, DD duoi 20 o muc mean) - nhung book retrain
walk-forward lo 2/3 nam (2019 am 1.38%/thang) keo ca he thong am nam 2019 va DD vuot 20 (2020p 30.8,
1 pha 39.3) - thiet ke trien khai KHONG kiem duoc tien o nhung nam chua ai nhin o muc replica.
Day la bang chung sach rang book khong chuyen sang du lieu moi (khop voi IC ~ 0 cua moi family) -
khong trien khai dua tren pre-sample; huong book dong lai, chi bang dip + prospective log moi xem xet.
Gia dinh A-family (khong rebuild duoc) va engine replica (khong phai stack v421) da duoc khai bao day du.
