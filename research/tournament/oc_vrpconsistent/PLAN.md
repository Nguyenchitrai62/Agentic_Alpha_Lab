# oc_vrpconsistent PLAN (pre-registered 2026-10-07, BEFORE any outcome computed)

Question: oc_vrprobust part A lowered ONLY the sale price (k x DVOL) but kept
marks at 1.05 x DVOL - inconsistent (the SL fires too often). oc_vrprobust part B
measured the TRUE 7-day ATM IV on Fridays 08:00-12:00 / DVOL = 0.868 mean,
0.862 median, p10 0.786, p90 0.941 (61 Fridays). This study re-runs V2 with every
sigma scaled CONSISTENTLY by r = sigma_true / DVOL.

## Frozen rule (V2 copy from oc_vrpstraddle PLAN.md / oc_vrprobust run_robust.py, r-scaled)

- Cycle: every Friday. Entry 08:05 UTC. S = Binance USD-M perp 1m close of minute
  08:04. K = S rounded NEAREST to grid (BTC 1000, ETH 50). Expiry next Friday
  08:00 UTC. T_entry = (7d-5min)/365.
- sigma_true(t) = r x DVOL(t)/100, where DVOL(t) = latest known hourly DVOL
  candle close <= t (same dvol_known helper). Variants scale ALL sigmas:
  * sigma_sell = 0.97 x sigma_true(entry) (bid haircut). Premium/unit = BS
    call+put (r=q=0) at sigma_sell, T_entry.
  * TP/mark sigma = 1.0 x sigma_true(t) (hourly path + buyback).
  * SL check / SL buy-back sigma = 1.05 x sigma_true(t) (ask).
- Fees (base, unchanged): per leg per side min(0.0003 x S_trade, 0.125 x leg).
  Settlement per ITM leg min(0.00015 x S_settle, 0.125 x intrinsic).
- Size: q = 0.5 x f x E / S per coin (f=1 standalone; f of TOTAL equity overlay).
- SL: hourly closes, P&L(t) = opt_cash - q x mark(1.05 x sigma_true) <=
  -1.0 x gross premium -> buy back at BS(1.05 x sigma_true) + fees. No exit
  checks before first hourly close strictly after entry (09:00 Friday).
- TP: 4h closes (checked FIRST on coincidence), mark(1.0 x sigma_true) <=
  0.3 x gross -> buy back + maker fees.
- Else settle at expiry: payoff = -|S_settle - K|, S_settle = mean of 30 1m
  closes 07:30..07:59 Friday + settlement fees.
- BS (r=q=0) identical to vrp.py. V2 has NO hedge, no funding.

## Pre-registered variants (ONLY these three)

- R100: r = 1.0 (= original V2; MUST reproduce oc_vrpstraddle dev4 overlay
  f=0.25 numbers 6.566 / 4.365 / 16.10 and standalone V2 dev4, else stop).
- R087: r = 0.87 (observed 7d-ATM/DVOL median 0.862 / mean 0.868).
- R080: r = 0.80 (observed p10 stress).

## Rows (ONLY these)

- Standalone V2 dev4 (f=1.0, fresh E=1.0 per anchor, boundary weeks skipped).
- G2 overlay (UTA combo A(t)=A(t-1)(1+r_bot)+dSleeve, reset metric) f=0.25 and
  f=0.10, dev4 (yearly R/DD, dev4-mean R geometric, worst year, max yearly DD,
  full-path DD continuous).
- Most recent year 2025-09-24..2026-09-23 scored ONCE, only for R087 f=0.25
  overlay + G2 reference (labelled; the recent year has been seen for r=1.0
  only). No standalone recent, no f=0.10 recent, no R080 recent.
- Gap stress for R087 f=0.25 at its worst minute (same definition as C4: hourly
  step with most negative combined hourly return in dev4 yearly-reset overlay
  f=0.25), g in {-10%,-15%,+10%,+15%} all-coin simultaneous, shocked mark
  BS(S(1+g),K,T,1.5 x sigma_true_asof). First reproduce C4 numbers for r=1.0
  (worst minute 2024-01-03 14:00 UTC, G2_mix_S/G 0.3456/0.3456, combined losses
  5.65/8.74/-2.46/-3.23) to validate the method, then the R087 row. G2 exposure
  by the oc_gapstress build_state method (dip scaled to gross cap 2.0/phase,
  equity-weighted mix), read-only import, no edits.

## G2 baseline

- Reproduce G2 (R2B1D17BFG2, v421_runs.pkl via v388.hourly) yearly R/DD
  [2.588/10.86, 3.282/16.91, 6.045/15.81, 10.677/8.27] + recent [4.648/12.90],
  5y R 5.41 / W 2.588 / DD 16.91, dev4 mean 5.601, and f=0 overlay to the digit
  before any overlay row; else stop and report.

## Selection (W_COMMON, dev4 only)

- Anchors 2021/22/23/24-09-24, each year [A,A+365d). Robust criterion:
  DD <= 20 and no losing dev year; prefer dev4 mean >= 5 %/mo, then highest
  dev4 WORST-year monthly return, ties -> higher mean. Recent year never picks.
- Adopt-worthy as PAPER candidate only if R087 f=0.25 beats G2 on dev4 mean AND
  worst year with DD <= G2+0.5 (<= 17.41) AND R080 overlay f=0.25 loses no more
  than 0.3 pp vs G2 dev4 mean (per assignment).

## Data (as-of only, same files as oc_vrprobust)

- DVOL data/raw/deribit_dvol_20261005, 1m BTC data/raw/btc_intraday_20260924 +
  ETH data/raw/majors_intraday_20260924, hourly grid 2021-09-24 04:00..v388.Y1+12h.
- Gate costs: maker 0.0002, taker 0.00055; no funding (V2 unhedged).
- Strike-IV parquet (B.json) is DESCRIPTIVE input for r only; never enters
  pricing per-bar.

## Leakage checks (to state in REPORT.md)

- Feature timing (DVOL close<=t; S 08:04 known 08:05; marks latest closed DVOL;
  settlement 07:30..07:59 known at 08:00); label windows (payoff post-entry
  only); fit windows (r=0.87/0.80 from pre-existing B.json Fridays mostly
  2021+2023-03+2025-06, NOT refit here; no thresholds on test years); fill
  timing (options at model marks, no book; first event 09:00, nothing fills in
  first 5 min by construction).

## Outputs

- research/tournament/oc_vrpconsistent/{PLAN.md(this),vrp.py,run_consistent.py,
  results.json,REPORT.md,tmp/}; tests/test_oc_vrpconsistent.py (>=1
  causality/truncation test + >=1 hand-checked synthetic BS/fee/r-scaling case;
  pytest -q). Code copied from oc_vrpstraddle(vrp.py,run_vrp.py) +
  oc_vrprobust(run_robust.py); originals never edited.
