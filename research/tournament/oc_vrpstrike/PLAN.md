# oc_vrpstrike PLAN (pre-registered 2026-10-07, BEFORE any outcome computed)

Question: does the weekly short-ATM-straddle edge survive when the premium is
priced from REAL Deribit traded prices of the actual strike (instead of
0.97 x DVOL, which oc_vrprobust/B.json showed overstates the 7d premium by
~11%, median traded-7d-ATM/DVOL 0.862)? Single frozen variant STRIKE-V2
(V2-unhedged mechanics, traded-IV pricing). No selection between variants.

## Fixed rule (from OPENCODE_W_oc_vrpstrike.md, no discretion)

- Coin-weeks: every Friday F. Expiry = NEXT Friday (F+7d) 08:00 UTC.
  Candidate set = instruments of that coin with expiry date == (F+7d).date().
- Strike K*: strike minimising |K - index08| over that expiry's instruments;
  ties -> lower strike. Call leg = (K*,C), put leg = (K*,P) at that expiry.
- index08 = median `vwap_index` over ALL rows of that coin with
  hour == F 08:00 UTC. If none, nearest hour (any row of that coin) to
  F 08:00, ties -> earlier hour; that hour's median vwap_index.
- Entry IV per leg: amount-weighted `vwap_iv` of that EXACT instrument over
  the 3 hourly buckets F 08:00, 09:00, 10:00 (window 08:00-10:59):
  sum(vwap_iv*sum_amount)/sum(sum_amount). If sum(sum_amount) < 0.1 coin for
  EITHER leg -> skip the coin-week (counted as signal-skip `low-volume`).
- S_entry = Binance USD-M perp 1m close of the 10:59 bar (known at 11:00;
  label: a bot sells inside 08:00-10:59, priced at the window end —
  conservative vs mid-window). T_entry = (expiry_08:00 - F 11:00)/365d.
  SELL premium per leg = BS(S_entry,K*,T_entry,(iv_entry-h)/100), h = 0.5
  vol points BTC, 1.0 ETH. iv_entry-h <= 0 or non-finite -> intrinsic
  (same BS guard as vrp.py). This replaces 0.97 x DVOL.
- Marks (V2-unhedged, no hedge leg, no funding): hourly SL checks, 4h-close TP.
  Mark time t runs on hourly closes; first check = first hourly close
  strictly after entry = F 12:00. TP checked FIRST at 4h closes (subset).
  - sigma(t) per leg = last traded `vwap_iv` of the SAME instrument over
    hourly buckets H with H+1h <= t (bucket known at its close; strictly
    as-of), amount-weighted within the bucket (single row normally).
  - SL check + SL buyback at ASK: sigma_ask = (last_iv + h)/100.
  - TP check + TP buyback at MID: sigma_mid = last_iv/100.
  - Fallback: if that instrument has NO traded bucket with
    t-24h <= H+1h <= t -> sigma from DVOL: r_leg x DVOL_known(t)/100, where
    r_leg = iv_entry_leg / DVOL_entry (DVOL_entry = latest known DVOL candle
    close <= F 11:00, strictly as-of; r_leg per leg, fixed at entry, no
    refit), SL ask adds +h/100 on top, TP/mid uses it directly.
  - Underlying px at marks: Binance 1m close of the prior minute (hourly
    close = :59 bar, same convention as run_vrp.py); T(t) = (expiry-t)/365d.
- Exits (exactly V2 economics): SL if P&L_ask(t) <= -1.0 x gross premium
  received (gross = call_prem+put_prem, pre-fee); TP if straddle_mid(t) <=
  0.3 x gross. SL buyback at ask + per-leg fees at triggering close px;
  TP buyback at mid + per-leg maker fees. Otherwise settle at expiry:
  payoff = -(|S_settle-K*|) with S_settle = mean of 30 1m closes
  07:30..07:59 expiry Friday (known at 08:00); per-leg settlement fees if ITM.
  Fees: entry/side min(0.0003*S_trade, 0.125*leg_price);
  settlement min(0.00015*S_settle, 0.125*intrinsic). Size: q = 0.5*f*E/S_entry
  per coin (f=1 standalone; f=0.25 overlay of TOTAL equity, UTA convention
  A(t)=A(t-1)*(1+r_bot(t))+dSleeve(t) per oc_carrycompound).
  Stop-first if both touch in one bar (TP checked first only at 4h closes
  per V2; at non-4h hours only SL exists — same as V2 code path).
- VARIANT REGISTERED (only one): STRIKE-V2. Reference: G2 R2B1D17BFG2 f=0 must
  reproduce v421_result.json yearly R/DD + R/W/DD + full_path_dd to the digit
  before any overlay; else stop and report. No robust-criterion selection
  (single variant); verdict bar per assignment: overlay beats G2 on dev4 mean
  AND worst year with DD <= G2+0.5 (all PARTIAL-labelled, see below).

