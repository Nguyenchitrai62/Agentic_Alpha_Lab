# oc_crash2020 PLAN (pre-registered BEFORE any outcome is computed, 2026-10-06)

## Purpose (labelled stress replay, NOT performance)

Measure the tail behaviour of the G2 dip sleeve through the worst historical
crash windows not covered by oc_stresshist (2021-2026 only): 2020-03-12..13
(COVID), 2020-03-16, 2021-01-21, 2021-05-19, and 2021-06-21.
The dip-sleeve rule parameters are in-sample for 2020-2021 (fitted on later
data); this answers "how bad could the open dip book get in a crash", not
"how much does it earn". No variant is selected here.

## Replica (G2 dip sleeve, isolated, dip-only)

- Coins: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (majors only).
  SOL/BNB/XRP have missing 1m history in early 2020 (SOL starts ~2020-09):
  missing minutes (NaN) never fill, never trigger an exit touch, never count
  as flushing; a fill whose timeout open is NaN is dropped.
- 1m klines: data/raw/btc_intraday_20260924 (BTC),
  data/raw/majors_intraday_20260924 (others).
- 4h grid: bar j of phase s covers [ORIGIN + s h + 4h*j, +4h), ORIGIN =
  2020-01-01 00:00 UTC (midnight-aligned, hence the s=0 grid is identical to
  the oc_dipexit grid from 2020-08-01). Phases s in {0,1,2,3} (the four
  deployed clock phases as 1h offsets). Bar offsets 0..239; next-bar open is
  offset 240.
- sigma_4h per coin per phase at bar j (known at the bar open): simple returns
  r_b = O_b / O_{b-1} - 1 of 4h bar opens; sigma(j) = std(r over 360 bars
  ending at j-1, min_periods 120, ddof=1) = oc_dipexit/v293 definition.
  Bars with non-finite O_j or sigma<=0/NaN are skipped (warm-up: bars before
  ~2020-01-21 have <120 bars and are skipped; all five crash windows have
  full sigma except SOL, which is skipped while its history is missing).
- Rungs k in {2.5, 3.0, 3.5, 4.0, 5.0} (R2 depths). Level lv = O_j*(1-k*sigma).
  Resting limit BUY, live window offsets 16..238. Fill at FIRST f with
  low(f) < lv (STRICT trade-through). Fill price = lv, maker 0.0002.
  At most one fill per (bar, coin, k).
- Correlation count at the fill (B1, v399-exact, causal): n(a,T,f) = number of
  OTHER majors b with finite O_b(T), finite C_b(T+f-1), finite sg_b(T)>0 AND
  C_b(T+f-1) <= O_b(T)*(1-2.5*sg_b(T)) (uses only closes up to minute f-1).
- Sizing (G2 wiring, agents OFF): per-rung notional as a fraction of bar-open
  equity E: w = mult*kd*u, mult = 1/(1+n_fill) (B1), kd = 1.7 (G2 dial),
  u = SIZE*size_mult/4/S_REF = 0.25*1.75/4/1.657 (engine fixed constants;
  v221 size_mult 1.75 via pipe_setup). The learned R2 agent size table is set
  to 1.0 (no walk-forward tables exist for 2020; labelled). Scale s and
  governor g are 1.0 (short window, labelled).
- Risk budget (engine-exact): candidate fills of a bar are processed in
  (f, r, a) order; keep iff risk_open + w*(4*sg+gap) <= 0.442
  (= 0.26*1.7, G2 budget), gap = 0.02; risk_open sums w*(4*sg+gap) of rungs
  still open (exit offset > f). Cut rungs are skipped.
- Arms (2, fixed): G2 = budget + gross cap G=2.0 per phase sub-account
  (room = 2.0 - sum of open notionals; w = min(w, room); skip if room<=1e-12;
  engine sleeve_gross_cap hook); NOCAP = budget only (reference to quantify
  what the cap does; NOT a candidate).
- Post-fill exits (long), oc_dipexit D0 replica from lv:
  sl = lv*(1-4*sg), bl = lv*(1-8*sg), tp = lv*(1+1*sg), evaluated on
  t in f+1..239 then timeout at 240: backstop touch (first low<=bl) exits at
  min(bl,open(t)) taker; else TP touch (first high>tp, STRICT) exits at tp
  maker+mfill; else close5 stop (clock (m+1)%5==0, first close<=sl) exits at
  open(m+1) (or o2 if m=239) taker; else timeout at next-bar open o2 taker +
  funding 0.0001 iff (T+4h).hour in (0,8,16). Priority stop-first (backstop
  wins ties kb<=ks,kt; else TP only if kt<ks; else stop). Same-minute stop+TP
  -> stop. Gate fees: maker 0.0002, taker 0.00055. Ret fractions of lv.

## Windows and equity

- Windows (UTC, 10-day sim each: crash + 7d recovery tail; rungs opened on
  bars with open in [S, S+10d)):
  W1 COVID 2020-03-12, W2 2020-03-16, W3 2021-01-21, W4 2021-05-19,
  W5 2021-06-21 (each S = date 00:00 UTC).
- Each (window, phase, arm) starts with equity 1.0 and no open positions
  (phase sub-account units). Equity compounds per bar on realised exits;
  1m marked equity M(t) = bar-open E * (1 + sum over open rungs
  w*(C(t)/lv-1)) tracks intrabar DD (open rungs marked at close).
- Per (window, phase, arm) report: min marked equity (max intraday loss as %
  of start equity = 100*(1-minM)), max DD from running peak
  (100*max(1-minM/peak)), peak gross notional (max over minutes of sum of
  open fill notionals, start-equity units), fills / stops (close5+backstop) /
  TPs / timeouts, gap-through stops (stop/backstop exit with
  (level-fillpx)/(lv*sg) > 1.0: count + max), worst minute (timestamp of minM),
  end equity, recovery = days from trough to first M >= pre-trough peak
  searched within 7d after the trough and inside the sim, else "never".
- Context row per window-arm: arithmetic mean of the 4 phases per metric
  (the deployed mix holds 1/4 equity per phase).
- Comparison: worst 2021-2026 week from oc_stresshist (G2 2023-12-27..2024-01-03:
  week -12.3%, DD 13.9% on FULL-pipeline year-equity units) vs the dip-sleeve-only
  crash losses here (sub-account units) - labelled as different units; plus
  G2-vs-NOCAP inside the replay. Runbook expectation (DEPLOYMENT_PLAN_VI):
  bad week -8..-12%, DD gate <=20%.

## Protocol / resources

- PLAN.md written before any outcome computation. Scripts: crash.py (pure-numpy
  core: sigma/n/fill/D0-exit/budget/cap + per-coin sequential loop ->
  results.json). Outputs: results.json, REPORT.md (tables + Vietnamese verdict).
- One process, one coin's 1m slice in RAM at a time (float32); only window
  bars are simulated (sigma history read as 4h opens). Peak RAM < 0.4 GB, so
  no heavy_slot needed (MEDIUM tag acknowledged; heavy_slot only if >0.4 GB).
- Tests: tests/test_oc_crash2020.py (synthetic hand checks: strict fill,
  stop-first, funding, budget cut, cap cut, gap-through flag; causality: sigma
  excludes the bar, n uses only closes up to f-1). Run with
  .venv/Scripts/python.exe -m pytest tests/test_oc_crash2020.py -q.
- No commits; no edits outside research/tournament/oc_crash2020/
  (+ tests/test_oc_crash2020.py). Git is read-only.
