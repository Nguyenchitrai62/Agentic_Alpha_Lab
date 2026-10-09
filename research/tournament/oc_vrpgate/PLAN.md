# oc_vrpgate PLAN (pre-registered 2026-10-07, BEFORE any outcome computed)

**POST-HOC INFORMED — LABEL ON EVERY ROW.** The idea comes from seeing V2's
yearly IV-RV gaps in oc_vrpstraddle REPORT.md: +0.097/+0.095 in 2021/2022
(profitable) vs +0.009/+0.012 in 2023/2024 (V2 lost in 2023). The gate
thresholds below (0.05 gap, 1.15 ratio) were picked AFTER seeing those four
numbers, so every result here is POST-HOC INFORMED, not a fresh hypothesis.
The most-recent year has not been used to pick the thresholds.

Question: does selling the weekly straddle ONLY when the ex-ante volatility
premium is high turn the realistic-priced sleeve (consistent r=0.87) into a
clear overlay gain on G2?

## Frozen pricing (from assignment; = oc_vrpconsistent R087)

- V2 1-week naked short ATM straddle, BTC+ETH, every Friday entry 08:05 UTC.
  S = Binance USD-M perp 1m close of minute 08:04. K = S rounded NEAREST to
  grid (BTC 1000, ETH 50). Guard K<=0/non-finite => skip (logged).
- Expiry next Friday 08:00 UTC. T_entry = (7d-5min)/365.
- Consistent scaling r = 0.87 (observed traded 7d-ATM/DVOL median 0.862 /
  mean 0.868, research/tournament/oc_vrprobust/tmp/B.json):
  sigma_sell = 0.97*r*DVOL/100, TP/mark sigma = 1.0*r*DVOL/100,
  SL check/buyback sigma = 1.05*r*DVOL/100. BS (r=q=0) identical to vrp.py.
- Fees base unchanged: per leg per side min(0.0003*S_trade, 0.125*leg);
  settlement per ITM leg min(0.00015*S_settle, 0.125*intrinsic).
- Size q = 0.5*f*E/S per coin (f=1 standalone; f of TOTAL equity overlay).
- SL hourly (first check 09:00 Friday): opt_cash - mark(1.05r) <= -gross =>
  buy back at BS(1.05r)+fees. TP at 4h closes checked FIRST on coincidence:
  mark(1.0r) <= 0.3*gross => buy back + maker fees. Else settle:
  payoff = -|S_settle-K|, S_settle = mean of 30 1m closes 07:30..07:59
  Friday + settlement fees. V2 has NO hedge, no funding.
- Everything else = V2 (oc_vrpstraddle PLAN.md). First reproduce
  oc_vrpconsistent's R087 row (standalone dev4 + overlay f=0.25 dev4) to the
  digit; if the reference file is missing, implement the scaling and state
  that it could not be cross-checked.

## Gate (ex-ante, per coin per Friday, information <= 08:05)

- t_gate = Friday 08:00:00 UTC. DVOL_0800 = dvol_known(t_gate) = close of the
  last hourly DVOL candle with candle-close <= 08:00 (points; /100 decimal).
- RV7 = annualised std of 1m log returns over the 7 days before 08:00:
  1m closes with open_time in [t_gate-7d, t_gate) (10080 bars expected),
  r_i = ln(c[i+1]/c[i]), RV7 = std(r, ddof=1)*sqrt(525600), decimal.
  RV30 likewise over [t_gate-30d, t_gate) (43200 bars), sqrt(525600).
- Both use ONLY bars with open_time < 08:00 Friday (known at 08:00); the gate
  itself is known by 08:05 entry. Coverage rule (frozen): require >=9000
  finite positive closes for RV7, >=38000 for RV30; else that RV = NaN and
  the gate FAILS (no sale — conservative, frozen).
- gap7 = r*DVOL_0800/100 - RV7 (decimals). ratio30 = (r*DVOL_0800/100)/RV30.
- Rows (ONLY these three):
  * R087: ungated V2 at r=0.87 (reference; = consistent R087).
  * G1: sell only if gap7 >= 0.05 (finite; NaN => skip).
  * G2: sell only if ratio30 >= 1.15 (finite, RV30>0; NaN => skip).