## Data (as-of only, complete months strictly from manifests)

- Strike trades: `data/raw/deribit_strike_20261007/{BTC,ETH}/*.parquet`
  (forward) + `data/raw/deribit_strike_20261007_b/{BTC,ETH}/*.parquet`
  (backward). COMPLETE month = listed in that folder/coin's manifest.json
  (BTC-forward: files[] list; ETH-forward/ETH-backward: months[] entries with
  complete:true; BTC-backward: files[] list). Disk files NOT in the manifest
  are NOT used (fetchers still running; e.g. ETH-forward disk has 25 files
  but manifest lists only 2021-06, 2023-03, 2025-06 as complete).
- Overlap check: any calendar month present complete in BOTH folders for one
  coin -> compare row count + sha256 (+ full-frame equality if sizes match);
  use one copy; log in STATUS.md. (No overlap in the current manifests.)
- DVOL: `data/raw/deribit_dvol_20261005/{BTC,ETH}_*.json` hourly, known at
  candle close (same `dvol_known` truncation as run_vrp.py). Underlying:
  Binance 1m `data/raw/btc_intraday_20260924` (BTC) +
  `data/raw/majors_intraday_20260924/{ETH}USDT_1m_*` (ETH).
- Hourly grid 2021-09-24 04:00 .. v388.Y1+12h (same as oc_vrpstraddle).

## Years: COMPLETE vs PARTIAL (pre-registered)

- Anchor years: dev4 2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24
  ([A,A+365d)); recent 2025-09-24..2026-09-23 scored ONCE, only for STRIKE-V2
  (+ G2 ref), never for selection (no selection exists here).
- COMPLETE year: every calendar month touched by any [entry F 08:00, expiry
  F+7d 08:00] window with F in [A,A+365d) is complete for BOTH coins.
- PARTIAL year (expected for all 5 now): identical yearly-reset account
  (fresh 1.0 at anchor, boundary weeks with expiry > year-end skipped,
  q sized off account at entry, compounding intra-year), but only TRADEABLE
  coin-weeks are entered: entry month AND expiry month both complete for
  that coin. Non-tradeable coin-weeks are skipped with reason `data-gap`
  (distinct from signal-skips `low-volume`/no-vol/no-price). Metrics use the
  same formulas (geometric %/mo, hourly-marked DD, worst week, SL/TP/expiry
  counts); every table labelled PARTIAL with months used. This equals monthly
  chaining with dSleeve=0 in missing months; a per-complete-month chained-R
  diagnostic row is also reported.
- Standalone rows: f=1 per anchor year (PARTIAL or COMPLETE per above).
  Overlay rows: G2 f=0.25 per anchor year (same convention; f=0 asserts G2).
  Full-path DD: continuous account over the full grid (sleeve close-marked;
  DD lower bound, labelled) for sleeve-only + G2_f0.25 + G2 alone.

## Diagnostics per year (pre-registered)

- Entry iv/DVOL ratio distribution per coin (median/mean/p10/p90 of
  iv_entry_leg/DVOL_entry pooled legs; cf. B.json 0.87).
- Skipped coin-week shares: data-gap vs low-volume/no-vol/no-price.
- Premium % of S: (call_prem+put_prem)/S_entry per coin-week (median/mean).
- IV - realised: iv_entry (amount-weighted straddle avg per coin-week) minus
  7d realised vol (1m log-returns entry->expiry, annualised); mean + SL/TP/
  expiry counts + worst week + P&L split N/A (no hedge leg in V2).

## Leakage checks (to state in REPORT.md)

feature timing (strike buckets known at H+1h; index08/entry-IV known at
11:00; S_entry 10:59 known at 11:00; marks use last bucket with H+1h<=t;
DVOL candle known at close; settlement 07:30..07:59 known at 08:00; first
exit check 12:00 so nothing fills in the first 5 min); label windows
(payoff/marks use only post-entry data); fit windows (r_leg fixed at entry
from entry-time values only; K* from as-of index; NO fits/thresholds on any
test year); fill timing (options at model marks + Deribit-style fees, no
book — haircut h stands in for half-spread + margin, labelled).

## Outputs

research/tournament/oc_vrpstrike/{PLAN.md (this file), STATUS.md,
vrpstrike.py, run_strike.py, results.json, REPORT.md, trades_*.parquet,
tmp/}; tests/test_oc_vrpstrike.py (>=1 causality/truncation test + >=1
hand-checked synthetic BS/fee/skip case; pytest -q). G2 numbers reproduced
to the digit or stop-and-report. Run first on what is complete now; STATUS.md
lists the months used; leader re-dispatches to extend when fetch finishes.
