# oc_gexchange PLAN (pre-registered 2026-10-07, BEFORE any outcome)

## Question
Do CHANGES in the dealer-gamma proxy (not levels) predict G2 dip-rung outcomes?
Follows oc_gex REPORT.md suggestion ("test CHANGES"). Reuses oc_gex hourly GEXn
files and its dip-replica join unchanged.

## Write scope
ONLY `research/tournament/oc_gexchange/` + `tests/test_oc_gexchange.py`.
No other edits. Read-only inputs: `research/tournament/oc_gex/gex_hourly_{BTC,ETH}.parquet`,
`research/tournament/oc_gex/gex_lib.py` (import `last_hour_before` unchanged),
`research/tournament/oc_placebo_dip/compute_placebo_dip.py` (dip replica, unchanged).

## Feature dG z (FIXED now, no tuning after)
- Decision time T = rung fill's 4h bar open time bt (bar open, 4h grid).
- Coin mapping (unchanged from oc_gex): BTC series for BTC/SOL/BNB/XRP rungs,
  ETH series for ETH rungs. Sigma comes from the same series as g.
- i0(T) = last full hour strictly before T = index of last hour_end <= T - 1 min
  (via oc_gex `last_hour_before`, 1-minute safety margin; hourly value known at hour end).
- i24(T) = 24 h earlier level = last hour_end <= (hour_end[i0] - 24 h), i.e.
  `searchsorted(hour_end_ns, hour_end_ns[i0] - 24*3600e9, side="right") - 1`.
  On the regular hourly grid this is exactly i0 - 24; the search form is robust to gaps.
- Raw change: d(T) = GEXn[i0] - GEXn[i24]; NaN unless both finite.
- 24 h-change series (hourly, causal): c(h) = GEXn[h] - GEXn[j(h)] with
  j(h) = last hour_end <= hour_end[h] - 24 h (same search form); NaN unless both finite.
- Trailing 90-day std (causal, excludes current): sigma(T) = sample std (ddof=1) of
  c(h) for the 2160 hourly predecessors of i0, i.e. h in [i0-2160, i0-1].
  Implemented as `pd.Series(c).shift(1).rolling(2160, min_periods=720).std(ddof=1)` at i0.
  Requires >= 720 valid c values in the window, else NaN. sigma <= 0 or non-finite -> NaN.
- z(T) = d(T) / sigma(T); NaN if d or sigma missing/non-finite.
- Buckets (fixed): LOW z < -1; MID -1 <= z <= 1; HIGH z > 1; missing excluded (counted).
- Hypothesis direction FIXED NOW: dealers getting SHORTER gamma fast (z < -1)
  -> WORSE rung outcomes / MORE stops. So LOW bucket mean outcome < MID and < HIGH,
  LOW stop rate > MID/HIGH, Spearman(z, outcome) expected POSITIVE.

## Dip screen (dev years 2021-09-24..2025-09-23 for SELECTION; most recent year untouched unless tilt triggers)
- Replica: vendored copy of oc_gex `add_how_column` logic (itself a byte-identical copy of
  `oc_placebo_dip.build_base` + how10 column: D0 outcomes TP1sg/sl4sg-close5/bl8sg/timeout
  next-bar open; maker 0.0002/taker 0.00055; v293 settle funding; B1 sizes w=1/(1+n);
  4 clock phases; majors x R2 rungs 2.5..5; live 16..238 strict trade-through;
  bars open [2021-09-24, 2026-09-24)). MUST reproduce checksum 902c5bbfe8fed3c0 and
  base_sum5y = 7.718304 (4-phase-mean sums [0.911, 0.833, 2.100, 3.197, 0.677] to 3 decimals)
  before any join; else stop and report.
- Join (causal, unchanged timing): each fill's bt -> i0/btc+own series via `last_hour_before`
  (last hour_end <= bt - 1 min); z computed as above from the hourly series only.
  Label rows with z missing as NaN (excluded from buckets/corrs, counted).
- 1) DESCRIPTIVE (dev fills only, per dev year y in 0..3, anchors 2021-09-24..2024-09-24):
  Spearman(z, rung net outcome y10 UNWEIGHTED raw per-rung return; weighted-mean check disclosed
  as secondary), mean y10 by z bucket (LOW/MID/HIGH, unweighted), stop-out rate
  (how10 in {stop, backstop} / filled) by bucket, bucket ns, finite-z fraction.
  Spread_y = mean(y10 | z >= -1) - mean(y10 | z < -1) (non-low minus low, unweighted).
- 2) CANDIDATE RULE (fixed now): tilt is scored IFF in ALL 4 dev years:
  (a) LOW mean outcome < MID mean AND LOW < HIGH mean (hypothesised sign), AND
  (b) spread_y > +0.0005 (+5 bps per rung).
  Spearman sign and stop-rate ordering are reported but NOT gating (single pre-registered rule).
  If the 4/4 + spread condition fails, NO tilt is scored (report descriptive only, no year-5 run).
- 3) CONDITIONAL TILT (only if candidate): single pre-registered variant T1 = rung weight x0.7
  when z < -1, else x1.0 (missing included at x1.0). NO threshold fitting (threshold -1 fixed
  above; no fit window needed). Exposure-matched constant control T1c: uniform multiplier
  c = (total T1 weight)/(total base weight) on the same fills (isolates selection vs leverage).
  Scored with the established dip gate: PROMISING legs (per-year 4-phase-mean
  S_rule >= S_base AND DD_rule <= DD_base + 0.01, >= 4/5 years) PLUS dSum5y >= +0.273
  (labelled 5-year calibration; pooled placebo p95), AND the dev4 view (same legs on
  years 0..3 + dSum_dev4 reported). NO other variants.
- Most recent year (2025-09-24..2026-09-23): scored ONCE, only for T1+T1c+base if the
  candidate triggers; labelled. Never used to choose. If not triggered, no year-5 scoring.
- Costs: replica legs already net of maker/taker + settle funding (same as placebo base).
  No extra cost layer.
- Leakage checks (REPORT): feature timing (hour_end <= bt-1min; i24 24 h earlier; sigma uses
  only h < i0), label windows (outcomes after fill, never in GEX), fit windows (no fitted
  thresholds; threshold -1 fixed pre-outcome), fill timing (replica unchanged).

## Outputs
- `research/tournament/oc_gexchange/{PLAN.md(this), gexchange_lib.py, screen_gexchange_dip.py,
  results.json, REPORT.md (oc_gex style: setup, fidelity, per-year table, verdict), tmp/ scratch only}`.
- `tests/test_oc_gexchange.py`: >=1 causality/truncation test + >=1 hand-checked synthetic case
  (z hand total; bucket edges; sigma-excludes-current; embargo-free threshold test).
  Run `.venv/Scripts/python.exe -m pytest tests/test_oc_gexchange.py -q`.
- REPORT ends with 3-line Vietnamese verdict (adopt / reject / needs prospective evidence).
  If PROMISING say so in BOLD; leader decides on an engine run.
- Progress print >= every 10 min in long scripts.

## Changelog
- 2026-10-07: created BEFORE any dG outcome was computed. Threshold -1, 90-day window,
  2160/720 counts, x0.7 tilt, 5 bps spread rule all fixed here.