- Gate is per coin per Friday: one coin may trade while the other skips.
  Skipped coin-weeks simply do not exist (no premium, no liability, no size).

## Rows computed (ONLY these)

- Standalone sleeve dev4 (f=1.0, fresh E=1.0 per anchor, boundary weeks with
  expiry past year-end skipped, disclosed): R087, G1, G2.
- G2 overlay (UTA combo A(t)=A(t-1)(1+r_bot)+dSleeve, yearly-reset reset
  metric, same v421/carrycompound convention as oc_vrpconsistent) f=0.25
  dev4: R087, G1, G2. Plus f=0.0 validation reproducing G2 to the digit.
- Most-recent year 2025-09-24..2026-09-23 scored ONCE, only for the CHOSEN
  row (robust winner on dev4 overlay, see below) + G2 reference (labelled).
  No standalone recent for losers, no extra thresholds on the recent year.
- Per row report: per-year R/D (reset metric), trades/win/TP/SL/expiry,
  worst week, share of coin-weeks sold (= sold / ungated-tradable universe
  of coin-Fridays with valid price+DVOL), mean gap7 of sold vs skipped
  coin-weeks (where RV7 finite), mean ratio30 sold vs skipped, IV-RV gap
  at entries (sigma_sell vs realised entry->expiry), full-path DD
  (continuous account, max of marked/close) for overlay f=0.25.

## Selection (W_COMMON, dev4 overlay only)

- Anchors 2021/22/23/24-09-24, each year [A,A+365d). Robust criterion on the
  G2-overlay f=0.25 dev4 rows: among R087/G1/G2 with yearly-reset DD<=20
  and no losing dev year, prefer dev4 mean>=5%/mo if any, then highest
  dev4 WORST-year monthly return, ties -> higher mean. Recent year never
  picks. Anything changed after seeing outcomes is a disclosed extra row,
  original kept.
- Adopt-worthy as overlay gain ONLY if the chosen gate beats G2 on dev4
  mean AND dev4 worst year with overlay DD <= G2 dev4 DD+0.5 (per assignment
  verdict: dev4 mean AND worst year above G2, DD <= G2+0.5).

## G2 baseline

- Reproduce G2 (R2B1D17BFG2, v421_runs.pkl via v388.hourly) yearly R/DD
  [2.588/10.86, 3.282/16.91, 6.045/15.81, 10.677/8.27] + recent
  [4.648/12.90], 5y R 5.41 / W 2.588 / DD 16.91, dev4 mean 5.601, and f=0
  overlay to the digit before any overlay row; else stop and report.

## Data (as-of only, same files as oc_vrpconsistent)

- DVOL data/raw/deribit_dvol_20261005, 1m BTC data/raw/btc_intraday_20260924
  + ETH data/raw/majors_intraday_20260924, hourly grid 2021-09-24 04:00..
  v388.Y1+12h. Gate costs: maker 0.0002, taker 0.00055; no funding (V2).
- B.json r=0.87 is DESCRIPTIVE input only; gate thresholds 0.05/1.15 are
  POST-HOC INFORMED (chosen after seeing V2 yearly gaps); no refit here.

## Leakage checks (to state in REPORT.md)

- Feature timing (DVOL close<=t; S 08:04 known 08:05; RV windows end strictly
  before 08:00 Friday; marks latest closed DVOL; settlement 07:30..07:59
  known at 08:00); label windows (payoff post-entry only); fit windows
  (r from pre-existing B.json, thresholds post-hoc from dev years only —
  labelled, never from the recent year); fill timing (options at model
  marks, no book; first event 09:00, nothing fills in first 5 min by
  construction).

## Outputs

- research/tournament/oc_vrpgate/{PLAN.md(this),vrp.py,run_gate.py,
  results.json,REPORT.md,tmp/}; tests/test_oc_vrpgate.py (>=1
  causality/truncation test + >=1 hand-checked synthetic BS/gate case;
  pytest -q). Code copied from oc_vrpstraddle(vrp.py,run_vrp.py) +
  oc_vrpconsistent(run_consistent.py); originals never edited.
