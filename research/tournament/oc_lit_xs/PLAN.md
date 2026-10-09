# oc_lit_xs PLAN (pre-registered BEFORE any engine run, 2026-10-07)

Assignment: `docs/opencode/OPENCODE_W_oc_lit_xs.md` + `docs/opencode/OPENCODE_W_COMMON_20261007.md`
+ `docs/opencode/OPENCODE_W_TEMPLATE_BOOKGATE_20261007.md`.
Ideas H4 (Amihud illiquidity tilt) + H5 (MAX/lottery tilt, crypto sign, incl. X3 falsification leg)
from `docs/opencode/IDEAS4_20261007.md` section C.
Write ONLY `research/tournament/oc_lit_xs/` + `tests/test_oc_lit_xs.py`.

## Hypothesis (fixed here)

- H4: illiquid majors earn more (Amihud XS). With 5 majors the spread is thin
  (prior 8%, veto-forms already failed), but a cross-sectional weight tilt was
  never engine-tested.
- H5: high-MAX majors earn MORE (crypto sign reversed vs stocks, Ozdamar).
  5-coin XS is underpowered (prior 7%), X3 (stock sign: underweight high-MAX)
  is the falsification leg expected to lose; included so a win means something.

## Data (fixed, no fetching, coverage verified 2026-10-07 without outcomes)

- Source: `data/raw/xs_universe_20260924/<SYM>_1d.parquet` for
  SYM in BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT (perp 1d klines with
  `open_time`, `close`, `quote_volume`, `close_time`).
  Spans: BTC 2019-09-09.., ETH 2019-11-28.., XRP 2020-01-07.., BNB 2020-02-11..,
  SOL 2020-09-15.., all through 2026-09-23. So 2021-09-24..2025-09-23 plus the
  30d/21d trailing windows are fully covered for every anchor. No fallback
  needed (fallback rule kept: unknown/NaN raw -> z NaN -> multiplier 1).
- No other inputs. No fits on test years. Calendar: none (not a calendar gate).

## Signal definitions (fixed, causal)

Daily frame per coin indexed by calendar day D (open midnight UTC):
- `r_d = close_d / close_{d-1} - 1` (simple daily return; NaN if either close missing).
- `amihud_d = |r_d| / quote_volume_d` (quote_volume in USD; NaN if quote_volume
  missing/non-positive/non-finite). Scale cancels in the XS z.
- `Amihud30(D) = mean(amihud_d over D-29..D)` (30 calendar days ending at D
  inclusive; require >= 20 non-NaN else NaN).
- `Size30(D) = mean(quote_volume_d over D-29..D)` (require >= 20 else NaN; A3 only).
- `MAX21(D) = max(r_d over D-20..D)` (21 calendar days ending at D inclusive;
  require >= 15 non-NaN else NaN).

Decision-time mapping (strict, no lookahead):
- For a 4h decision time T (standard-book index timestamp), the last fully
  closed daily bar is `D*(T) = date(T) - 1 day` (day D usable iff D+1 00:00 <= T;
  at T = D+1 00:00 exactly the day just closed 1ms earlier is usable).
  Raw inputs at T use only days <= D*(T). Cross-sectional moments use only the
  5 raws at the same T (no trailing fit, no full-sample rank).
- Cross-sectional z at T (H4 raw = Amihud30, H5 raw = MAX21):
  `z_sym = (x_sym - mean(x over finite syms)) / std(ddof=1 over finite syms)`;
  if < 2 finite syms or std == 0/non-finite, all z = 0 for finite raws;
  NaN raw -> NaN z -> multiplier 1.
- A3 size-neutralised z: rank Size30 ascending at T; terciles by rank
  [0,1] -> group 0, [2,3] -> group 1, [4] -> group 2. Within each group with
  >= 2 finite Amihud30, z = (x - group mean)/group std(ddof=1); group of 1 or
  std 0/non-finite -> z = 0; NaN raw -> NaN. (Majors-only so nearly identical
  to A1; included to pre-empt the size confound as specified.)

## Book-gate mechanism (fixed, v426 copy)

- Base = G2 (`R2B1D17BFG2` in v421: rule inv, k 1.0, kd 1.7, bear True, G 2.0).
  Mechanism copied from `research/parallel/rounds/parallel-20260906-r2/v426/v426_book_brake.py`:
  multiplier on STANDARD book rows after the bear filter (BTC 4h open <
  1200-bar mean -> longs x0.5, same as v426) and before the shifted-clock
  forward fill. Rows before 2021-09-24 are not tilted (v426 convention).
  Harness, costs, fills, reset metric, full-path DD exactly as v426/v421
  (gate costs: maker 0.0002, taker 0.00055, longs pay 0.0001 per 8h settlement
  00/08/16 UTC, shorts nothing; limit fills only on 1m trade-through, no fill
  in first 5 min after a 4h close (`win_start=5`); stop-first in same 1m bar).
