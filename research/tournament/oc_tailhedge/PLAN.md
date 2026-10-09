# oc_tailhedge PLAN (pre-registered 2026-10-07, BEFORE any outcome is computed)

## Question
Does a long-BTC-put tail hedge let a larger dip sleeve (G2K20 = dips x2.0 + G 2.0)
run at the same-or-lower drawdown, moving the return-DD frontier (premium cost <
extra return of G2K20 over G2)? First options study in this repo.

## Pre-registered rows (ONLY these; chosen on dev4 = anchors 2021..2024)
Bases: G2 = `R2B1D17BFG2` in v421/v421_runs.pkl; G2K20 = `G2K20` in v422/v422_runs.pkl.
For m in {0.15, 0.25}, h in {1.0, 2.0}: G2+H(m,h) and G2K20+H(m,h) = 8 hedge rows,
plus G2 and G2K20 alone = 10 rows. No other variants (no fitted parameters).

## Fixed rule (from assignment, ambiguities pinned here)
- Expiries: last Friday of each month, 08:00 UTC, Sep-2021..Sep-2026.
- Roll: on each expiry day, at the first hourly grid hour strictly after 08:05 UTC,
  settle the old put (if any) then buy the earliest expiry E with E - t_entry >= 21 d
  (t_entry = 08:05 that day). S_entry = BTC 1m close of the 08:04 bar.
  K = floor(S_entry*(1-m)/1000)*1000.
- Buy price: BS European put (r=q=0) with sigma_buy = 1.05*iv/100 + skew,
  iv = last 4h bar with (bar+4h) <= t_entry, skew = +0.05 (m=0.15) / +0.10 (m=0.25).
  Fee_buy/unit = min(0.0003*S_entry, 0.125*buy_price).
- Size: units = h * A_mid / S_entry, A_mid = total equity after settlement at that step.
  Premium+fee paid from equity; position value added at mark.
- Hourly marks at grid hour t (first grid hour > event time): BS with
  sigma_mark = 0.95*iv_known(t)/100 + same skew, T = max(E-t,0)/365d in years,
  S = S_close(t) (1m close of minute t-1) for the account path + conservative DD;
  S = S_low(t) (min 1m low over [t-60m, t-1m]) for the optimistic DD view only.
  At T<=0 mark = intrinsic.
- TP: at a grid hour, if per-unit close-mark >= 5 * per-unit buy_price: sell at
  (mark - fee_sell), fee_sell = min(0.0003*S_close(t), 0.125*mark); immediately
  re-buy same m: S_new = S_close(t), expiry = earliest E with E - t >= 21 d,
  sigma_buy from last bar close <= t, units_new = h*A_after_sale/S_new, K refloored.
- Expiry settlement: payoff/unit = max(K - S_settle, 0),
  S_settle = mean of 1m closes 07:30..07:59 on expiry day; settle fee/unit =
  min(0.00015*S_settle, 0.125*intrinsic). Processed together with the roll buy
  at the first grid hour after 08:05 (<=1h accounting shift, labelled).
- Account overlay (UTA): A(t) = A(t-1)*(1+r_bot(t)) + dH(t), r_bot from the stored
  4-phase base mean equity; dH = hedge mark change + sale/settlement proceeds -
  buy costs - fees at t. A uses close marks. Marked paths M_cons (close marks),
  M_opt (low marks): M(t) = A(t-1)*(ms_base(t)/es_base(t-1)) + dH_view(t).
- Per-year reset: equity reset to 1.0 at each anchor; fresh user starts FLAT (no
  spanning put; first buy at next roll). Spanning puts exist only in the continuous
  full-path pass. Open position at data cap is marked to cap (truncation, labelled).
- Metric: reset_metric.year_reset arithmetic per anchor year (R = 100*(A_end^(1/12)-1),
  DD_cons/DD_opt from M_cons/M_opt vs running peak of A). Full-path DD continuous
  from grid start, v421 formula max(marked, close) per view.
- Hedge cost/year = sum(paid: buys+all fees) - sum(received: TP sales net + expiry
  payoffs net) inside the year, in year-start-equity units (= % of starting equity x100).
- Top-5 G2 DD episodes: 5 largest non-overlapping peak-to-trough declines on the G2
  continuous mean MARKED path; per episode report peak/trough dates, G2 DD%, and each
  row's hedge P&L = sum of its dH over (peak, trough], in full-path equity units and
  as % of episode-peak equity.
- Validation gates (stop and report if failed): f-less base reproduces v421_result G2
  (5.41 / W 2.588 / DD 16.91 / full 16.82) AND v422_result G2K20
  (5.874 / W 2.832 / DD 17.79 / full 17.69) to the digit.

## Selection (robust criterion, dev4 only)
Among rows with conservative DD <= 20 and no losing dev year: prefer dev4 mean >= 5 %/mo
(if any); among them pick highest dev4 WORST-year R; ties -> higher mean. Key question
(answered in REPORT): does any G2K20+H row beat G2 on dev4 mean AND have yearly/full
DD <= G2's (conservative)? Most-recent year (2025-09-24..2026-09-23) scored ONCE, only
for the chosen row and G2. No post-hoc rows except disclosed extras (none planned).

## Leakage statement (checked in code, asserted in tests)
IV at t uses only 4h bars with close <= t (searchsorted, side=right on bar-close ns).
S_close(t)/S_low(t) use 1m minutes strictly before t. S_settle uses 07:30-07:59 closes
(known 08:00) applied at first grid hour after 08:05. No fits; all constants fixed above.
Grid capped at 2026-09-24T00:00Z; hourly/1m/IV rows beyond cap are dropped before use.

## Outputs
`analyze_tailhedge.py` (one process, streams one yearly 1m file at a time, no engine
reruns, no GPU), `REPORT.md`, `results.json`, pytest `tests/test_oc_tailhedge.py`
(BS hand-check + IV/side-informed causality + overlay accounting identity).
