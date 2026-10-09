# audit_amihud PLAN (pre-registered BEFORE any engine run, 2026-10-07)

Assignment: `docs/opencode/OPENCODE_W_audit_amihud.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
+ `docs/opencode/OPENCODE_W_TEMPLATE_BOOKGATE_20261007.md` + IDEAS4 §C item H4 (variant A1 only)
+ `research/tournament/oc_lit_xs/PLAN.md` (spec only; code/REPORT/results/tmp NOT opened).
Write ONLY `research/tournament/audit_amihud/` + `tests/test_audit_amihud.py`.

## Hypothesis (fixed)

- H4: illiquid majors earn more (Amihud XS). Blind replication of variant A1 only.
- No other variant (no A2/A3/X1/X2/X3, no control rows). If A1 needs a control for
  interpretation it is added as a disclosed extra row AFTER part A, never before.

## Data (fixed, no fetching)

- Daily source (stated): `data/raw/xs_universe_20260924/<SYM>_1d.parquet` for
  SYM in BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT, columns `open_time`
  (day open midnight UTC), `close`, `quote_volume` (USD), `close_time`.
  Volume source (stated): `quote_volume` only. No other volume column is used.
- Spans (from PLAN.md, verified without outcomes 2026-10-07): BTC from 2019-09-09,
  ETH 2019-11-28, XRP 2020-01-07, BNB 2020-02-11, SOL 2020-09-15, all through
  2026-09-23. Trailing 30d windows fully covered for every anchor year.
- No fits on test years. No calendar input.

## Signal definitions (fixed, causal, PLAN.md exact)

Daily frame per coin indexed by calendar day D = open_time normalized to midnight UTC:
- `r_d = close_d / close_{d-1} - 1` (NaN if either close missing/non-finite).
- `amihud_d = |r_d| / quote_volume_d` (NaN if quote_volume missing / <= 0 / non-finite,
  or r_d NaN).
- `Amihud30(D) = mean(amihud_d over D-29..D)` inclusive, require >= 20 non-NaN else NaN.

Decision-time mapping (strict, no lookahead):
- For a 4h decision time T (standard-book index timestamp), the last fully closed
  daily bar is `D*(T) = date(T) - 1 day`, i.e. day D usable iff D+1 00:00 UTC <= T.
  At T = D+1 00:00 exactly the day just closed is usable. Raw at T uses only days
  <= D*(T). Equivalently `D*(T) = floor(T - 1 day, 'D') = floor(T).normalize() - 1 day`.
- Cross-sectional z at T (raw = Amihud30):
  `z_sym = (x_sym - mean(x over finite syms)) / std(ddof=1 over finite syms)`;
  if < 2 finite syms or std == 0 / non-finite, all z = 0 for finite raws;
  NaN raw -> NaN z -> multiplier 1.
- Cross-sectional moments use only the 5 raws at the same T (no trailing fit,
  no full-sample rank).

## Book-gate mechanism (fixed, v426 copy)

- Base = G2 (`R2B1D17BFG2` in v421: rule inv, k 1.0, kd 1.7, bear True, G 2.0).
- Mechanism copied from `research/parallel/rounds/parallel-20260906-r2/v426/v426_book_brake.py`:
  multiplier on STANDARD book rows after the bear filter (BTC 4h open <
  1200-bar mean -> longs x0.5, same as v426) and before the shifted-clock forward
  fill. Rows before 2021-09-24 are not tilted (v426 convention).
- Multiplier clipped to [0.5, 1.5]; NaN z -> 1.0.
- Pre-registered row (ONLY this one + G2 reference):
  - A1 (H4 both-legs): every non-zero bear-filtered weight w -> w * (1 + 0.25 * z_illiq),
    clipped. Illiquid coins get larger absolute weight on both sides.
- Harness, costs, fills, reset metric, full-path DD exactly as v426/v421
  (gate costs: maker 0.0002, taker 0.00055, longs pay 0.0001 per 8h settlement
  00/08/16 UTC, shorts nothing; limit fills only on 1m trade-through, no fill in
  first 5 min after a 4h close (`win_start=5`); stop-first in same 1m bar).

## Reproduction gate (stop if failed)

- Reproduce G2 exactly from `v421/v421_runs.pkl` + `v421_result.json` via
  `reset_metric.year_reset` + `v388.mix` full-path DD:
  5.41 %/mo, W 2.588, max yearly DD 16.91, full-path DD 16.82, yearly rows
  (2.588/10.86, 3.282/16.91, 6.045/15.81, 10.677/8.27, 4.648/12.9).
  Else STOP, no overlay. The engine harness must also re-run G2 to the same
  triple before any variant comparison is valid.

## Engine rows and metrics (fixed)

- Rows: G2 (engine re-run), A1 (engine). 4 phases (shift 0/1/2/3h), live
  2021-09-24 .. 2026-09-23 (dev4 anchors 2021-2024 + most-recent-year anchor 2025
  as a labelled byproduct; the last year is never a selection input here).
- Per-year 4-phase reset R (%/mo geometric) + yearly DD via `reset_metric.year_reset`;
  dev4 mean = geometric mean of the 4 dev-year R; dev4 worst = min dev-year R;
  dev4 maxDD = max dev-year DD; 5y R/W/DD likewise; full-path DD via `v388.mix`
  from 2021-09-24 (max of marked/close convention as in v426 main).
- Part A `replication.json` (per-year R/DD for A1, dev4 mean/worst/DD, 5y and
  full-path DD, plus the G2 reproduction block) is written BEFORE opening anything
  of oc_lit_xs beyond PLAN.md.

## Leakage checks (pre-registered)

- Feature timing: daily close_time < T enforced by D*(T); sampled-T truncation test
  must leave multipliers unchanged; ±1s boundary test exposes exactly the prior day.
- Label windows: none fitted (engine uses realised 1m path).
- Fit windows: no fits; cross-sectional mean/std at same T only; thresholds (30d,
  0.25, clip) fixed here.
- Fill timing: engine `win_start=5` + 1m trade-through + stop-first (v426 harness,
  G2 bit-exact). Tests assert these constants in the engine script.

## Deliverables

- `research/tournament/audit_amihud/`: PLAN.md (this file), `amihud_signal.py`
  (daily raws + XS z + A1 multipliers), `compute_a1_engine.py` (G2+A1 4-phase engine
  via heavy_slot), `replication.json` (part A, before unblinding), `COMPARISON.md`
  (PASS/FAIL/PASS-WITH-NOTES vs oc_lit_xs REPORT/results + code look-ahead audit,
  thresholds R > 0.10 pp, DD > 0.5 pp, Vietnamese 3 lines).
- `tests/test_audit_amihud.py`: >=1 causality/truncation test + >=1 hand-checked
  synthetic case + engine-constant tests; run
  `.venv/Scripts/python.exe -m pytest tests/test_audit_amihud.py -q`.
- Blind log: this PLAN + signal + engine were written without opening
  oc_lit_xs's code, REPORT.md, results, engine_results, engine_runs.pkl, xs_signal.py,
  compute_xs_engine.py, tmp/, nor research/tournament/oc_amihudrobust/.

## Post-hoc log

- Outcome 2026-10-07: G2 reproduced to the digit from cache AND re-ran bit-exact
  through the harness (5.41 / W 2.588 / DD 16.91 / full 16.82; yearly
  2.588/10.86, 3.282/16.91, 6.045/15.81, 10.677/8.27, 4.648/12.9).
  A1 (blind): per-year 2.798/12.21, 3.395/16.81, 6.390/15.77, 10.987/8.42;
  dev4 5.844 / worst 2.798 / DD 16.81; Y4 (labelled once) 4.750/11.14;
  5y 5.624 / full-path DD 16.66. `replication.json` written BEFORE unblinding.
  No definition was changed after seeing any outcome (two test-only fixes
  post-unblinding: assertion direction/scale in the volume-source test and the
  ffill order anchor in the engine-constant test; no signal/engine change).