- Multipliers clipped to [0.5, 1.5] (disclosed; avoids negative/extreme sizing
  when |z| is large; turnover stays within book cadence). NaN z -> 1.0.
- Pre-registered variants (ONLY these six):
  - A1 (H4 both-legs): every non-zero bear-filtered weight w -> w * (1+0.25*z_illiq),
    clipped. Illiquid coins get larger absolute weight on both sides.
  - A2 (H4 longs-only asymmetric, spec parenthetical exact): longs w>0 ->
    w * (1+0.25*max(z_illiq,0)); shorts/flats unchanged. Liquid longs untouched.
  - A3 (H4 size-neutralised both-legs): every non-zero w -> w * (1+0.25*z_illiq_terc),
    clipped.
  - X1 (H5 crypto sign both-legs): every non-zero w -> w * (1+0.25*z_max), clipped.
  - X2 (H5 crypto sign longs-only): longs w>0 -> w * (1+0.25*z_max), clipped;
    shorts/flats unchanged.
  - X3 (H5 stock-sign falsification both-legs, expected to lose): every non-zero w ->
    w * (1-0.25*z_max), clipped (underweight high-MAX).
- Exposure-matched controls (one per variant, per template):
  - For both-legs variants (A1/A3/X1/X3): per anchor year constant c applied to
    every non-zero row of that year, c = variant's realised mean multiplier over
    non-zero cells in that year.
  - For longs-only variants (A2/X2): per anchor year constant c applied to every
    long row (w>0) of that year, c = variant's realised mean multiplier over
    long cells in that year; shorts unchanged.
  - Control means are realised-exposure only (no return information); the variant
    must beat its control to claim timing value. Rows: C_A1, C_A2, C_A3, C_X1,
    C_X2, C_X3.
- Full row set (13): G2, A1, A2, A3, X1, X2, X3, C_A1, C_A2, C_A3, C_X1, C_X2, C_X3.

## Reproduction gate (stop if failed)

- Reproduce G2 exactly from `v421/v421_runs.pkl` + `v421_result.json` via
  `reset_metric.year_reset` + `v388.mix` full-path DD:
  5.41 %/mo, W 2.588, max yearly DD 16.91, full-path DD 16.82, yearly rows
  (2.588/10.86, 3.282/16.91, 6.045/15.81, 10.677/8.27, 4.648/12.9).
  Else STOP, no overlay. The engine harness must also re-run G2 to the same
  triple before any variant comparison is valid.

## Selection (ONLY on dev4 2021-09-24..2025-09-23, per template)

- Candidate iff: dev4 mean > G2's 5.601 AND dev4 worst year > G2's 2.588 AND
  max yearly DD <= 16.91 + 0.5 AND beats its exposure-matched control on dev4 mean.
- Score the most recent year 2025-09-24..2026-09-23 ONCE, only for a candidate
  (and G2/control). Otherwise the most recent year is a labelled engine byproduct,
  never a selection input. Robust view (DD<=20, no losing dev year; prefer dev4
  mean>=5% then highest dev4 worst-year) also reported.
- Report per year: 4-phase reset R (%/mo geometric), yearly DD, full-path DD,
  share of tilted cells, mean multiplier, and variant vs control rows.

## Leakage checks (pre-registered)

- Feature timing: daily close_time < T (D+1 00:00 <= T); sampled-T truncation test
  must leave multipliers unchanged; ±1s boundary test exposes exactly the prior day.
- Label windows: none fitted (engine uses realised 1m path).
- Fit windows: no fits; cross-sectional mean/std at same T only; thresholds (30d,
  21d, 0.25, clip, tercile rule) fixed here.
- Fill timing: engine `win_start=5` + 1m trade-through + stop-first (v426 harness,
  G2 bit-exact). Tests assert these constants in the engine script.

## Deliverables

- `research/tournament/oc_lit_xs/`: PLAN.md (this file), `xs_signal.py` (daily
  raws + XS z + multipliers), `compute_xs_engine.py` (13-row 4-phase engine via
  heavy_slot), `results.json`, `REPORT.md` (per-year tables, what failed,
  3-line Vietnamese verdict).
- `tests/test_oc_lit_xs.py`: >=1 causality/truncation test + >=1 hand-checked
  synthetic case; run `.venv/Scripts/python.exe -m pytest tests/test_oc_lit_xs.py -q`.
  Stop when done.

## Post-hoc log

- (Filled after outcomes; no definition changes permitted without a disclosed extra row.)
- Outcome 2026-10-07: G2 reproduced to the digit; engine re-ran G2 bit-exact.
  Dev4: A1 5.844/W 2.798/DD 16.81 CANDIDATE (beats G2 5.601/2.588/16.91 and C_A1
  5.662; Y4 4.75 vs G2 4.648 scored once); A2/A3/X1/X2/X3 REJECT (fail mean gate;
  X3 also DD 18.19). No definition was changed after seeing outcomes (two
  pre-outcome code fixes only: tz-aware searchsorted + missing paren).
