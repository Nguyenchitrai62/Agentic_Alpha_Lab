# oc_ideas — 10 new testable ideas (2026-10-05)

Baseline: BOT R2B1D17BF = 4h trend book (pooled HGB) on 4 clock-shifted sub-books
+ dip ladder 2.5–5 sigma_4h below each 4h open, rung size 1/(1+n), dips x1.7,
bear-regime book longs x0.5: 5.43 %/mo, DD 18.3, win 65 %.
Stretch goal: 8 %/mo, DD < 15, win > 60 %.
Ranked by expected value per unit of effort (cheapest rung-level screens first).
Screening convention for all: walk-forward anchor years [A, A+365d),
A = 2021-09-24..2025-09-24; cut-offs/terciles from strictly pre-anchor data;
causal timing stated per idea; costs context ~4–8 bps round-trip.

## 1. Late-fill fast-TP (TP conditioned on fill minute f)
Mechanism: late fills (f ≥ 209, last 30 min) underperform early fills by 10–39 bps
but stay positive on average (oc_filltime) — they arrive into tired moves with less
time to reach TP 1.0 sigma before the bar-end timeout. A faster TP harvests what is
there instead of timing out.
Causal definition: at the fill minute f (known exactly at the fill, bot-executable),
TP = 0.5 sigma if f ≥ 209 else 1.0 sigma; stops/timeout/fees unchanged (v293 replica,
exact y0.5/y1.0 counterfactuals).
Data: fills_U + oc_b1shape fills_n (already in repo), no new data.
Screen cheaply: rung-level, exact paired outcomes (same engine as oc_tpbyn/oc_dipexit):
S = sum(w'·y) with 1/(1+n) weights, equal exposure/year; PROMISING bar = D>0 vs
always-1.0 in ≥4/5 years AND worst-day not worse in ≥4/5 years.
Differs from closest tried: oc_tpbyn tested TP 1.5 conditioned on flush count n
(rejected 3/5); oc_dipexit tested unconditional exits incl. split-TP (0/5) and
TP1+120min (1/5); oc_filltime documented the LATE drag but never tested a
TP×lateness interaction. This is the untested interaction cell.
Expected: return +0.1–0.3 pp/mo, DD −0.2–0.8 pp (cuts timeout bleed, keeps early-fill
upside); near-zero implementation cost.

## 2. Per-coin dip stop distance (XRP wider, rest standard)
Mechanism: oc_ddanat17: 17/20 worst rungs are full-size (n=0) single-coin XRP
stop-outs; SOL drove the FTX cascade. One global 4-sigma close-stop cannot fit both
a whipsaw coin and a trending one.
Causal definition: close-stop distance per coin set walk-forward (e.g. XRP 5–6 sigma,
BTC/ETH/SOL/BNB 4 sigma; one pre-registered pair only), 8-sigma native backstop
unchanged; stop evaluated on 5m-block CLOSE exactly as v266 B1, exit next minute open.
Data: majors 1m (data/raw/majors_intraday_20260924, btc_intraday_20260924), in repo.
Screen cheaply: rung-level replica (oc_dipexit harness) with per-coin stop leg;
yearly sums + worst-day/maxDD per year vs uniform B1.
Differs from closest tried: v264–v277 explored stop distance GLOBALLY (4-sigma M1 kept);
oc_idiocap capped SIZE on idiosyncratic (n=0, x4>−1, x0<−4) rungs (fired 0.5%, rejected).
This changes DISTANCE per coin (keeps exposure, trims the tail where stops
concentrate), neither a global distance nor a size cap.
Expected: return −0.1–+0.1 pp/mo, DD −0.5–1.5 pp (tail trim, not edge).

## 3. Pre-bar intraday-RV skip (don't place dips into an ongoing flush)
Mechanism: if minutes 0–15 already printed most of the bar's range, the resting bids
at 2.5–5 sigma are chasing a live cascade; fills cluster at the worst adverse-selection
point. Skipping the bar avoids buying the middle of the waterfall.
Causal definition: at minute 15 (before first fill at 16), RV15 = high(0..15)−low(0..15)
divided by 60d sigma_4h at T; skip ALL dips of bar T if RV15 > walk-forward threshold
(single value, e.g. prior-year 80th pct, fitted pre-anchor only).
Data: majors 1m only, in repo.
Screen cheaply: rung-level — drop fills with T flagged, recompute equal-exposure sums
and worst-day/maxDD vs full ladder (same screen as oc_macro skip simulation).
Differs from closest tried: v254 moved ladder SPACING by 1m RV (much worse: bought
ordinary pullbacks closer); v255 shifted start minute 5/10 (neutral). This does the
opposite of v254 — it buys NOTHING when RV already exploded, a skip not a spacing.
Expected: return −0.2–0.0 pp/mo (gives up some V-recoveries), DD −0.5–1.5 pp; filter,
not a stream.

## 4. Funding-surprise dip filter (actual minus predicted, not level)
Mechanism: funding LEVEL is a slow regime (non-stationary; oc_fundregime terciles
degenerate, dip_funding quintiles flip sign). The SURPRISE (settled minus the
predicted rate known pre-settlement) is an event: a large positive surprise = longs
more crowded than priced = flush more likely to extend past the bids.
Causal definition: at bar open T, surprise = last settled funding − last predicted
funding published before that settlement (both from data/raw/binance_premium_20260928,
settlement strictly < T); skip/scale-down (x0.5) dip bids in the coin when surprise
> walk-forward 80th pct (pre-anchor fit, per-coin).
Data: binance_premium_20260928 funding + premium (2020-01+, in repo).
Screen cheaply: rung-level skip simulation per year (S_full vs S_skip, worst-day check,
same table as oc_macro); needs ≥4/5 years with retention ≥95% AND tail improvement.
Differs from closest tried: v231 V2/V3 put predicted-funding LEVEL inside member A
(worse); dip_funding sorted outcomes by predicted LEVEL (sign flips); oc_fundregime
used 7d mean LEVEL (Hi bucket empty 3/5 years). Surprise is an event, not a level —
orthogonal by construction (level partialled out).
Expected: return −0.1–+0.1 pp/mo, DD −0.3–1.0 pp; small, honest DD buy if any.

## 5. Premium-gated book flips (veto reversals into dislocated tape)
Mechanism: member D works because Coinbase premium carries information (v285). The
unexploited use is execution, not weight: flipping the book short into a deeply
negative Coinbase-minus-Binance dislocation (or long into a positive one) is selling
the flush bottom — delay the flip one bar instead.
Causal definition: at 4h close T with a book sign flip signal, compute premium_z =
(Coinbase spot − Binance perp, 1h mean before T, z-scored vs trailing 90d, strictly
<T); if flip direction is INTO the dislocation (|z|>2 against the new leg), hold
prior weights one more bar (single pre-registered threshold, max 1-bar delay).
Data: data/raw/coinbase_20260925 (+ coinbase_alts_20260930) and Binance 1m, in repo.
Screen cheaply: vectorised book open-to-open replay (oc_bookvol harness:
pn[t] = ws·r − 0.0005·TO) base vs gated; per-year net/DD/Sharpe + LOYO.
Differs from closest tried: v285 adds premium as a 20% ensemble MEMBER (weight);
oc_premfill (running) studies premium level AT THE FILL for dip outcomes.
This is a bar-open BOOK execution gate (veto, no weight change) — different layer,
different decision, different timing.
Expected: return +0.0–0.2 pp/mo, DD −0.3–1.0 pp (fewer flip-whipsaws in W1/W3-type
windows); turnover falls.

## 6. Basis-momentum dip throttle (change in quarterly basis, not level)
Mechanism: oc_qbasis killed the LEVEL hypothesis (high basis → BETTER book longs,
wrong-way sign 5/5). The economic object for crash risk is the CHANGE: a fast basis
collapse = de-leveraging impulse; dips bought into it face follow-through.
Causal definition: at T, mom = BTC front-quarterly annualised basis(T) − basis(T−24h),
basis from 4h delivery closes strictly < T (data/raw/qbasis_20261003, BTC/ETH 2020+);
if mom < walk-forward 20th pct (pre-anchor only), dip bids x0.5 that bar (market-wide,
all 5 coins).
Data: qbasis_20261003 BTC/ETH legs (2020-09+, in repo); SOL leg too short, unused.
Screen cheaply: rung-level rescale (same harness as v254 re-screen): equal-exposure
sums + worst-day/maxDD per year vs unthrottled.
Differs from closest tried: oc_qbasis terciles on basis LEVEL/z90 (FAIL, sign flips
or wrong way); v351 QB1 basis member + v352 one-way control (DD 22.9/20.6, no transfer).
Momentum (impulse) vs level (stock) — the level result does not pre-judge the change.
Expected: return −0.2–0.0 pp/mo, DD −0.5–1.5 pp; a throttle, screened DD-first.

## 7. VRP-regime dip BUDGET dial (not per-rung sizing)
Mechanism: oc_dvol found dvol_z90/vrp IC positive 5/5 (fear → better fills) — but
v414 tilted per-rung SIZE by DVOL and got more return with more DD (rejected). The
clean use of a fear gauge is the opposite layer: the SLEEVE BUDGET (market-wide
exposure), raised when compensation is high and cut when it is not, with DD-first
acceptance.
Causal definition: at T, BTC VRP = 90d z of (DVOL −  30d realised) from
data/raw/deribit_dvol_20261005 + 1m realised, strictly < T; sleeve budget for bar T
= base × {1.25 if VRP > pre-anchor q67, 0.75 if < q33, else 1.0} (single
pre-registered triple).
Data: deribit_dvol_20261005 (2021-04+, in repo; warm-up ends before year 1) + 1m.
Screen cheaply: rung-level budget rescale with equal-exposure renormalisation +
engine spot-check for path effects (budget path matters; rung screen is the cheap gate).
Differs from closest tried: v414 = per-RUNG size tilt by DVOL (risk into fear, DD up);
oc_corrbudget = uniform 1/(1+c) daily scaler (retention 0.54–0.62, rejected).
Budget dial by VRP (compensation) ≠ size tilt by DVOL level ≠ correlation scaler.
Expected: return +0.0–0.3 pp/mo, DD −0.5–1.0 pp if the compensation story holds;
reject on DD first.

## 8. Dominance-momentum dip throttle (alt-capitulation flow, not level)
Mechanism: oc_dombook level tilt added return every year but deepened DD in 2021/2024
(extra size met the worst slides); oc_ethbtc dom30 level is fragile (rests on +0.02
bps/bar 2021, LOO fails the most recent year). The tradable object is FLOW: when BTC
dominance is SURGING (alts in capitulation), alt-dip bids catch falling knives; when
stable, the ladder is safe.
Causal definition: at T, ddom = dom30(T) − dom30(T−7d), dom30 = BTC 30d log-ret minus
equal-weight majors 30d log-ret (opens only, causal, full history from 2017 as in
oc_dombook fix); if ddom > pre-anchor 67th pct, alt (ETH/SOL/BNB/XRP) dip bids x0.5
that bar, BTC unchanged.
Data: opens only (v154 4h opens / spot_majors_20260925), in repo; no new data.
Screen cheaply: rung-level rescale, alt-vs-BTC split reported (per-coin sums as in
v229 alt diagnostics); equal exposure; worst-day/maxDD.
Differs from closest tried: oc_dombook scaled the BOOK by dom LEVEL terciles
(×1.25/×0.75, DD gate FAIL); oc_ethbtc sorted outcomes by LEVEL. Momentum (flow)
vs level (stock); applied to ALT DIPS, not the book.
Expected: return −0.1–+0.2 pp/mo, DD −0.3–1.0 pp (FTX-type alt cascades throttled).

## 9. US-equity overnight-gap book tilt (single risk-appetite dial)
Mechanism: crypto book drawdowns cluster in global risk-off (W1/W3-type windows);
the macro PANEL dilutes (v157, v290-F) and event blackouts cut profit without tail
gain (oc_macro 0/5). A single causal overnight gap (SPX close→open / prior-day return
known before the 4h bar) is a slow risk dial, not a member, not a blackout.
Causal definition: at T (00:00/04:00/08:00 UTC grid), gap = SPX prior session
log-return (daily close strictly < T); book target × {0.75 if gap < pre-anchor 25th
pct, 1.0 otherwise} (single pre-registered rule; no scaling up).
Data: free Yahoo ^GSPC daily (10y+, ≥4y requirement met; NOT in data/raw — fetch +
manifest like newinfo_20261005); maps to macro_20260924/xasset convention.
Screen cheaply: vectorised book replay (oc_bookvol harness) base vs tilted; per-year
ret/DD/Sharpe + LOYO; turnover row.
Differs from closest tried: v157/v290-F = broad macro FEATURE PANEL as ensemble member
(dilutes: 1.91/18.4); oc_macro = FOMC/CPI/NFP window SKIP (never improves worst day,
cuts sums up to 64%). One overnight risk dial (downside-only, no skip, no member).
Expected: return −0.2–0.0 pp/mo, DD −0.5–1.5 pp; buys DD with return, screened strictly.

## 10. 1h-confirmation filter on 4h dip bids (fewer trades, not more)
Mechanism: the hourly LADDER as an independent stream failed 3× (v229/v275/v413:
DD 30–44) — more trades into faster noise. The opposite direction is untested: use
the 1h timeframe as a FILTER on the 4h ladder (same bids, fewer of them), requiring
the flush to be visible intraday before buying the 4h dislocation.
Causal definition: at T, for coin c, 1h-state = (open_T − min low of prior six 1h
bars)/sigma_4h(T), 1h bars strictly < T; place coin c's 4h rung bids only if
1h-state > 1.0 (flush confirmed intraday); else skip coin-bar.
Data: majors 1m aggregated to 1h (or spot_majors_20260925 1h prefix), in repo.
Screen cheaply: rung-level filter (drop fills failing the gate, equal exposure);
report kept-share + per-year sums + worst-day (same table as idea 3).
Differs from closest tried: v229/v275/v413 ran the hourly ladder as an EXTRA STREAM
(more rungs, DD 42–44, "closed for good"); v349 hour-of-day multiplier (DD 22,
rejected). A gate that REMOVES 4h bids ≠ a second ladder that ADDS hourly bids.
Expected: return −0.3–+0.1 pp/mo (fewer fills), DD −0.5–1.5 pp, win rate up 1–3 pp
(slow-bleed bids removed); only interesting if DD falls with retention ≥90%.
